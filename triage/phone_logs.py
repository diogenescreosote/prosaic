#!/usr/bin/env python3
"""Extract call/SMS traffic with a phone number from SMS Backup & Restore XML.

Reads the `calls-*.xml` and `sms-*.xml` files the SMS Backup & Restore
app produces, filters to one or more phone numbers (and optionally a
date window), de-duplicates across overlapping daily backups, and
emits a chronological markdown report. Spec: specs/phone-logs.md.

Usage:
    python3 triage/phone_logs.py -n +17075551234 \
        [--after 2026-04-01] [--before 2026-08-22] \
        [--kind calls|sms|both] [-o report.md] <file-or-dir> [...]

Parsing is streaming (xml.etree.iterparse with element clearing), so a
multi-gigabyte sms backup is fine. Sources are never modified; MMS
attachments are noted by MIME type, never decoded.
"""

import argparse
import datetime
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CALL_TYPES = {
    "1": "incoming",
    "2": "outgoing",
    "3": "missed",
    "4": "voicemail",
    "5": "rejected",
    "6": "blocked",
}
SMS_TYPES = {
    "1": "received",
    "2": "sent",
    "3": "draft",
    "4": "outbox",
    "5": "failed",
    "6": "queued",
}
MMS_BOXES = {"1": "received", "2": "sent"}

BANNER = (
    "**MACHINE EXTRACT — VERIFY AGAINST THE SOURCE BACKUP "
    "BEFORE CITING IN ANY FILING**"
)


