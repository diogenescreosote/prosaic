#!/usr/bin/env python3
"""A per-matter message store built from SMS Backup & Restore XML.

`phone_logs.py` streams one backup per question, which is right for a
single extract and wrong for daily use: a full `sms-*.xml` runs to a
gigabyte and a half of inline base64 attachments, and every search
re-reads it. This module ingests the backups once into one SQLite file
per matter, incrementally, and answers searches from there in
milliseconds. Spec: specs/phone-store.md. ADR-0048.

    phone_store.py ingest <matter> [--exhaustive] [-v]
    phone_store.py search <matter> [--text Q] [--number N] [--from D] [--to D]
                                   [--kind sms|mms|call] [--format md|json]
    phone_store.py stats  <matter>

Configuration is matter.yaml's `phone:` block:

    phone:
      sources: ["~/backups/sms-*.xml", "~/backups/calls-*.xml"]
      since: "2024-05-01"              # nothing older is ever stored
      db: derived/phone/messages.sqlite  # default; keep it gitignored

What makes it cheap. A backup is two or three blocks of records (`sms`
then `mms`; or `call`), each in ascending date order. The store keeps a
`coverage` table: for each record kind, the date intervals some backup
has been read across in full. Ingesting a backup reads only the
intervals of `[since, backup date]` that coverage lacks, and reaches
them by bisecting byte offsets (a record start is found by its tag;
`<` cannot occur inside an attribute value or base64), so a daily run
reads the new tail of the new file and nothing else. A backup found out
of order is reread in full. Files below FULL_READ_BELOW are always read
whole: they cost nothing, and reading every one keeps records a later
backup no longer carries (a deleted call log entry).

The store is derived, never a source of truth: delete it and `ingest`
rebuilds it from the backups, which are never modified. Attachment bytes
are never stored; each part keeps its type, name, size and sha256.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from triage.phone_logs import (
    BANNER,
    CALL_TYPES,
    MMS_BOXES,
    SMS_TYPES,
    fmt_duration,
    fmt_when,
    parse_window,
)

SCHEMA_VERSION = 1
DEFAULT_DB = "derived/phone/messages.sqlite"

#: Backups smaller than this are read whole, never bisected (calls files
#: are a few hundred kilobytes; sms files run to gigabytes).
FULL_READ_BELOW = 64 * 1024 * 1024

#: How much earlier than its gap each read starts, so a message that
#: reached the phone late, carrying an earlier timestamp, is still picked
#: up by the next backup's tail read. Dedup absorbs the overlap.
OVERLAP_DAYS = 3

#: Bytes per read while parsing; a probe for a record start reads
#: PROBE bytes first and doubles up to CHUNK.
CHUNK = 1024 * 1024
PROBE = 16 * 1024
#: Bisection stops and scans forward once the window is this small.
BISECT_MIN = 64 * 1024
#: Bytes hashed from the head of a file for its fingerprint.
HEAD_BYTES = 64 * 1024

DAY_MS = 86_400_000

#: MMS address roles (WAP PDU header codes, as the app writes them).
ADDR_ROLES = {"137": "from", "151": "to", "130": "cc", "129": "bcc"}

#: Record tags, the coverage kind each feeds, and the file kind holding it.
RECORD_TAGS = ("sms", "mms", "call")
FILE_KIND_TAGS = {"sms": ("sms", "mms"), "calls": ("call",)}

_RECORD_START = re.compile(rb"<(sms|mms|call)[\s/>]")
_DATE_ATTR = re.compile(rb'\sdate="(-?\d+)"')
_ROOT_START = re.compile(rb"<(smses|calls)(\s[^<]*?)?/?>")
_ATTR = re.compile(rb'([\w:]+)="([^"]*)"')
_STAMP = re.compile(r"(\d{14})")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,              -- sms | calls
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    fingerprint TEXT,                -- sha256(size + first 64 KiB)
    backup_ms INTEGER,               -- when the backup was taken
    head_ms INTEGER,                 -- date of its first record
    status TEXT NOT NULL,            -- read | partial | covered | empty
    mode TEXT,                       -- full | seek | none
    ordered INTEGER,                 -- 1 ascending, 0 found out of order
    records_seen INTEGER DEFAULT 0,
    rows_added INTEGER DEFAULT 0,
    min_date_ms INTEGER,             -- of the records parsed
    max_date_ms INTEGER,
    bytes_read INTEGER DEFAULT 0,
    seconds REAL,
    since_ms INTEGER,                -- the store's since when examined
    ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coverage (
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,               -- sms | mms | call
    lo_ms INTEGER NOT NULL,
    hi_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,              -- sms | mms (RCS arrives as either)
    date_ms INTEGER NOT NULL,
    date_sent_ms INTEGER,
    type_code INTEGER,               -- sms type / mms msg_box
    direction TEXT,
    address TEXT,                    -- as the backup gives it
    address_norm TEXT,               -- primary counterpart, normalized
    contact TEXT,
    subject TEXT,
    body TEXT NOT NULL DEFAULT '',
    n_attachments INTEGER NOT NULL DEFAULT 0,
    sub_id TEXT,
    source_id INTEGER,
    dedup TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS addresses (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    address TEXT,
    address_norm TEXT NOT NULL,
    role TEXT NOT NULL               -- from | to | cc | bcc
);
CREATE TABLE IF NOT EXISTS parts (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    seq INTEGER,
    content_type TEXT,
    name TEXT,
    size INTEGER,                    -- decoded bytes (text: UTF-8 bytes)
    sha256 TEXT                      -- of the decoded bytes; NULL for text
);
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY,
    date_ms INTEGER NOT NULL,
    number TEXT,
    number_norm TEXT,
    duration INTEGER,
    type_code INTEGER,
    direction TEXT,
    contact TEXT,
    source_id INTEGER,
    dedup TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS messages_addr_date ON messages(address_norm, date_ms);
CREATE INDEX IF NOT EXISTS messages_date ON messages(date_ms);
CREATE INDEX IF NOT EXISTS addresses_norm ON addresses(address_norm, message_id);
CREATE INDEX IF NOT EXISTS addresses_msg ON addresses(message_id);
CREATE INDEX IF NOT EXISTS parts_msg ON parts(message_id);
CREATE INDEX IF NOT EXISTS calls_number_date ON calls(number_norm, date_ms);
CREATE INDEX IF NOT EXISTS calls_date ON calls(date_ms);
CREATE INDEX IF NOT EXISTS coverage_tag ON coverage(tag, lo_ms);
"""

FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, body, subject) VALUES (new.id, new.body, new.subject);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, body, subject)
    VALUES ('delete', old.id, old.body, old.subject);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, body, subject)
    VALUES ('delete', old.id, old.body, old.subject);
  INSERT INTO messages_fts(rowid, body, subject) VALUES (new.id, new.body, new.subject);
END;
"""


# --- normalization and keys ------------------------------------------


def normalize_address(raw: str | None) -> str:
    """The index key for a phone number or sender.

    Digits only, and the last ten of them when there are at least ten,
    so `+1 (555) 000-1234`, `15550001234` and `555-000-1234` share one
    key. Short codes keep all their digits. A sender with no digits at
    all (an alphanumeric sender ID) is keyed on its lowercased text.
    """
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 10:
        return digits[-10:]
    return digits or text.lower()


def dedup_key(*fields: object) -> str:
    """A stable identity for a record across overlapping backups."""
    joined = "\x1f".join("" if f is None else str(f) for f in fields)
    return hashlib.sha256(joined.encode("utf-8", "surrogatepass")).hexdigest()


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "", "null") else None
    except ValueError:
        return None


def _text(value: str | None) -> str | None:
    return None if value in (None, "null") else value


def local_ms(day: str, end_of_day: bool = False) -> int:
    """Epoch ms for a local date or ISO timestamp (phone_logs's clock)."""
    lo, hi = parse_window(None if end_of_day else day, day if end_of_day else None)
    when = hi if end_of_day else lo
    assert when is not None
    return int(when.timestamp() * 1000)


def ms_day(ms: int) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d")


# --- intervals --------------------------------------------------------

Interval = tuple[int, int]


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Union of closed intervals, sorted; touching intervals join."""
    out: list[list[int]] = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [(lo, hi) for lo, hi in out]


def subtract(target: Interval, covered: Iterable[Interval]) -> list[Interval]:
    """The parts of `target` no interval in `covered` reaches."""
    lo, hi = target
    gaps: list[Interval] = []
    cursor = lo
    for clo, chi in merge(covered):
        if chi < cursor:
            continue
        if clo > hi:
            break
        if clo > cursor:
            gaps.append((cursor, clo - 1))
        cursor = max(cursor, chi + 1)
        if cursor > hi:
            break
    if cursor <= hi:
        gaps.append((cursor, hi))
    return gaps


# --- the store --------------------------------------------------------


@dataclass
class Config:
    matter: Path
    sources: list[str]
    since_ms: int
    since: str
    db: Path
    overlap_days: int = OVERLAP_DAYS

    @classmethod
    def from_matter(cls, matter: Path) -> Config:
        import yaml

        cfg_path = matter / "matter.yaml"
        if not cfg_path.is_file():
            raise SystemExit(f"no matter.yaml in {matter}")
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        phone = cfg.get("phone")
        if not isinstance(phone, dict) or not phone.get("sources"):
            raise SystemExit(
                f"{cfg_path}: no phone: block with sources (see prosaic docs/phone-logs.md)"
            )
        sources = phone["sources"]
        if isinstance(sources, str):
            sources = [sources]
        since = str(phone.get("since") or "1970-01-01")
        db = Path(str(phone.get("db") or DEFAULT_DB)).expanduser()
        return cls(
            matter=matter,
            sources=[str(s) for s in sources],
            since=since,
            since_ms=local_ms(since),
            db=db if db.is_absolute() else matter / db,
            overlap_days=int(phone.get("overlap_days", OVERLAP_DAYS)),
        )

    def source_files(self) -> list[Path]:
        found: dict[str, Path] = {}
        for pattern in self.sources:
            pat = Path(pattern).expanduser()
            if not pat.is_absolute():
                pat = self.matter / pat
            for p in sorted(pat.parent.glob(pat.name)):
                if p.is_file():
                    found[str(p)] = p
        return list(found.values())


def fts_tokenizer(conn: sqlite3.Connection) -> str:
    """`trigram` when this SQLite has it (3.34+), else `unicode61`."""
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.probe_tri USING fts5(x, tokenize='trigram')")
        conn.execute("DROP TABLE temp.probe_tri")
        return "trigram"
    except sqlite3.OperationalError:
        return "unicode61"


def connect(db: Path, since: str | None = None, since_ms: int | None = None) -> sqlite3.Connection:
    """Open (creating if needed) a store and bring its schema current."""
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    tok = get_meta(conn, "fts_tokenizer")
    if tok is None:
        tok = fts_tokenizer(conn)
        set_meta(conn, "fts_tokenizer", tok)
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
        f"body, subject, content='messages', content_rowid='id', tokenize='{tok}')"
    )
    conn.executescript(FTS_TRIGGERS)
    set_meta(conn, "schema_version", str(SCHEMA_VERSION))
    if since is not None and since_ms is not None:
        apply_since(conn, since, since_ms)
    conn.commit()
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))


def apply_since(conn: sqlite3.Connection, since: str, since_ms: int) -> None:
    """Record the date of relevance; react when it moves.

    Later: rows now older than it are pruned (the store never holds
    anything older). Earlier: backups once judged unneeded are judged
    again, since the newly relevant months may be in them.
    """
    old = get_meta(conn, "since_ms")
    if old is not None and int(old) != since_ms:
        if since_ms > int(old):
            conn.execute("DELETE FROM messages WHERE date_ms < ?", (since_ms,))
            conn.execute("DELETE FROM calls WHERE date_ms < ?", (since_ms,))
        else:
            conn.execute("DELETE FROM sources WHERE status IN ('covered', 'empty')")
    set_meta(conn, "since", since)
    set_meta(conn, "since_ms", str(since_ms))


def coverage(conn: sqlite3.Connection, tag: str) -> list[Interval]:
    rows = conn.execute("SELECT lo_ms, hi_ms FROM coverage WHERE tag = ?", (tag,)).fetchall()
    return merge((int(r[0]), int(r[1])) for r in rows)


# --- reading a backup -------------------------------------------------


@dataclass
class Record:
    pos: int
    tag: str
    date: int | None


@dataclass
class Block:
    tag: str
    start: int
    end: int
    first: int | None


class Backup:
    """Random access to one backup file, counting the bytes it reads."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.size = path.stat().st_size
        self.fh: IO[bytes] = path.open("rb")
        self.bytes_read = 0
        self._head: bytes | None = None

    def close(self) -> None:
        self.fh.close()

    def __enter__(self) -> Backup:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def read(self, pos: int, n: int) -> bytes:
        self.fh.seek(pos)
        data = self.fh.read(n)
        self.bytes_read += len(data)
        return data

    def head(self) -> bytes:
        if self._head is None:
            self._head = self.read(0, HEAD_BYTES)
        return self._head

    def fingerprint(self) -> str:
        return hashlib.sha256(str(self.size).encode() + self.head()).hexdigest()[:32]

    def root(self) -> tuple[str, dict[str, str]]:
        m = _ROOT_START.search(self.head())
        if not m:
            raise ValueError(f"{self.path.name}: not an SMS Backup & Restore file")
        attrs = {
            k.decode(): v.decode("utf-8", "replace") for k, v in _ATTR.findall(m.group(2) or b"")
        }
        return m.group(1).decode(), attrs

    def record_at(self, pos: int) -> Record | None:
        """The first record whose start tag begins at or after `pos`."""
        buf, base = self.read(pos, PROBE), pos
        while True:
            m = _RECORD_START.search(buf)
            if m:
                start = m.start()
                end = buf.find(b"<", start + 1)
                while end < 0 and base + len(buf) < self.size:
                    buf += self.read(base + len(buf), CHUNK)
                    end = buf.find(b"<", start + 1)
                tag_text = buf[start : end if end >= 0 else len(buf)]
                d = _DATE_ATTR.search(tag_text)
                return Record(base + start, m.group(1).decode(), int(d.group(1)) if d else None)
            if base + len(buf) >= self.size or not buf:
                return None
            # Keep a short tail so a tag split across reads is still seen.
            keep = buf[-8:]
            base = base + len(buf) - len(keep)
            step = min(CHUNK, max(PROBE, 2 * len(buf)))
            buf = keep + self.read(base + len(keep), step)

    def lower_bound(self, start: int, end: int, pred: Any) -> int:
        """First record start in [start, end) where `pred` holds, `pred`
        being false-then-true over the records in file order; `end` if
        none. Bisection over byte offsets, then a short forward scan."""
        lo, hi = start, end
        while hi - lo > BISECT_MIN:
            mid = (lo + hi) // 2
            rec = self.record_at(mid)
            if rec is None or rec.pos >= hi or pred(rec):
                hi = mid
            else:
                lo = rec.pos + 1
        rec = self.record_at(lo)
        while rec is not None and rec.pos < end:
            if pred(rec):
                return rec.pos
            rec = self.record_at(rec.pos + 1)
        return end

    def last_tag(self) -> str | None:
        """The tag of the file's last record, read from its tail."""
        step = PROBE
        while True:
            lo = max(0, self.size - step)
            found = list(_RECORD_START.finditer(self.read(lo, self.size - lo)))
            if found:
                return found[-1].group(1).decode()
            if lo == 0:
                return None
            step *= 2

    def blocks(self) -> list[Block]:
        """The file's runs of one record tag, in order."""
        out: list[Block] = []
        rec = self.record_at(0)
        last = self.last_tag()
        while rec is not None:
            tag, start, first = rec.tag, rec.pos, rec.date
            if out and tag == last:  # a later run of the last tag ends with the file
                out.append(Block(tag, start, self.size, first))
                break
            end = self.lower_bound(start, self.size, lambda r, t=tag: r.tag != t)
            out.append(Block(tag, start, end, first))
            rec = self.record_at(end) if end < self.size else None
        return out


def _chunks(bk: Backup, pos: int) -> Iterator[bytes]:
    while pos < bk.size:
        data = bk.read(pos, CHUNK)
        if not data:
            return
        pos += len(data)
        yield data


def iter_records(bk: Backup, pos: int = 0, root_tag: str | None = None) -> Iterator[ET.Element]:
    """Stream complete record elements from `pos` on.

    From 0 the file is parsed as written. From a record start inside it,
    a synthetic opening root tag is fed first, so the file's own closing
    tag still balances. Each element is cleared once the caller has
    moved on, which with the root cleared keeps memory to one record.
    """
    parser: Any = ET.XMLPullParser(events=("start", "end"))  # typeshed types events loosely
    if pos:
        parser.feed(f"<{root_tag}>".encode())
    root: ET.Element | None = None
    feeding = _chunks(bk, pos)
    while True:
        data = next(feeding, None)
        if data is None:
            parser.close()  # flushes the events expat still holds
        else:
            parser.feed(data)
        for event, elem in parser.read_events():
            assert isinstance(elem, ET.Element)
            if event == "start":
                if root is None:
                    root = elem
                continue
            if elem.tag in RECORD_TAGS:
                yield elem
                if root is not None:
                    root.clear()
        if data is None:
            return


@dataclass
class FileResult:
    path: Path
    status: str = "read"
    mode: str = "full"
    ordered: bool | None = True
    seen: int = 0
    added: int = 0
    min_ms: int | None = None
    max_ms: int | None = None
    bytes_read: int = 0
    seconds: float = 0.0
    note: str = ""
    tag_min: dict[str, int] = field(default_factory=dict)
    covered: list[tuple[str, int, int]] = field(default_factory=list)


class OutOfOrder(Exception):
    """A backup's records are not in ascending date order within a block."""


class Ingester:
    def __init__(self, conn: sqlite3.Connection, since_ms: int, overlap_days: int) -> None:
        self.conn = conn
        self.since_ms = since_ms
        self.margin = overlap_days * DAY_MS
        self.source_id: int | None = None

    # -- inserting records --

    def insert(self, elem: ET.Element, res: FileResult) -> None:
        date = _int(elem.get("date"))
        if date is None:
            return
        res.seen += 1
        res.min_ms = date if res.min_ms is None else min(res.min_ms, date)
        res.tag_min[elem.tag] = min(res.tag_min.get(elem.tag, date), date)
        res.max_ms = date if res.max_ms is None else max(res.max_ms, date)
        if date < self.since_ms:
            return
        if elem.tag == "call":
            added = self._call(elem, date)
        elif elem.tag == "sms":
            added = self._sms(elem, date)
        else:
            added = self._mms(elem, date)
        res.added += added

    def _call(self, e: ET.Element, date: int) -> int:
        number = e.get("number")
        norm = normalize_address(number)
        code = e.get("type")
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO calls(date_ms, number, number_norm, duration, type_code,"
            " direction, contact, source_id, dedup) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                date,
                number,
                norm,
                _int(e.get("duration")) or 0,
                _int(code),
                CALL_TYPES.get(code or "", f"type={code}"),
                _text(e.get("contact_name")),
                self.source_id,
                dedup_key("call", norm, date, code, e.get("duration")),
            ),
        )
        return cur.rowcount

    def _sms(self, e: ET.Element, date: int) -> int:
        address = e.get("address")
        norm = normalize_address(address)
        code = e.get("type")
        body = e.get("body") or ""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO messages(kind, date_ms, date_sent_ms, type_code, direction,"
            " address, address_norm, contact, subject, body, sub_id, source_id, dedup)"
            " VALUES ('sms',?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                date,
                _int(e.get("date_sent")),
                _int(code),
                SMS_TYPES.get(code or "", f"type={code}"),
                address,
                norm,
                _text(e.get("contact_name")),
                _text(e.get("subject")),
                body,
                _text(e.get("sub_id")),
                self.source_id,
                dedup_key("sms", norm, date, code, body),
            ),
        )
        if cur.rowcount:
            role = "from" if code == "1" else "to"
            self.conn.execute(
                "INSERT INTO addresses(message_id, address, address_norm, role) VALUES (?,?,?,?)",
                (cur.lastrowid, address, norm, role),
            )
        return cur.rowcount

    def _mms(self, e: ET.Element, date: int) -> int:
        addrs = [
            (a.get("address"), ADDR_ROLES.get(a.get("type") or "", f"type={a.get('type')}"))
            for a in e.iter("addr")
            if a.get("address")
        ]
        if not addrs:
            addrs = [(p, "to") for p in (e.get("address") or "").split("~") if p]
        texts: list[str] = []
        parts: list[ET.Element] = []
        for part in e.iter("part"):
            ct = part.get("ct") or "unknown"
            if ct == "application/smil":
                continue
            parts.append(part)
            text = _text(part.get("text"))
            if ct.startswith("text/plain") and text is not None:
                texts.append(text)
        body = "\n".join(texts)
        address = e.get("address")
        first = (address or "").split("~")[0]
        box = e.get("msg_box")
        shape = sorted(
            (p.get("ct") or "", len(p.get("data") or p.get("text") or "")) for p in parts
        )
        norms = sorted({normalize_address(a) for a, _ in addrs})
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO messages(kind, date_ms, date_sent_ms, type_code, direction,"
            " address, address_norm, contact, subject, body, n_attachments, sub_id, source_id,"
            " dedup) VALUES ('mms',?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                date,
                _int(e.get("date_sent")),
                _int(box),
                MMS_BOXES.get(box or "", f"msg_box={box}"),
                address,
                normalize_address(first),
                _text(e.get("contact_name")),
                _text(e.get("sub")),
                body,
                sum(1 for p in parts if not (p.get("ct") or "").startswith("text/plain")),
                _text(e.get("sub_id")),
                self.source_id,
                dedup_key("mms", "~".join(norms), date, box, body, shape),
            ),
        )
        if not cur.rowcount:
            return 0
        mid = cur.lastrowid
        self.conn.executemany(
            "INSERT INTO addresses(message_id, address, address_norm, role) VALUES (?,?,?,?)",
            [(mid, a, normalize_address(a), role) for a, role in addrs],
        )
        rows = []
        for part in parts:
            data = part.get("data")
            text = _text(part.get("text"))
            size: int | None
            digest: str | None = None
            if data:
                try:
                    raw = base64.b64decode(data)
                    size, digest = len(raw), hashlib.sha256(raw).hexdigest()
                except ValueError:
                    size = None
            else:
                size = len(text.encode("utf-8", "surrogatepass")) if text is not None else None
            name = next(
                (v for k in ("name", "fn", "cl") if (v := _text(part.get(k))) is not None),
                None,
            )
            rows.append((mid, _int(part.get("seq")), part.get("ct"), name, size, digest))
        self.conn.executemany(
            "INSERT INTO parts(message_id, seq, content_type, name, size, sha256)"
            " VALUES (?,?,?,?,?,?)",
            rows,
        )
        return 1

    # -- reading a file --

    def read_full(self, bk: Backup, res: FileResult) -> None:
        """Every record, in file order; notes whether order held."""
        last: dict[str, int] = {}
        for elem in iter_records(bk):
            d = _int(elem.get("date"))
            if d is not None:
                if d < last.get(elem.tag, d):
                    res.ordered = False
                last[elem.tag] = d
            self.insert(elem, res)
        res.mode = "full"

    def read_interval(
        self,
        bk: Backup,
        root_tag: str,
        block: Block,
        lo: int,
        hi: int,
        end: int,
        res: FileResult,
    ) -> None:
        """The records of one block dated within [lo, hi]; to the end of
        the block when `hi` reaches the backup's own date `end`."""
        start = bk.lower_bound(
            block.start, block.end, lambda r: r.tag == block.tag and (r.date or 0) >= lo
        )
        if start >= block.end:
            return
        last: int | None = None
        stop = hi if hi < end else None
        for elem in iter_records(bk, start, root_tag):
            if elem.tag != block.tag:
                break
            d = _int(elem.get("date"))
            if d is not None:
                if last is not None and d < last:
                    raise OutOfOrder(block.tag)
                last = d
                if stop is not None and d > stop:
                    break
            self.insert(elem, res)


