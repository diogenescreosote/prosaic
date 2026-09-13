"""A per-message index of the mail record.

The gmail connector stores each thread as one mbox and renders it to one
PDF named for the thread's FIRST message (`20251111_intake_form.pdf`).
A message sent on November 18 in a thread that began November 11 is
therefore invisible to any lookup by its own date: nothing in the record
carries the date of the message, only the date of the thread.

This module reads every stored mbox and writes `derived/mail/messages.tsv`
(one row per message: date, time, from, to, cc, subject, thread stem,
message number, attachment count, snippet) and a Markdown twin grouped
by month, so that "what did X write in mid-November" is one grep, and
`sc find` sees the message dates too. It is a pure function of the mbox
files; rerun it any time.
"""

from __future__ import annotations

import csv
import email
import email.utils
import mailbox
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC
from html import unescape
from pathlib import Path

SNIPPET_CHARS = 300

_QUOTE_HEAD_RE = re.compile(r"(?:^|\n)On .{0,200}?wrote:", re.S)
_BOILERPLATE_RE = re.compile(
    r"(CONFIDENTIALITY NOTICE|The information contained in this (?:transmission|e-?mail)|"
    r"This (?:e-?mail|message|communication)(?:,| and any attachments)? (?:is|may|contains?)|"
    r"Please consider the environment)",
    re.I,
)
_FORWARD_RE = re.compile(r"^-{3,}\s*Forwarded message\s*-{3,}", re.M)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class Row:
    date: str  # YYYY-MM-DD, local to the sender's offset
    time: str  # HH:MM
    sender: str
    to: str
    cc: str
    subject: str
    thread: str  # mbox stem = the rendered PDF stem
    n: int  # 1-based position in the thread
    attachments: int
    snippet: str

    def as_list(self) -> list[str]:
        return [
            self.date,
            self.time,
            self.sender,
            self.to,
            self.cc,
            self.subject,
            self.thread,
            str(self.n),
            str(self.attachments),
            self.snippet,
        ]


HEADER = ["date", "time", "from", "to", "cc", "subject", "thread", "msg", "attachments", "snippet"]


def _addr(value: str | None) -> str:
    if not value:
        return ""
    parts = email.utils.getaddresses([value])
    out = []
    for name, addr in parts:
        name = name.strip().strip('"')
        out.append(f"{name} <{addr}>" if name and addr else (addr or name))
    return "; ".join(out)


def _body_text(msg: email.message.Message) -> str:
    plain, html = "", ""
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            payload = None
        if not isinstance(payload, bytes) or not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not html:
            html = text
    if plain.strip():
        return plain
    if html:
        html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        html = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", html)
        return unescape(_TAG_RE.sub(" ", html))
    return ""


def snippet(text: str, limit: int = SNIPPET_CHARS) -> str:
    """The message's own words: quoted reply chains, forwarded blocks and
    signature boilerplate cut, whitespace folded, first `limit` chars."""
    text = text.replace("\r", "").replace("\ufeff", "")
    for cut in (_QUOTE_HEAD_RE, _FORWARD_RE, _BOILERPLATE_RE):
        m = cut.search(text)
        if m:
            text = text[: m.start()]
    lines = [ln for ln in text.split("\n") if not ln.lstrip().startswith(">")]
    text = _WS_RE.sub(" ", " ".join(lines)).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _count_attachments(msg: email.message.Message) -> int:
    return sum(1 for p in msg.walk() if p.get_content_disposition() == "attachment")


def _local_date_time(value: str | None) -> tuple[str, str]:
    if not value:
        return "", ""
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return "", ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def rows_for_mbox(path: Path) -> Iterator[Row]:
    box = mailbox.mbox(str(path))
    for i, msg in enumerate(box, start=1):
        date, time = _local_date_time(msg.get("Date"))
        yield Row(
            date=date,
            time=time,
            sender=_addr(msg.get("From")),
            to=_addr(msg.get("To")),
            cc=_addr(msg.get("Cc")),
            subject=_WS_RE.sub(" ", str(msg.get("Subject") or "")).strip(),
            thread=path.stem,
            n=i,
            attachments=_count_attachments(msg),
            snippet=snippet(_body_text(msg)),
        )


