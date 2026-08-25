"""Finding the blanks on a built PDF that signing fills in.

Discovery reads the *printed* page rather than relying on the renderer to
leave markers behind. That is a deliberate choice with a practical
payoff: it works on any PDF the pipeline produced, including old ones and
including flattened Judicial Council forms, where `technology: overlay`
has already removed every widget annotation (ADR-0033) so there is no
form field left to interrogate.

An earlier design emitted invisible marker text at each slot, in PDF text
rendering mode 3, for a later pass to locate. It was abandoned because
invisible text is still selectable and still appears in `pdftotext`
output: a select-all on a filed pleading would have pasted the markers.
The signature blocks already print distinctive, stable text --- an
underscore run in a known sentence --- so nothing needs to be hidden in
the file to find them.

The sentences come from `pleading/md_pleading.py`:

    Executed this _____ day of _________________, 2026, at Reno, Nevada.
    Dated: _________________________
    ____________________________________          (the signature rule)

If those strings change there, the patterns here must change with them,
and `tests/test_signing_slots.py` builds a real pleading to catch the
drift rather than trusting the two files to stay in step.
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from .base import Slot, SlotRole

# A word that is nothing but underscores, once trailing punctuation is
# removed: text extraction hands back "_______," as a single word when a
# blank is followed immediately by a comma.
_BLANK_RE = re.compile(r"^_{3,}$")

# The signature rule is much longer than any date blank, which is what
# distinguishes it without having to count exact underscores --- those
# are a typography decision and may reasonably be retuned.
_RULE_MIN_UNDERSCORES = 30

_EXECUTED_RE = re.compile(r"\bExecuted this\b.*\bday of\b", re.I)
_DATED_RE = re.compile(r"^Dated:\s*_{3,}", re.I)

# Printed labels beneath the signature line on Judicial Council forms.
# A flattened form has no widgets, so the label is the only anchor left.
#
# "(TYPE OR PRINT NAME)" is deliberately absent: it labels a blank that
# wants the name in ordinary type, and drawing a cursive mark there would
# put a second signature where a legible name belongs.
_JC_SIGNATURE_LABELS = (
    "(SIGNATURE OF ATTORNEY OR PARTY WITHOUT ATTORNEY)",
    "(SIGNATURE OF DECLARANT)",
    "(SIGNATURE OF PARTY)",
    "(SIGNATURE)",
)


def _lines(page: fitz.Page) -> list[list[tuple]]:
    """Words grouped into rendered lines, in reading order.

    PyMuPDF returns (x0, y0, x1, y1, word, block_no, line_no, word_no);
    grouping on (block_no, line_no) reconstructs the line as laid out,
    which is what the sentence patterns match against.
    """
    words = page.get_text("words")
    grouped: dict[tuple[int, int], list[tuple]] = {}
    for w in words:
        grouped.setdefault((w[5], w[6]), []).append(w)
    return [sorted(v, key=lambda w: w[7]) for _, v in sorted(grouped.items())]


def _is_blank(word: str) -> bool:
    return bool(_BLANK_RE.match(word.strip(" .,;:")))


def _blank_boxes(line: list[tuple]) -> list[tuple[float, float, float, float]]:
    return [(w[0], w[1], w[2], w[3]) for w in line if _is_blank(w[4])]


def discover(pdf: Path) -> list[Slot]:
    """Every signature-block blank in the document, in page order."""
    found: list[Slot] = []
    with fitz.open(pdf) as doc:
        for pno, page in enumerate(doc):
            for line in _lines(page):
                text = " ".join(w[4] for w in line).strip()
                boxes = _blank_boxes(line)

                # The signature rule: a line that is one long blank and
                # nothing else.
                if len(line) == 1 and _is_blank(line[0][4]):
                    if line[0][4].count("_") >= _RULE_MIN_UNDERSCORES:
                        found.append(
                            Slot(pno, SlotRole.SIGNATURE_MARK, boxes[0], text)
                        )
                        continue

                # "Executed this ___ day of _______, YEAR, at PLACE."
                # Two blanks, in order: ordinal day, then month name. The
                # year and location are already printed.
                if _EXECUTED_RE.search(text) and len(boxes) >= 2:
                    found.append(Slot(pno, SlotRole.DAY_ORDINAL, boxes[0], text))
                    found.append(Slot(pno, SlotRole.MONTH_NAME, boxes[1], text))
                    continue

                # "Dated: ______" takes the whole date, deliberately, so
                # a December build signed in January is not wrong.
                if _DATED_RE.match(text) and boxes:
                    found.append(Slot(pno, SlotRole.DATE_FULL, boxes[0], text))
                    continue

    return found


def jc_signature_lines(pdf: Path) -> list[Slot]:
    """Signature rules on flattened Judicial Council forms.

    Located by the printed label *underneath* the line, since a flattened
    form has no widget to ask. The rule sits immediately above the label,
    so the slot is synthesised from the label's own box: same horizontal
    extent, a line's height above it.
    """
    found: list[Slot] = []
    with fitz.open(pdf) as doc:
        for pno, page in enumerate(doc):
            for label in _JC_SIGNATURE_LABELS:
                for rect in page.search_for(label):
                    height = 12.0
                    found.append(
                        Slot(
                            pno,
                            SlotRole.SIGNATURE_MARK,
                            (rect.x0, rect.y0 - height, rect.x1, rect.y0 - 1.0),
                            label,
                        )
                    )
    return found


def describe(slots: list[Slot]) -> str:
    """Human-readable inventory, for `sc sign --slots`."""
    if not slots:
        return "no signature slots found"
    out = []
    for s in slots:
        x0, y0, x1, y1 = (round(v, 1) for v in s.rect)
        out.append(
            f"  p{s.page + 1}  {s.role.value:<15} "
            f"[{x0}, {y0}, {x1}, {y1}]  {s.anchor[:58]}"
        )
    return "\n".join(out)
