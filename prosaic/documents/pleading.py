"""Pleading paper per CRC 2.100 through 2.119.

Letter-size pages with 28 numbered lines against a double vertical rule,
one inch of left margin and half an inch of right (CRC 2.107), text
double-spaced on the numbered lines, and a footer with the page number
and the title of the paper (CRC 2.110). The first page carries the
attorney block on lines 1 through 7, the court name centered below it
(CRC 2.111), and the two-column caption with the case number and paper
title opposite the party names.
"""

from __future__ import annotations

import datetime
import io
from dataclasses import dataclass

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN = 72.0
RIGHT_MARGIN = 36.0
TEXT_LEFT = LEFT_MARGIN + 14.0
TEXT_RIGHT = PAGE_WIDTH - RIGHT_MARGIN - 6.0
LINE_LEADING = 24.0
FIRST_LINE_Y = PAGE_HEIGHT - 76.0
LINES_PER_PAGE = 28
FONT = "Courier"
FONT_SIZE = 12.0
FOOTER_Y = 40.0


@dataclass(frozen=True, slots=True)
class Pleading:
    """The content of one court paper on pleading paper."""

    title: str
    attorney_block: tuple[str, ...]
    court_name: str
    plaintiff_caption: str
    defendant_caption: str
    case_number: str
    paragraphs: tuple[str, ...]
    signature_name: str
    signed_on: datetime.date

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("a pleading has a title; it appears in the caption and footer")
        if len(self.attorney_block) > 7:
            raise ValueError("the attorney block must fit on lines 1 through 7")


def _line_y(line: int) -> float:
    return FIRST_LINE_Y - (line - 1) * LINE_LEADING


def _wrap(text: str, width: float, canvas: Canvas) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if canvas.stringWidth(candidate, FONT, FONT_SIZE) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class _Page:
    """One sheet of numbered pleading paper being written top to bottom."""

    def __init__(self, canvas: Canvas, title: str, number: int) -> None:
        self.canvas = canvas
        self.title = title
        self.number = number
        self.line = 1
        self._rule_and_numbers()

    def _rule_and_numbers(self) -> None:
        top = _line_y(1) + LINE_LEADING / 2
        bottom = _line_y(LINES_PER_PAGE) - 6
        self.canvas.setLineWidth(0.7)
        self.canvas.line(LEFT_MARGIN, top, LEFT_MARGIN, bottom)
        self.canvas.line(LEFT_MARGIN + 4, top, LEFT_MARGIN + 4, bottom)
        self.canvas.setFont(FONT, 10)
        for index in range(1, LINES_PER_PAGE + 1):
            label = str(index)
            self.canvas.drawRightString(LEFT_MARGIN - 8, _line_y(index), label)
        self.canvas.setFont(FONT, FONT_SIZE)

    def write(self, text: str, *, x: float = TEXT_LEFT, centered: bool = False) -> None:
        y = _line_y(self.line)
        if centered:
            self.canvas.drawCentredString((TEXT_LEFT + TEXT_RIGHT) / 2, y, text)
        else:
            self.canvas.drawString(x, y, text)
        self.line += 1

    def skip(self, lines: int = 1) -> None:
        self.line += lines

    @property
    def remaining(self) -> int:
        return LINES_PER_PAGE - self.line + 1

    def finish(self) -> None:
        self.canvas.setFont(FONT, 10)
        self.canvas.drawCentredString(PAGE_WIDTH / 2, FOOTER_Y + 14, f"- {self.number} -")
        self.canvas.line(LEFT_MARGIN, FOOTER_Y + 8, PAGE_WIDTH - RIGHT_MARGIN, FOOTER_Y + 8)
        self.canvas.drawCentredString(PAGE_WIDTH / 2, FOOTER_Y - 4, self.title.upper())
        self.canvas.setFont(FONT, FONT_SIZE)
        self.canvas.showPage()


def render_pleading(pleading: Pleading) -> bytes:
    """Render to PDF bytes."""
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=letter)
    canvas.setTitle(pleading.title)
    canvas.setFont(FONT, FONT_SIZE)

    page = _Page(canvas, pleading.title, 1)
    for entry in pleading.attorney_block:
        page.write(entry)
    page.line = 8
    page.write(pleading.court_name.upper(), centered=True)
    page.skip(1)

    caption_divider = TEXT_LEFT + 240
    caption_top = page.line
    page.write(f"{pleading.plaintiff_caption.upper()},")
    page.skip(1)
    page.write("          Plaintiff,")
    page.skip(1)
    page.write("     v.")
    page.skip(1)
    page.write(f"{pleading.defendant_caption.upper()},")
    page.skip(1)
    page.write("          Defendant.")
    caption_bottom = page.line
    for line in range(caption_top, caption_bottom + 1):
        canvas.drawString(caption_divider, _line_y(line), ")")
    canvas.drawString(
        caption_divider + 18, _line_y(caption_top), f"Case No. {pleading.case_number}"
    )
    title_lines = _wrap(pleading.title.upper(), TEXT_RIGHT - caption_divider - 18, canvas)
    for offset, title_line in enumerate(title_lines):
        canvas.drawString(caption_divider + 18, _line_y(caption_top + 2 + offset), title_line)
    page.line = caption_bottom + 2

    def fresh_page() -> _Page:
        page.finish()
        return _Page(canvas, pleading.title, page.number + 1)

    for number, paragraph in enumerate(pleading.paragraphs, start=1):
        wrapped = _wrap(f"{number}.  {paragraph}", TEXT_RIGHT - TEXT_LEFT, canvas)
        for text_line in wrapped:
            if page.remaining < 1:
                page = fresh_page()
            page.write(text_line)

    signature = (
        f"Dated: {pleading.signed_on.strftime('%B %-d, %Y')}",
        "",
        "                              _______________________________",
        f"                              {pleading.signature_name}",
    )
    if page.remaining < len(signature) + 1:
        page = fresh_page()
    page.skip(1)
    for entry in signature:
        page.write(entry)
    page.finish()

    canvas.save()
    return buffer.getvalue()
