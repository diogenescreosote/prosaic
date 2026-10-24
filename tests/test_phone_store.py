"""The phone message store keeps its promises (specs/phone-store.md).

Fixtures are synthetic: invented 555 numbers, invented names, invented
text. No case material enters this repo (leak-guard discipline).
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import random
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from triage import phone_store as ps

ME = "+15550000001"
PAT = "+15550001234"
SAM = "+15550005678"
LEE = "+15550009999"


def ms(y: int, mo: int, d: int, h: int = 12, mi: int = 0) -> int:
    return int(datetime.datetime(y, mo, d, h, mi).timestamp() * 1000)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def sms_el(date: int, addr: str, typ: int, body: str) -> str:
    return (
        f'  <sms protocol="0" address="{addr}" date="{date}" type="{typ}" subject="null"'
        f' body="{esc(body)}" date_sent="{date}" contact_name="Fixture" />\n'
    )


def mms_el(date: int, box: int, others: list[str], text: str, image: bytes | None = None) -> str:
    parts = '      <part seq="-1" ct="application/smil" name="null" text="&lt;smil/&gt;" />\n'
    parts += f'      <part seq="0" ct="text/plain" name="null" text="{esc(text)}" />\n'
    if image is not None:
        data = base64.b64encode(image).decode()
        parts += (
            f'      <part seq="1" ct="image/jpeg" name="photo.jpg" text="null" data="{data}" />\n'
        )
    sender = others[0] if box == 1 else ME
    recips = [ME, *others[1:]] if box == 1 else others
    addrs = f'      <addr address="{sender}" type="137" charset="106" />\n'
    addrs += "".join(f'      <addr address="{a}" type="151" charset="106" />\n' for a in recips)
    return (
        f'  <mms date="{date}" msg_box="{box}" address="{"~".join(others)}" sub="null"'
        f' contact_name="Fixture" m_type="132">\n    <parts>\n{parts}    </parts>\n'
        f"    <addrs>\n{addrs}    </addrs>\n  </mms>\n"
    )


def sms_file(path: Path, smses: list[str], mmses: list[str], backup: int) -> Path:
    body = "".join(smses) + "".join(mmses)
    path.write_text(
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n"
        f'<smses count="{len(smses) + len(mmses)}" backup_date="{backup}" type="full">\n'
        f"{body}</smses>\n",
        encoding="utf-8",
    )
    return path


def calls_file(path: Path, calls: list[tuple[int, str, int, int]], backup: int) -> Path:
    rows = "".join(
        f'  <call number="{n}" duration="{dur}" date="{d}" type="{t}" contact_name="Fixture" />\n'
        for d, n, t, dur in calls
    )
    path.write_text(
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n"
        f'<calls count="{len(calls)}" backup_date="{backup}" type="full">\n{rows}</calls>\n',
        encoding="utf-8",
    )
    return path


def matter(tmp_path: Path, since: str = "2026-01-01", pattern: str = "backups/*.xml") -> Path:
    m = tmp_path / "matter"
    (m / "backups").mkdir(parents=True, exist_ok=True)
    (m / "matter.yaml").write_text(
        f'case: {{name: "Smith v. Roe"}}\nphone:\n  sources: ["{pattern}"]\n  since: "{since}"\n',
        encoding="utf-8",
    )
    return m


def cfg(m: Path) -> ps.Config:
    return ps.Config.from_matter(m)


def rows(db: Path, sql: str) -> list[Any]:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


IMAGE = bytes(range(256)) * 8  # 2 KiB of invented "image"


def basic_backups(m: Path) -> None:
    b = m / "backups"
    sms_file(
        b / "sms-20260301000000.xml",
        [
            sms_el(ms(2025, 12, 1), PAT, 1, "before the date of relevance"),
            sms_el(ms(2026, 2, 1), PAT, 1, "Hello from the Fixture"),
            sms_el(ms(2026, 2, 2), "(555) 000-1234", 2, 'reply & <angle> "quoted"'),
            sms_el(ms(2026, 2, 3), LEE, 1, "unrelated chatter"),
        ],
        [
            mms_el(ms(2026, 2, 4), 1, [PAT, SAM], "group picture caption", IMAGE),
            mms_el(ms(2026, 2, 5), 2, [SAM], "just text over mms"),
        ],
        ms(2026, 3, 1),
    )
    calls_file(
        b / "calls-20260301000000.xml",
        [
            (ms(2025, 11, 1), PAT, 1, 10),
            (ms(2026, 2, 1, 9), "1-555-000-1234", 1, 125),
            (ms(2026, 2, 2, 9), PAT, 3, 0),
            (ms(2026, 2, 3, 9), LEE, 2, 30),
        ],
        ms(2026, 3, 1),
    )


# --- normalization and intervals ---------------------------------------


def test_numbers_normalize_to_one_key() -> None:
    key = ps.normalize_address("+1 (555) 000-1234")
    assert key == "5550001234"
    for form in ("15550001234", "555-000-1234", "+15550001234", "1.555.000.1234"):
        assert ps.normalize_address(form) == key
    assert ps.normalize_address("882867") == "882867"  # short code: exact
    assert ps.normalize_address("ACME-Alerts") == "acme-alerts"  # sender ID
    assert ps.normalize_address(None) == ""


def test_interval_arithmetic() -> None:
    assert ps.merge([(5, 9), (1, 3), (4, 4), (20, 30)]) == [(1, 9), (20, 30)]
    assert ps.subtract((0, 100), [(10, 20), (50, 60)]) == [(0, 9), (21, 49), (61, 100)]
    assert ps.subtract((0, 100), [(-5, 200)]) == []
    assert ps.subtract((0, 100), []) == [(0, 100)]


# --- ingest --------------------------------------------------------------


def test_ingest_stores_messages_calls_and_part_metadata(tmp_path: Path) -> None:
    m = matter(tmp_path)
    basic_backups(m)
    results = ps.ingest(cfg(m))
    assert {r.path.name for r in results} == {"sms-20260301000000.xml", "calls-20260301000000.xml"}
    db = cfg(m).db
    assert db == m / "derived/phone/messages.sqlite"
    assert rows(db, "SELECT kind, COUNT(*) FROM messages GROUP BY kind ORDER BY kind") == [
        ("mms", 2),
        ("sms", 3),
    ]
    assert rows(db, "SELECT COUNT(*) FROM calls") == [(3,)]
    # MMS text parts become the body; smil is dropped; the image is metadata only.
    (body, n_att) = rows(
        db, "SELECT body, n_attachments FROM messages WHERE kind='mms' AND body LIKE 'group%'"
    )[0]
    assert body == "group picture caption" and n_att == 1
    assert rows(
        db, "SELECT content_type, name, size, sha256 FROM parts WHERE content_type='image/jpeg'"
    ) == [("image/jpeg", "photo.jpg", len(IMAGE), hashlib.sha256(IMAGE).hexdigest())]
    assert base64.b64encode(IMAGE)[:64] not in db.read_bytes()  # payload never stored
    # Addresses carry roles and normalized keys.
    roles = rows(
        db,
        "SELECT a.role, a.address_norm FROM addresses a JOIN messages m ON m.id=a.message_id"
        " WHERE m.body LIKE 'group%' ORDER BY a.role, a.address_norm",
    )
    assert roles == [("from", "5550001234"), ("to", "5550000001"), ("to", "5550005678")]
    assert rows(db, "SELECT body FROM messages WHERE body LIKE 'reply%'") == [
        ('reply & <angle> "quoted"',)
    ]


def test_since_is_never_crossed(tmp_path: Path) -> None:
    m = matter(tmp_path)
    basic_backups(m)
    ps.ingest(cfg(m))
    db = cfg(m).db
    floor = ps.local_ms("2026-01-01")
    assert rows(db, f"SELECT COUNT(*) FROM messages WHERE date_ms < {floor}") == [(0,)]
    assert rows(db, f"SELECT COUNT(*) FROM calls WHERE date_ms < {floor}") == [(0,)]
    # Moving since later prunes what is now too old.
    (m / "matter.yaml").write_text(
        (m / "matter.yaml").read_text().replace("2026-01-01", "2026-02-03"), encoding="utf-8"
    )
    ps.ingest(cfg(m))
    later = ps.local_ms("2026-02-03")
    assert rows(db, f"SELECT COUNT(*) FROM messages WHERE date_ms < {later}") == [(0,)]
    assert rows(db, "SELECT value FROM meta WHERE key='since'") == [("2026-02-03",)]


def test_overlapping_backups_never_duplicate(tmp_path: Path) -> None:
    m = matter(tmp_path)
    basic_backups(m)
    b = m / "backups"
    # The next day's backup repeats everything and adds one of each.
    old = (b / "sms-20260301000000.xml").read_text()
    sms_file(
        b / "sms-20260302000000.xml",
        [],
        [],
        ms(2026, 3, 2),
    )
    newer = old.replace(
        "</smses>", sms_el(ms(2026, 3, 1, 18), PAT, 1, "one more") + "</smses>"
    ).replace(str(ms(2026, 3, 1)), str(ms(2026, 3, 2)))
    (b / "sms-20260302000000.xml").write_text(newer, encoding="utf-8")
    ps.ingest(cfg(m))
    db = cfg(m).db
    assert rows(db, "SELECT COUNT(*) FROM messages") == [(6,)]
    assert rows(db, "SELECT COUNT(*) FROM messages_fts") == [(6,)]
    assert rows(db, "SELECT COUNT(*) FROM parts WHERE content_type='image/jpeg'") == [(1,)]


def test_unchanged_files_are_skipped(tmp_path: Path) -> None:
    m = matter(tmp_path)
    basic_backups(m)
    assert len(ps.ingest(cfg(m))) == 2
    assert ps.ingest(cfg(m)) == []  # nothing new: nothing opened
    calls_file(
        m / "backups/calls-20260302000000.xml", [(ms(2026, 3, 1, 20), PAT, 2, 5)], ms(2026, 3, 2)
    )
    again = ps.ingest(cfg(m))
    assert [r.path.name for r in again] == ["calls-20260302000000.xml"]
    assert again[0].added == 1
    # A changed file (new size/mtime) is examined again.
    f = m / "backups/calls-20260302000000.xml"
    f.write_text(f.read_text().replace('duration="5"', 'duration="55"'), encoding="utf-8")
    os.utime(f, (1, 1))
    assert [r.path.name for r in ps.ingest(cfg(m))] == ["calls-20260302000000.xml"]


# --- the seek path: large files read only what coverage lacks ---------


def big_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every fixture 'large' and every read small, so bisection and
    early stops are exercised on kilobyte files."""
    monkeypatch.setattr(ps, "FULL_READ_BELOW", 0)
    monkeypatch.setattr(ps, "BISECT_MIN", 512)
    monkeypatch.setattr(ps, "PROBE", 256)
    monkeypatch.setattr(ps, "CHUNK", 1024)
    monkeypatch.setattr(ps, "HEAD_BYTES", 1024)