def plan_reads(
    conn: sqlite3.Connection, tags: Iterable[str], since_ms: int, end_ms: int, margin: int
) -> dict[str, list[Interval]]:
    """For each tag, the intervals of [since, end] coverage lacks, each
    started `margin` earlier (never before since): a message that reached
    the phone late carries an earlier date than the last backup's tail."""
    out: dict[str, list[Interval]] = {}
    for tag in tags:
        gaps = subtract((since_ms, end_ms), coverage(conn, tag))
        widened = merge((max(since_ms, lo - margin), hi) for lo, hi in gaps)
        if widened:
            out[tag] = widened
    return out


def file_kind(path: Path) -> str:
    return "calls" if path.name.startswith("calls") else "sms"


def backup_ms(path: Path, attrs: dict[str, str]) -> int:
    """When the backup was taken: the root's backup_date, else the
    timestamp in the file name, else the file's mtime."""
    stamp = _int(attrs.get("backup_date"))
    if stamp:
        return stamp
    m = _STAMP.search(path.name)
    if m:
        return int(datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S").timestamp() * 1000)
    return int(path.stat().st_mtime * 1000)


def _update_source(conn: sqlite3.Connection, sid: int, **cols: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE sources SET {sets} WHERE id = ?", (*cols.values(), sid))


def _record_source(conn: sqlite3.Connection, path: Path, kind: str, **cols: Any) -> int:
    st = path.stat()
    base = {
        "path": str(path),
        "name": path.name,
        "kind": kind,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "ingested_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    base.update(cols)
    conn.execute("DELETE FROM sources WHERE path = ?", (str(path),))
    keys = ", ".join(base)
    marks = ", ".join("?" for _ in base)
    cur = conn.execute(f"INSERT INTO sources({keys}) VALUES ({marks})", tuple(base.values()))
    assert cur.lastrowid is not None
    return cur.lastrowid


def unchanged(conn: sqlite3.Connection, path: Path) -> bool:
    st = path.stat()
    row = conn.execute(
        "SELECT 1 FROM sources WHERE path = ? AND size = ? AND mtime_ns = ?",
        (str(path), st.st_size, st.st_mtime_ns),
    ).fetchone()
    return row is not None


def ingest_file(
    conn: sqlite3.Connection,
    path: Path,
    since_ms: int,
    overlap_days: int = OVERLAP_DAYS,
    exhaustive: bool = False,
) -> FileResult:
    """Bring one backup's relevant, not-yet-covered records into the store."""
    t0 = time.monotonic()
    res = FileResult(path)
    ing = Ingester(conn, since_ms, overlap_days)
    kind = file_kind(path)
    common: dict[str, Any] = {"since_ms": since_ms}
    if not exhaustive and path.stat().st_size >= FULL_READ_BELOW:
        # Judged from the name alone, with no read: over a synced drive
        # even opening an uncached file costs seconds.
        end_ms = backup_ms(path, {})
        if not plan_reads(conn, FILE_KIND_TAGS[kind], since_ms, end_ms, ing.margin):
            res.status, res.mode = "covered", "none"
            res.seconds = time.monotonic() - t0
            _record_source(
                conn, path, kind, status=res.status, mode=res.mode, backup_ms=end_ms, **common
            )
            conn.commit()
            return res
    with Backup(path) as bk:
        root_tag, attrs = bk.root()
        kind = "calls" if root_tag == "calls" else "sms"
        end_ms = backup_ms(path, attrs)
        first = bk.record_at(0)
        head_ms = first.date if first else None
        fp = bk.fingerprint()
        common.update(fingerprint=fp, backup_ms=end_ms, head_ms=head_ms)
        if first is None:
            res.status, res.mode = "empty", "none"
        else:
            # The source row exists first so records can point at it.
            ing.source_id = _record_source(conn, path, kind, status="partial", **common)
            if exhaustive or bk.size < FULL_READ_BELOW:
                ing.read_full(bk, res)
                res.covered = full_coverage(res, since_ms, end_ms)
            else:
                _read_planned(conn, bk, root_tag, kind, end_ms, ing, res)
        res.bytes_read = bk.bytes_read
    res.seconds = time.monotonic() - t0
    if ing.source_id is None:
        ing.source_id = _record_source(conn, path, kind, status=res.status, **common)
    sid = ing.source_id
    _update_source(
        conn,
        sid,
        status=res.status,
        mode=res.mode,
        ordered=None if res.ordered is None else int(res.ordered),
        records_seen=res.seen,
        rows_added=res.added,
        min_date_ms=res.min_ms,
        max_date_ms=res.max_ms,
        bytes_read=res.bytes_read,
        seconds=round(res.seconds, 3),
    )
    conn.executemany(
        "INSERT INTO coverage(source_id, tag, lo_ms, hi_ms) VALUES (?,?,?,?)",
        [(sid, tag, lo, hi) for tag, lo, hi in res.covered if hi >= lo],
    )
    conn.commit()
    return res


def full_coverage(res: FileResult, since_ms: int, end_ms: int) -> list[tuple[str, int, int]]:
    """A whole-file read covers, for each record kind it holds, from
    that kind's first record (or since) to the backup's date."""
    return [(tag, max(since_ms, lo), end_ms) for tag, lo in res.tag_min.items()]


def _read_planned(
    conn: sqlite3.Connection,
    bk: Backup,
    root_tag: str,
    kind: str,
    end_ms: int,
    ing: Ingester,
    res: FileResult,
) -> None:
    plan = plan_reads(conn, FILE_KIND_TAGS[kind], ing.since_ms, end_ms, ing.margin)
    if not plan:
        res.status, res.mode = "covered", "none"
        return
    res.mode = "seek"
    try:
        for block in bk.blocks():
            for lo, hi in plan.get(block.tag, []):
                lo = max(lo, block.first or lo)
                if lo > hi:
                    continue
                ing.read_interval(bk, root_tag, block, lo, hi, end_ms, res)
                res.covered.append((block.tag, lo, min(hi, end_ms)))
        res.ordered = True
        if not res.covered:  # every gap lay before this backup's history
            res.status, res.mode = "covered", "none"
    except OutOfOrder as exc:
        res.covered.clear()
        res.ordered = None
        res.note = f"{exc.args[0]} records out of date order; reread in full"
        ing.read_full(bk, res)
        res.covered = full_coverage(res, ing.since_ms, end_ms)


def choose_order(conn: sqlite3.Connection, files: list[Path], since_ms: int) -> list[Path]:
    """The order to examine new backups in.

    Small files: all of them, newest first. Large files: the newest
    first (it holds the new tail), then a greedy interval cover of what
    is still missing before the covered range: repeatedly the backup
    reaching furthest forward among those starting at or before the
    point reached, judged from each file's first record (one small read)
    and its backup date. Large files the cover never needs are returned
    last; ingesting them finds nothing uncovered and reads nothing.
    """
    stamped = sorted(files, key=lambda p: backup_ms(p, {}), reverse=True)
    small = [p for p in stamped if p.stat().st_size < FULL_READ_BELOW]
    large = [p for p in stamped if p.stat().st_size >= FULL_READ_BELOW]
    if not large:
        return small
    order = [large[0]]
    rest = large[1:]

    def head(path: Path) -> int | None:
        with Backup(path) as bk:
            rec = bk.record_at(0)
            return rec.date if rec else None

    starts = [lo for tag in FILE_KIND_TAGS["sms"] for lo, _ in coverage(conn, tag)[:1]]
    newest = head(large[0])
    if newest is not None:
        starts.append(newest)
    point = min(starts) if starts else None
    chosen: list[Path] = []
    if point is not None and point > since_ms:
        reach, target = since_ms, point
        pool = {p: h for p in rest if (h := head(p)) is not None}
        while reach < target and pool:
            starting = [p for p, h in pool.items() if h <= reach]
            if starting:
                best = max(starting, key=lambda p: backup_ms(p, {}))
            else:
                best = min(pool, key=lambda p: pool[p])  # a hole nothing covers
            if backup_ms(best, {}) <= reach:
                break
            chosen.append(best)
            reach = backup_ms(best, {})
            del pool[best]
    order += chosen
    order += [p for p in rest if p not in chosen]
    return order + small


def ingest(cfg: Config, exhaustive: bool = False, log: Any = None) -> list[FileResult]:
    """Ingest every configured backup not already ingested unchanged."""
    conn = connect(cfg.db, cfg.since, cfg.since_ms)
    try:
        files = [p for p in cfg.source_files() if not unchanged(conn, p)]
        results = []
        for path in choose_order(conn, files, cfg.since_ms):
            res = ingest_file(conn, path, cfg.since_ms, cfg.overlap_days, exhaustive)
            results.append(res)
            if log:
                log(res)
        return results
    finally:
        conn.close()


# --- searching --------------------------------------------------------


@dataclass
class Query:
    text: str | None = None
    numbers: list[str] = field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None
    kind: str | None = None
    limit: int | None = None


def _fts_phrase(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def search(conn: sqlite3.Connection, q: Query) -> dict[str, list[dict[str, Any]]]:
    """Messages and calls matching every given filter, chronological."""
    lo = local_ms(q.date_from) if q.date_from else None
    hi = local_ms(q.date_to, end_of_day=True) if q.date_to else None
    keys = [normalize_address(n) for n in q.numbers]
    out: dict[str, list[dict[str, Any]]] = {"messages": [], "calls": []}

    if q.kind in (None, "sms", "mms"):
        where: list[str] = []
        params: list[Any] = []
        if q.kind:
            where.append("m.kind = ?")
            params.append(q.kind)
        if lo is not None:
            where.append("m.date_ms >= ?")
            params.append(lo)
        if hi is not None:
            where.append("m.date_ms <= ?")
            params.append(hi)
        if keys:
            where.append(
                "m.id IN (SELECT message_id FROM addresses WHERE address_norm IN"
                f" ({','.join('?' * len(keys))}))"
            )
            params.extend(keys)
        if q.text:
            tok = get_meta(conn, "fts_tokenizer")
            if tok == "trigram" and len(q.text) >= 3:
                where.append("m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)")
                params.append(_fts_phrase(q.text))
            else:
                where.append("(m.body LIKE ? OR m.subject LIKE ?)")
                params.extend([f"%{q.text}%"] * 2)
        sql = "SELECT m.* FROM messages m"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY m.date_ms, m.id"
        if q.limit:
            sql += f" LIMIT {int(q.limit)}"
        for row in conn.execute(sql, params).fetchall():
            rec = dict(row)
            rec["addresses"] = [
                dict(a)
                for a in conn.execute(
                    "SELECT address, address_norm, role FROM addresses WHERE message_id = ?",
                    (row["id"],),
                )
            ]
            rec["parts"] = [
                dict(p)
                for p in conn.execute(
                    "SELECT seq, content_type, name, size, sha256 FROM parts"
                    " WHERE message_id = ? ORDER BY seq",
                    (row["id"],),
                )
            ]
            out["messages"].append(rec)

    if q.kind in (None, "call") and not q.text:
        where, params = [], []
        if lo is not None:
            where.append("date_ms >= ?")
            params.append(lo)
        if hi is not None:
            where.append("date_ms <= ?")
            params.append(hi)
        if keys:
            where.append(f"number_norm IN ({','.join('?' * len(keys))})")
            params.extend(keys)
        sql = "SELECT * FROM calls"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date_ms, id"
        if q.limit:
            sql += f" LIMIT {int(q.limit)}"
        out["calls"] = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return out


def coverage_summary(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    return {
        tag: [(ms_day(lo), ms_day(hi)) for lo, hi in coverage(conn, tag)] for tag in RECORD_TAGS
    }


def render_md(conn: sqlite3.Connection, q: Query, found: dict[str, list[dict[str, Any]]]) -> str:
    calls, messages = found["calls"], found["messages"]
    out = ["# Phone store search", "", BANNER, ""]
    terms = []
    if q.text:
        terms.append(f'text contains "{q.text}"')
    if q.numbers:
        terms.append("number " + ", ".join(q.numbers))
    if q.kind:
        terms.append(f"kind {q.kind}")
    out.append("- Query: " + ("; ".join(terms) if terms else "(everything)"))
    window = "{} to {}".format(q.date_from or "(start of store)", q.date_to or "(end of store)")
    out.append(f"- Window: {window} (local time, inclusive)")
    out.append(f"- Store: since {get_meta(conn, 'since')}; coverage by record kind:")
    for tag, spans in coverage_summary(conn).items():
        text = ", ".join(f"{a} to {b}" for a, b in spans) or "none"
        out.append(f"  - {tag}: {text}")
    n_src = conn.execute("SELECT COUNT(*) FROM sources WHERE status != 'covered'").fetchone()[0]
    out.append(f"- Sources read: {n_src} backup file(s) (`sc phone stats` lists them)")
    out.append(f"- Result: {len(calls)} calls, {len(messages)} messages")
    out.append("- Generated by `triage/phone_store.py` from SMS Backup & Restore XML.")
    out.append("")
    if calls or (q.kind in (None, "call") and not q.text):
        out += ["## Calls", ""]
        if calls:
            out.append("| When | Direction | Duration | Number | Contact |")
            out.append("|---|---|---|---|---|")
            for c in calls:
                out.append(
                    "| {} | {} | {} | {} | {} |".format(
                        fmt_when(c["date_ms"]),
                        c["direction"],
                        fmt_duration(c["duration"] or 0),
                        c["number"] or "",
                        c["contact"] or "",
                    )
                )
        else:
            out.append("No calls match.")
        out.append("")
    if q.kind != "call":
        out += ["## Messages", ""]
        for m in messages:
            parties = ", ".join(
                f"{a['role']} {a['address']}" for a in m["addresses"] if a["address"]
            )
            head = "**{}** · {} {} · {}".format(
                fmt_when(m["date_ms"]), m["kind"].upper(), m["direction"], parties
            )
            if m["contact"]:
                head += f" ({m['contact']})"
            out.append(head)
            out.append("")
            body = m["body"] or ""
            for line in body.splitlines() or [""]:
                out.append(f"> {line}" if line else ">")
            for p in m["parts"]:
                if not (p["content_type"] or "").startswith("text/plain"):
                    out.append(
                        "> [attachment: {}{}, {} bytes, not extracted]".format(
                            p["content_type"],
                            f" {p['name']}" if p["name"] else "",
                            p["size"] if p["size"] is not None else "?",
                        )
                    )
            out.append("")
        if not messages:
            out += ["No messages match.", ""]
    return "\n".join(out).rstrip() + "\n"


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    def one(sql: str) -> Any:
        return conn.execute(sql).fetchone()[0]

    by_kind = dict(conn.execute("SELECT kind, COUNT(*) FROM messages GROUP BY kind").fetchall())
    span = conn.execute("SELECT MIN(date_ms), MAX(date_ms) FROM messages").fetchone()
    cspan = conn.execute("SELECT MIN(date_ms), MAX(date_ms) FROM calls").fetchone()
    sources = [
        dict(r)
        for r in conn.execute(
            "SELECT name, kind, status, mode, rows_added, records_seen, bytes_read, seconds,"
            " ordered FROM sources ORDER BY backup_ms DESC"
        )
    ]
    return {
        "since": get_meta(conn, "since"),
        "schema_version": get_meta(conn, "schema_version"),
        "fts_tokenizer": get_meta(conn, "fts_tokenizer"),
        "sqlite_version": sqlite3.sqlite_version,
        "messages": by_kind,
        "messages_span": [ms_day(x) if x else None for x in span],
        "calls": one("SELECT COUNT(*) FROM calls"),
        "calls_span": [ms_day(x) if x else None for x in cspan],
        "attachments": one("SELECT COUNT(*) FROM parts WHERE content_type NOT LIKE 'text/plain%'"),
        "coverage": coverage_summary(conn),
        "sources": sources,
    }


def render_stats(s: dict[str, Any], db: Path) -> str:
    out = [f"Phone store: {db}"]
    if db.exists():
        out[0] += f" ({db.stat().st_size / 1e6:.1f} MB)"
    out.append(
        f"since {s['since']}; schema {s['schema_version']}; FTS {s['fts_tokenizer']}"
        f" (SQLite {s['sqlite_version']})"
    )
    msgs = ", ".join(f"{v} {k}" for k, v in sorted(s["messages"].items())) or "0"
    out.append(f"messages: {msgs}; span {s['messages_span'][0]} to {s['messages_span'][1]}")
    out.append(f"calls: {s['calls']}; span {s['calls_span'][0]} to {s['calls_span'][1]}")
    out.append(f"attachments noted: {s['attachments']}")
    out.append("coverage (date ranges read in full from some backup):")
    for tag, spans in s["coverage"].items():
        out.append(f"  {tag}: " + (", ".join(f"{a} to {b}" for a, b in spans) or "none"))
    counts: dict[str, int] = {}
    for src in s["sources"]:
        counts[src["status"]] = counts.get(src["status"], 0) + 1
    out.append(
        f"sources: {len(s['sources'])} examined ("
        + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        + ")"
    )
    for src in s["sources"]:
        if src["status"] == "covered":
            continue
        out.append(
            "  {name}: {status}/{mode}, {rows_added} added of {records_seen} seen, "
            "{mb:.1f} MB read, {seconds}s".format(mb=(src["bytes_read"] or 0) / 1e6, **src)
        )
    return "\n".join(out) + "\n"


# --- command line ------------------------------------------------------


def _matter(raw: str) -> Path:
    p = Path(raw).expanduser().resolve()
    for cand in (p, *p.parents):
        if (cand / "matter.yaml").is_file():
            return cand
    raise SystemExit(f"no matter.yaml at or above {p}")


def _log(res: FileResult) -> None:
    sys.stderr.write(
        f"{res.path.name}: {res.status}/{res.mode}, {res.added} added of {res.seen} seen, "
        f"{res.bytes_read / 1e6:.1f} MB read, {res.seconds:.1f}s"
        + (f" ({res.note})" if res.note else "")
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sc phone", description="The matter's phone message store (SMS Backup & Restore)."
    )
    sub = ap.add_subparsers(dest="action", required=True)
    sp = sub.add_parser("ingest", help="ingest new backups named in matter.yaml phone.sources")
    sp.add_argument("matter", nargs="?", default=".")
    sp.add_argument(
        "--exhaustive", action="store_true", help="read every new backup in full (no seeking)"
    )
    sp.add_argument("-q", "--quiet", action="store_true", help="no per-file lines on stderr")
    sp = sub.add_parser("search", help="search messages and calls; prints a citable report")
    sp.add_argument("matter", nargs="?", default=".")
    sp.add_argument("--text", help="substring of the message text (case-insensitive)")
    sp.add_argument("--number", action="append", default=[], help="phone number (repeatable)")
    sp.add_argument("--from", dest="date_from", help="inclusive start, YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", help="inclusive end, YYYY-MM-DD")
    sp.add_argument("--kind", choices=("sms", "mms", "call"))
    sp.add_argument("--limit", type=int)
    sp.add_argument("--format", choices=("md", "json"), default="md")
    sp.add_argument("-o", "--output", help="write the report here instead of stdout")
    sp = sub.add_parser("stats", help="what the store holds and which backups it read")
    sp.add_argument("matter", nargs="?", default=".")
    sp.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cfg = Config.from_matter(_matter(args.matter))
    if args.action == "ingest":
        t0 = time.monotonic()
        results = ingest(cfg, exhaustive=args.exhaustive, log=None if args.quiet else _log)
        added = sum(r.added for r in results)
        read = sum(r.bytes_read for r in results)
        sys.stderr.write(
            f"ingest: {len(results)} new file(s), {added} rows added, "
            f"{read / 1e6:.1f} MB read, {time.monotonic() - t0:.1f}s\n"
        )
        return 0

    if not cfg.db.exists():
        raise SystemExit(f"no phone store at {cfg.db}; run `sc phone ingest` first")
    conn = connect(cfg.db)
    try:
        if args.action == "stats":
            s = stats(conn)
            sys.stdout.write(
                json.dumps(s, indent=2) + "\n" if args.json else render_stats(s, cfg.db)
            )
            return 0
        if args.kind == "call" and args.text:
            ap.error("--text searches messages; calls carry no text")
        q = Query(args.text, args.number, args.date_from, args.date_to, args.kind, args.limit)
        found = search(conn, q)
        if args.format == "json":
            report = json.dumps(
                {"banner": BANNER, "query": vars(q), "coverage": coverage_summary(conn), **found},
                indent=2,
                ensure_ascii=False,
            )
        else:
            report = render_md(conn, q, found)
    finally:
        conn.close()
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        sys.stderr.write(
            f"wrote {args.output}: {len(found['calls'])} calls, {len(found['messages'])} messages\n"
        )
    else:
        sys.stdout.write(report if report.endswith("\n") else report + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