def build(
    matter: Path, mbox_dir: Path | None = None, out_dir: Path | None = None
) -> tuple[Path, Path, int]:
    mbox_dir = mbox_dir or matter / "assets" / "gmail" / "mbox"
    out_dir = out_dir or matter / "derived" / "mail"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[Row] = []
    for mb in sorted(mbox_dir.glob("*.mbox")):
        try:
            rows.extend(rows_for_mbox(mb))
        except Exception as exc:  # a corrupt mbox must not sink the index
            print(f"mail-index: skipping {mb.name}: {exc}", file=sys.stderr)
    rows.sort(key=lambda r: (r.date, r.time, r.thread, r.n))
    tsv = out_dir / "messages.tsv"
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(HEADER)
        for r in rows:
            w.writerow(r.as_list())
    md = out_dir / "messages.md"
    md.write_text(render_markdown(rows), encoding="utf-8")
    return tsv, md, len(rows)


def render_markdown(rows: list[Row]) -> str:
    out = [
        "# Mail record, one row per message",
        "",
        "Generated by `sc mail-index` from `assets/gmail/mbox/`; regenerate, never edit. "
        "Each row is one message with ITS OWN date; the thread column is the rendered "
        "PDF's stem (`assets/gmail/<thread>.pdf`, text at "
        "`derived/text/assets/gmail/<thread>.pdf.txt`), "
        "which is named for the thread's first message and may be weeks earlier.",
        "",
        f"{len(rows)} messages.",
        "",
    ]
    month = None
    for r in rows:
        m = r.date[:7] if r.date else "undated"
        if m != month:
            month = m
            out += [f"## {month}", ""]
        att = f" [{r.attachments} att]" if r.attachments else ""
        out.append(
            f"- **{r.date} {r.time}** {r.sender} → {r.to}"
            + (f" (cc {r.cc})" if r.cc else "")
            + f" · *{r.subject}* · `{r.thread}` #{r.n}{att}"
            + (f" — {r.snippet}" if r.snippet else "")
        )
    out.append("")
    return "\n".join(out)


def _matches(
    r: Row, sender: str | None, after: str | None, before: str | None, grep: re.Pattern[str] | None
) -> bool:
    if sender and sender.lower() not in r.sender.lower():
        return False
    if after and r.date < after:
        return False
    if before and r.date > before:
        return False
    return True


def _full_body(matter: Path, thread: str, n: int, cache: dict[str, list[str]]) -> str:
    """The whole text of message n of a thread, from the mbox, cached per thread."""
    if thread not in cache:
        mb = matter / "assets" / "gmail" / "mbox" / f"{thread}.mbox"
        try:
            cache[thread] = [_body_text(m) for m in mailbox.mbox(str(mb))]
        except Exception:
            cache[thread] = []
    bodies = cache[thread]
    return bodies[n - 1] if 0 < n <= len(bodies) else ""


def search(
    matter: Path,
    sender: str | None = None,
    after: str | None = None,
    before: str | None = None,
    grep: str | None = None,
) -> list[Row]:
    tsv = matter / "derived" / "mail" / "messages.tsv"
    if not tsv.exists():
        build(matter)
    pat = re.compile(grep, re.I) if grep else None
    cache: dict[str, list[str]] = {}
    out: list[Row] = []
    with tsv.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader, None)
        for cells in reader:
            if len(cells) != len(HEADER):
                continue
            r = Row(
                cells[0],
                cells[1],
                cells[2],
                cells[3],
                cells[4],
                cells[5],
                cells[6],
                int(cells[7]),
                int(cells[8]),
                cells[9],
            )
            if not _matches(r, sender, after, before, pat):
                continue
            if pat and not pat.search(
                " ".join([r.subject, r.to, r.cc, _full_body(matter, r.thread, r.n, cache)])
            ):
                continue
            out.append(r)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="per-message index of the stored mail")
    ap.add_argument("matter_dir", nargs="?", default=".")
    ap.add_argument("--from", dest="sender", help="substring of the sender")
    ap.add_argument("--after", help="YYYY-MM-DD, inclusive")
    ap.add_argument("--before", help="YYYY-MM-DD, inclusive")
    ap.add_argument("--grep", help="regex over subject and snippet")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the index first")
    args = ap.parse_args(argv)
    matter = Path(args.matter_dir).resolve()
    querying = any([args.sender, args.after, args.before, args.grep])
    if args.rebuild or not querying:
        tsv, md, n = build(matter)
        print(f"mail-index: {n} messages -> {tsv.relative_to(matter)}, {md.relative_to(matter)}")
        if not querying:
            return 0
    for r in search(matter, args.sender, args.after, args.before, args.grep):
        print(
            f"{r.date} {r.time}  {r.sender}  {r.subject}  [{r.thread} #{r.n}]"
            + (f"\n    {r.snippet}" if r.snippet else "")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