def history(days: int, start: tuple[int, int, int] = (2026, 1, 2)) -> tuple[list[str], list[str]]:
    d0 = datetime.datetime(*start, 12)
    smses, mmses = [], []
    for i in range(days):
        when = int((d0 + datetime.timedelta(days=i)).timestamp() * 1000)
        smses.append(sms_el(when, PAT, 1 + i % 2, f"day {i} text message"))
        mmses.append(mms_el(when + 1000, 1, [PAT], f"day {i} picture", bytes([i % 256]) * 3000))
    return smses, mmses


def test_daily_backup_reads_only_its_new_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big_mode(monkeypatch)
    m = matter(tmp_path)
    b = m / "backups"
    s, mm = history(400)  # Jan 2, 2026 on; day 300 is Oct 29
    sms_file(b / "sms-20261030000000.xml", s[:300], mm[:300], ms(2026, 10, 30))
    first = ps.ingest(cfg(m))
    assert first[0].added == 600 and first[0].mode == "seek"
    sms_file(b / "sms-20270206000000.xml", s, mm, ms(2027, 2, 6))
    new = b / "sms-20270206000000.xml"
    (res,) = ps.ingest(cfg(m))
    assert res.added == 200
    assert res.mode == "seek" and res.ordered
    # Only the new quarter (plus the overlap margin and bisection probes) is read.
    assert res.bytes_read < new.stat().st_size * 0.35, (res.bytes_read, new.stat().st_size)
    # Same store as reading everything in full.
    fresh = matter(tmp_path / "fresh")
    sms_file(fresh / "backups/sms-20270206000000.xml", s, mm, ms(2027, 2, 6))
    ps.ingest(cfg(fresh), exhaustive=True)
    q = "SELECT dedup FROM messages ORDER BY dedup"
    assert rows(cfg(m).db, q) == rows(cfg(fresh).db, q)


