#!/usr/bin/env python3
"""Convert a text-message TSV dump into a cleanly formatted exhibit PDF.

Usage:
    python tsv_to_exhibit.py input.tsv output.pdf [--title TITLE] [--me NAME] [--them NAME] [--after DATE] [--before DATE]

The TSV format is: timestamp<TAB>sender<TAB>recipient<TAB>message
where sender/recipient is either "me" or a phone number.

Options:
    --title   Heading printed at the top of the first page.
    --me      Display name for "me" (default: "Jane Roe").
    --them    Display name for the phone number (default: the phone number).
    --after   Only include messages on or after this date (YYYY-MM-DD or "Mon DD, YYYY").
    --before  Only include messages on or before this date.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 72
FONT_DIR = Path(__file__).resolve().parent / "fonts"

FONT_NAME = "CenturySchoolbook"
FONT_NAME_BOLD = "CenturySchoolbook-Bold"

for name, filename in [
    ("CenturySchoolbook", "texgyreschola-regular.ttf"),
    ("CenturySchoolbook-Bold", "texgyreschola-bold.ttf"),
]:
    path = FONT_DIR / filename
    if path.exists():
        pdfmetrics.registerFont(TTFont(name, str(path)))

SIZE = 10
SIZE_HEADER = 12
LEADING = 14
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN
MSG_INDENT = 18


def parse_tsv(path: Path) -> List[Tuple[str, str, str, str]]:
    rows: List[Tuple[str, str, str, str]] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.rstrip("\n\r")
            if not line:
                continue
            parts = line.split("\t", 3)
            if len(parts) < 4:
                # A malformed row silently shrinking an evidence exhibit is
                # an evidence-completeness hazard: warn loudly, keep going.
                print(
                    f"WARNING: {path.name} line {lineno}: expected 4 "
                    f"tab-separated fields, got {len(parts)} — row skipped: "
                    f"{line[:60]!r}",
                    file=sys.stderr,
                )
                continue
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def parse_date_filter(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def msg_timestamp(ts_str: str) -> Optional[datetime]:
    for fmt in ("%b %d, %Y %I:%M:%S %p", "%B %d, %Y %I:%M:%S %p",
                "%b %d, %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except ValueError:
            continue
    return None


def wrap_text(text: str, max_width: float, font_name: str, font_size: float) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        trial = current + " " + word
        if pdfmetrics.stringWidth(trial, font_name, font_size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def build_pdf(rows: List[Tuple[str, str, str, str]], output: Path,
              title: str, me_name: str, them_name: Optional[str],
              after: Optional[datetime], before: Optional[datetime]) -> None:
    c = canvas.Canvas(str(output), pagesize=letter)
    c.setTitle(title)

    phone_number: Optional[str] = None
    for _, sender, recip, _ in rows:
        if sender != "me":
            phone_number = sender
            break
        if recip != "me":
            phone_number = recip
            break

    display_them = them_name or phone_number or "Other Party"

    y = PAGE_HEIGHT - MARGIN

    def new_page() -> float:
        c.showPage()
        return PAGE_HEIGHT - MARGIN

    # Title
    c.setFont(FONT_NAME_BOLD, SIZE_HEADER)
    c.drawString(MARGIN, y, title)
    y -= LEADING * 2

    for ts_str, sender, recip, msg in rows:
        ts = msg_timestamp(ts_str)
        if ts:
            if after and ts.date() < after.date():
                continue
            if before and ts.date() > before.date():
                continue

        if sender == "me":
            label = f"[{ts_str}] {me_name}:"
        else:
            label = f"[{ts_str}] {display_them}:"

        # Check if we need a new page for at least the label + one line
        if y < MARGIN + LEADING * 3:
            y = new_page()

        c.setFont(FONT_NAME_BOLD, SIZE)
        c.drawString(MARGIN, y, label)
        y -= LEADING

        c.setFont(FONT_NAME, SIZE)
        wrapped = wrap_text(msg, TEXT_WIDTH - MSG_INDENT, FONT_NAME, SIZE)
        for wline in wrapped:
            if y < MARGIN + LEADING:
                y = new_page()
                c.setFont(FONT_NAME, SIZE)
            c.drawString(MARGIN + MSG_INDENT, y, wline)
            y -= LEADING

        y -= LEADING * 0.3

    c.save()
    print(f"Wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert TSV text messages to exhibit PDF.")
    parser.add_argument("input_tsv", help="Path to TSV file")
    parser.add_argument("output_pdf", help="Path to output PDF")
    parser.add_argument("--title", default="Text Messages", help="Document title")
    parser.add_argument("--me", default="Jane Roe", help="Display name for 'me'")
    parser.add_argument("--them", default=None, help="Display name for the other party")
    parser.add_argument("--after", default=None, help="Only messages on/after this date")
    parser.add_argument("--before", default=None, help="Only messages on/before this date")
    args = parser.parse_args()

    rows = parse_tsv(Path(args.input_tsv))
    after = parse_date_filter(args.after) if args.after else None
    before = parse_date_filter(args.before) if args.before else None

    build_pdf(rows, Path(args.output_pdf), args.title, args.me, args.them, after, before)


if __name__ == "__main__":
    main()