def normalize_number(raw):
    """Digits only; a US 11-digit number loses its leading 1."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def numbers_match(a, b):
    """Format-blind comparison: last ten digits for full-length
    numbers, exact for short codes."""
    if not a or not b:
        return False
    if len(a) >= 10 and len(b) >= 10:
        return a[-10:] == b[-10:]
    return a == b


def matches_any(number, targets):
    n = normalize_number(number)
    return any(numbers_match(n, t) for t in targets)


def parse_window(after, before):
    """Inclusive local-time bounds from YYYY-MM-DD or ISO timestamps."""
    lo = hi = None
    if after:
        lo = datetime.datetime.fromisoformat(after)
    if before:
        hi = datetime.datetime.fromisoformat(before)
        if len(before) == 10:  # bare date: include the whole day
            hi = hi + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
    return lo, hi


def in_window(ms, lo, hi):
    when = datetime.datetime.fromtimestamp(int(ms) / 1000.0)
    if lo and when < lo:
        return False
    if hi and when > hi:
        return False
    return True


def _mms_participants(elem):
    addrs = [
        (a.get("address"), a.get("type"))
        for a in elem.iter("addr")
        if a.get("address")
    ]
    if not addrs:
        addrs = [(part, None) for part in (elem.get("address") or "").split("~") if part]
    return addrs


def _mms_content(elem):
    texts, attachments = [], []
    for part in elem.iter("part"):
        ct = part.get("ct") or "unknown"
        if ct == "application/smil":
            continue
        if ct.startswith("text/"):
            if part.get("text") not in (None, "null"):
                texts.append(part.get("text"))
        else:
            attachments.append(ct)
    return "\n".join(texts), attachments


def scan_file(path, targets, lo, hi, records, seen, stats):
    """Stream one backup file, appending matching records."""
    context = ET.iterparse(str(path), events=("start", "end"))
    _, root = next(context)
    stats.setdefault("sources", []).append(
        (Path(path).name, root.get("count"), root.tag)
    )
    for event, elem in context:
        if event != "end" or elem.tag not in ("call", "sms", "mms"):
            continue
        if elem.tag == "call":
            number = elem.get("number")
            if matches_any(number, targets) and in_window(elem.get("date"), lo, hi):
                stats["raw"] = stats.get("raw", 0) + 1
                key = (
                    "call",
                    elem.get("date"),
                    normalize_number(number),
                    elem.get("type"),
                    elem.get("duration"),
                )
                if key not in seen:
                    seen.add(key)
                    records.append(
                        {
                            "kind": "call",
                            "ms": int(elem.get("date")),
                            "direction": CALL_TYPES.get(
                                elem.get("type"), "type=%s" % elem.get("type")
                            ),
                            "duration": int(elem.get("duration") or 0),
                            "number": number,
                            "contact": elem.get("contact_name"),
                        }
                    )
        elif elem.tag == "sms":
            address = elem.get("address")
            if matches_any(address, targets) and in_window(elem.get("date"), lo, hi):
                stats["raw"] = stats.get("raw", 0) + 1
                key = (
                    "sms",
                    elem.get("date"),
                    normalize_number(address),
                    elem.get("type"),
                    elem.get("body"),
                )
                if key not in seen:
                    seen.add(key)
                    records.append(
                        {
                            "kind": "message",
                            "ms": int(elem.get("date")),
                            "direction": SMS_TYPES.get(
                                elem.get("type"), "type=%s" % elem.get("type")
                            ),
                            "number": address,
                            "contact": elem.get("contact_name"),
                            "body": elem.get("body") or "",
                            "attachments": [],
                        }
                    )
        else:  # mms
            participants = _mms_participants(elem)
            if any(matches_any(addr, targets) for addr, _ in participants) and in_window(
                elem.get("date"), lo, hi
            ):
                stats["raw"] = stats.get("raw", 0) + 1
                text, attachments = _mms_content(elem)
                key = (
                    "mms",
                    elem.get("date"),
                    tuple(sorted(normalize_number(a) for a, _ in participants)),
                    elem.get("msg_box"),
                    text,
                )
                if key not in seen:
                    seen.add(key)
                    others = [
                        a for a, _ in participants if matches_any(a, targets)
                    ]
                    records.append(
                        {
                            "kind": "message",
                            "ms": int(elem.get("date")),
                            "direction": MMS_BOXES.get(
                                elem.get("msg_box"),
                                "msg_box=%s" % elem.get("msg_box"),
                            ),
                            "number": others[0] if others else elem.get("address"),
                            "contact": elem.get("contact_name"),
                            "body": text,
                            "attachments": attachments,
                            "group": len(participants) > 2,
                        }
                    )
        root.clear()


def fmt_when(ms):
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")


def fmt_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return "%dh %dm %ds" % (h, m, s)
    if m:
        return "%dm %ds" % (m, s)
    return "%ds" % s


def render(records, numbers, after, before, stats):
    records.sort(key=lambda r: (r["ms"], r["kind"]))
    calls = [r for r in records if r["kind"] == "call"]
    messages = [r for r in records if r["kind"] == "message"]

    out = []
    out.append("# Phone log extract: %s" % ", ".join(numbers))
    out.append("")
    out.append(BANNER)
    out.append("")
    out.append("- Number(s): %s" % ", ".join(numbers))
    window = "%s to %s" % (after or "(start of backup)", before or "(end of backup)")
    out.append("- Window: %s (local time, inclusive)" % window)
    out.append("- Sources:")
    for name, count, tag in stats.get("sources", []):
        out.append("  - `%s` (%s, %s records)" % (name, tag, count or "?"))
    out.append(
        "- Result: %d calls, %d messages (de-duplicated from %d matching rows)"
        % (len(calls), len(messages), stats.get("raw", 0))
    )
    out.append(
        "- Generated by `triage/phone_logs.py` from SMS Backup & Restore XML."
    )
    out.append("")

    out.append("## Calls")
    out.append("")
    if calls:
        out.append("| Date | Direction | Duration | Number | Contact |")
        out.append("|---|---|---|---|---|")
        for r in calls:
            out.append(
                "| %s | %s | %s | %s | %s |"
                % (
                    fmt_when(r["ms"]),
                    r["direction"],
                    fmt_duration(r["duration"]),
                    r["number"],
                    (r["contact"] or "").replace("|", "\\|") or "(Unknown)",
                )
            )
    else:
        out.append("No calls in the window.")
    out.append("")

    out.append("## Messages")
    out.append("")
    if messages:
        for r in messages:
            label = "%s — %s" % (fmt_when(r["ms"]), r["direction"])
            if r.get("group"):
                label += " (group)"
            out.append("**%s** (%s):" % (label, r["number"]))
            out.append("")
            body = r.get("body") or ""
            if body:
                for line in body.replace("\r\n", "\n").split("\n"):
                    out.append("> %s" % line)
            for ct in r.get("attachments", []):
                out.append("> [attachment: %s — not extracted]" % ct)
            if not body and not r.get("attachments"):
                out.append("> (empty message)")
            out.append("")
    else:
        out.append("No messages in the window.")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def gather_inputs(paths, kind):
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            if kind in ("calls", "both"):
                files.extend(sorted(p.glob("calls-*.xml")))
            if kind in ("sms", "both"):
                files.extend(sorted(p.glob("sms-*.xml")))
        else:
            files.append(p)
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Filter SMS Backup & Restore XML by phone number "
        "into a markdown report."
    )
    ap.add_argument(
        "-n",
        "--number",
        action="append",
        required=True,
        help="phone number to match (any format; repeatable)",
    )
    ap.add_argument("--after", help="inclusive start, YYYY-MM-DD or ISO timestamp")
    ap.add_argument("--before", help="inclusive end, YYYY-MM-DD or ISO timestamp")
    ap.add_argument(
        "--kind",
        choices=("calls", "sms", "both"),
        default="both",
        help="which backups to read when a directory is given (default both)",
    )
    ap.add_argument("-o", "--output", help="write report here instead of stdout")
    ap.add_argument("inputs", nargs="+", help="backup XML files or directories")
    args = ap.parse_args(argv)

    targets = [normalize_number(n) for n in args.number]
    if not all(targets):
        ap.error("a --number contains no digits")
    lo, hi = parse_window(args.after, args.before)

    files = gather_inputs(args.inputs, args.kind)
    if not files:
        ap.error("no calls-*.xml or sms-*.xml found in the given inputs")

    records, seen, stats = [], set(), {}
    for f in files:
        scan_file(f, targets, lo, hi, records, seen, stats)

    report = render(records, args.number, args.after, args.before, stats)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        sys.stderr.write(
            "wrote %s: %d records from %d file(s)\n"
            % (args.output, len(records), len(files))
        )
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