def test_older_backups_fill_only_the_gap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    big_mode(monkeypatch)
    m = matter(tmp_path, since="2026-01-01")
    b = m / "backups"
    s, mm = history(120)
    # The newest backup lost its early history; an old one still has it;
    # a middle one adds nothing the other two lack.
    sms_file(b / "sms-20260502000000.xml", s[60:], mm[60:], ms(2026, 5, 2))
    sms_file(b / "sms-20260401000000.xml", s[30:90], mm[30:90], ms(2026, 4, 1))
    sms_file(b / "sms-20260301000000.xml", s[:70], mm[:70], ms(2026, 3, 13))
    results = {r.path.name: r for r in ps.ingest(cfg(m))}
    assert rows(cfg(m).db, "SELECT COUNT(*) FROM messages") == [(240,)]
    assert results["sms-20260401000000.xml"].status == "covered"
    assert results["sms-20260401000000.xml"].added == 0
    # The old backup was read only up to where the newest one begins.
    old = results["sms-20260301000000.xml"]
    assert old.added == 120
    stats = ps.stats(ps.connect(cfg(m).db))
    assert stats["coverage"]["sms"][0][0] == "2026-01-02"


def test_out_of_order_backup_is_reread_in_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big_mode(monkeypatch)
    m = matter(tmp_path)
    b = m / "backups"
    s, mm = history(60)
    sms_file(b / "sms-20260301000000.xml", s[:40], mm[:40], ms(2026, 2, 11))
    ps.ingest(cfg(m))
    shuffled = s[:]
    random.Random(7).shuffle(shuffled)
    sms_file(b / "sms-20260302000000.xml", shuffled, mm, ms(2026, 3, 2))
    (res,) = ps.ingest(cfg(m))
    assert "out of date order" in res.note and res.ordered is False
    assert rows(cfg(m).db, "SELECT COUNT(*) FROM messages") == [(120,)]


# --- search ----------------------------------------------------------------


def ingested(tmp_path: Path) -> sqlite3.Connection:
    m = matter(tmp_path)
    basic_backups(m)
    ps.ingest(cfg(m))
    return ps.connect(cfg(m).db)


def test_text_search_is_indexed_substring(tmp_path: Path) -> None:
    conn = ingested(tmp_path)
    if ps.get_meta(conn, "fts_tokenizer") == "trigram":
        plan = " ".join(
            str(r[3])
            for r in conn.execute(
                "EXPLAIN QUERY PLAN SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?",
                ('"ello"',),
            )
        )
        assert "VIRTUAL TABLE INDEX" in plan
    hits = ps.search(conn, ps.Query(text="ELLO FR"))  # mid-word, any case
    assert [h["body"] for h in hits["messages"]] == ["Hello from the Fixture"]
    assert hits["calls"] == []  # text queries search messages only
    assert [h["body"] for h in ps.search(conn, ps.Query(text="picture"))["messages"]] == [
        "group picture caption"
    ]
    assert len(ps.search(conn, ps.Query(text="re"))["messages"]) >= 1  # short: LIKE fallback


def test_number_window_and_kind_filters(tmp_path: Path) -> None:
    conn = ingested(tmp_path)
    by_pat = ps.search(conn, ps.Query(numbers=["(555) 000-1234"]))
    assert len(by_pat["messages"]) == 3  # two sms + the group mms
    assert len(by_pat["calls"]) == 2
    only_sam = ps.search(conn, ps.Query(numbers=["5550005678"], kind="mms"))
    assert len(only_sam["messages"]) == 2 and only_sam["calls"] == []
    window = ps.search(conn, ps.Query(numbers=[PAT], date_from="2026-02-02", date_to="2026-02-02"))
    assert [m["body"][:5] for m in window["messages"]] == ["reply"]
    assert [c["direction"] for c in window["calls"]] == ["missed"]


def test_cli_reports_are_citable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    m = matter(tmp_path)
    basic_backups(m)
    assert ps.main(["ingest", str(m), "-q"]) == 0
    assert ps.main(["search", str(m), "--number", PAT]) == 0
    md = capsys.readouterr().out
    assert "MACHINE EXTRACT" in md
    assert "Result: 2 calls, 3 messages" in md
    assert "> group picture caption" in md
    assert "[attachment: image/jpeg photo.jpg, 2048 bytes, not extracted]" in md
    assert "sms: 2026-01-01 to 2026-03-01" in md  # coverage declared
    assert ps.main(["search", str(m), "--text", "hello", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["banner"].startswith("**MACHINE EXTRACT") and len(data["messages"]) == 1
    assert ps.main(["stats", str(m)]) == 0
    out = capsys.readouterr().out
    assert "messages: 2 mms, 3 sms" in out and "calls: 3" in out


def test_sources_are_read_only(tmp_path: Path) -> None:
    m = matter(tmp_path)
    basic_backups(m)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (m / "backups").iterdir()}
    ps.ingest(cfg(m))
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (m / "backups").iterdir()}
    assert before == after
