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
from dataclasses import replace
from pathlib import Path

import fitz

from .base import Slot, SlotRole

# A word that is nothing but underscores, once trailing punctuation is
# removed: text extraction hands back "_______," as a single word when a
# blank is followed immediately by a comma.
_BLANK_RE = re.compile(r"^_{3,}$")

# A two-digit-year blank prints its own century: "20___". It is not all
# underscores, so it is invisible to _BLANK_RE --- and being invisible is
# not harmless. In the whereof clause it sits between the month and the
# location, so skipping it shifted every later blank up by one and put a
# two-digit year into the *location* blank. A blank that cannot be seen
# is worse than one that cannot be filled.
_YEAR_BLANK_RE = re.compile(r"^(?:19|20)_{2,}$")

# The signature rule is much longer than any date blank, which is what
# distinguishes it without having to count exact underscores --- those
# are a typography decision and may reasonably be retuned.
_RULE_MIN_UNDERSCORES = 30

_EXECUTED_RE = re.compile(r"\bExecuted this\b.*\bday of\b", re.I)
_WHEREOF_RE = re.compile(r"\bIN WITNESS WHEREOF\b", re.I)
_DATED_RE = re.compile(r"^Dated:\s*_{3,}", re.I)

# A date clause and the roles its blanks take, in printed order. Matching
# is per *clause*, not per line, because a clause wraps: the whereof
# clause runs onto a second line, which is why an earlier line-at-a-time
# version found its signature rule and none of its four date blanks --- it
# would have signed a will and left it undated.
_CLAUSES: tuple[tuple[re.Pattern[str], tuple[SlotRole, ...]], ...] = (
    # "Executed this ___ day of ______, 2026, at Reno, Nevada."
    # Year and location are printed from front matter, so only two blanks.
    (_EXECUTED_RE, (SlotRole.DAY_ORDINAL, SlotRole.MONTH_NAME)),
    # "IN WITNESS WHEREOF, I, NAME, sign this Will on this ___ day of
    #  _______, 20___, at ____________."  Four blanks, and the year is
    # two-digit because the clause prints its own "20".
    (
        _WHEREOF_RE,
        (
            SlotRole.DAY_ORDINAL,
            SlotRole.MONTH_NAME,
            SlotRole.YEAR_TWO_DIGIT,
            SlotRole.LOCATION,
        ),
    ),
)

# Titles printed beneath a judicial officer's signature rule. A judge
# block is "Dated: ____" + rule + title, so its date line is textually
# identical to a filer's --- the title is the only thing that tells them
# apart.
_JUDICIAL_TITLE_RE = re.compile(
    r"^(?:HON\.|HONORABLE\b|JUDGE\b|COMMISSIONER\b|JUDICIAL OFFICER\b|"
    r"JUDGE PRO TEM\b|REFEREE\b)", re.I
)

# How far below a slot a judicial title may sit and still claim it. The
# judge block spans about four lines at 12pt double-spaced.
_JUDICIAL_REACH_PT = 72.0

# Printed labels beneath the signature line on Judicial Council forms.
# A flattened form has no widgets, so the label is the only anchor left.
#
# "(TYPE OR PRINT NAME)" is deliberately absent: it labels a blank that
# wants the name in ordinary type, and drawing a cursive mark there would
# put a second signature where a legible name belongs.
# Ordered longest-first and matched with rect dedup below: some Judicial
# Council blanks print the bare word "SIGNATURE" --- no parentheses, no
# OF-phrase --- and the bare word is a substring of every longer label,
# so an undeduped search would emit two slots for one line.
_JC_SIGNATURE_LABELS = (
    "(SIGNATURE OF ATTORNEY OR PARTY WITHOUT ATTORNEY)",
    "(SIGNATURE OF DECLARANT)",
    "(SIGNATURE OF PARTY)",
    "(SIGNATURE)",
    "SIGNATURE",
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
    """Whether a word is a fillable blank of any shape."""
    stripped = word.strip(" .,;:")
    return bool(_BLANK_RE.match(stripped) or _YEAR_BLANK_RE.match(stripped))


def _is_plain_blank(word: str) -> bool:
    return bool(_BLANK_RE.match(word.strip(" .,;:")))


def _blank_boxes(line: list[tuple]) -> list[tuple[float, float, float, float]]:
    """Every blank on the line, left to right as printed.

    Order is what the clause mapping relies on, so this sorts by x rather
    than trusting word index --- a wrapped clause is still one line to
    PyMuPDF's grouping, but justified text can hand words back out of
    visual order.
    """
    boxes = [(w[0], w[1], w[2], w[3]) for w in line if _is_blank(w[4])]
    return sorted(boxes, key=lambda b: b[0])


def _is_rule(line: list[tuple]) -> bool:
    return (
        len(line) == 1
        and _is_plain_blank(line[0][4])
        and line[0][4].count("_") >= _RULE_MIN_UNDERSCORES
    )


def normalise_name(name: str) -> str:
    """A name reduced for comparison: upper case, no punctuation.

    Comparison is exact after this, never fuzzy. A near-match rule would
    make "ANDREW CONE" match "ANDREA CONE", and the cost of a false
    positive here is a signature on the wrong person's line --- so an
    unrecognised name fails loudly instead.
    """
    return " ".join(re.sub(r"[.,]", "", name).upper().split())


def _owner_below(lines: list[list[tuple]], start: int) -> str:
    """The name or title printed under a signature rule.

    A signature block is rule + name (+ role), so the first line of real
    text below the rule names whose block it is. This is what tells a
    four-party stipulation apart: the rules are identical, the names are
    not.
    """
    for k in range(start + 1, min(start + 4, len(lines))):
        text = " ".join(w[4] for w in lines[k]).strip()
        if not text or _is_rule(lines[k]):
            continue
        if _blank_boxes(lines[k]):
            # Another block's date line: this rule had no name under it.
            return ""
        return text
    return ""


def discover(pdf: Path) -> list[Slot]:
    """Every signature-block blank in the document, in page order.

    Slots belonging to a judicial officer are returned too, flagged
    `for_signer=False`, rather than dropped: an inventory that silently
    omitted them would make a proposed order look like it had no
    signature area at all.
    """
    found: list[Slot] = []
    with fitz.open(pdf) as doc:
        for pno, page in enumerate(doc):
            lines = _lines(page)
            page_slots: list[Slot] = []
            # Date blanks seen since the last rule. A "Dated: ___" line
            # belongs to the block whose rule follows it, so attribution
            # has to wait until that rule names its owner.
            pending: list[int] = []
            i = 0
            while i < len(lines):
                line = lines[i]
                text = " ".join(w[4] for w in line).strip()

                if _is_rule(line):
                    owner = _owner_below(lines, i)
                    judicial = bool(_JUDICIAL_TITLE_RE.match(owner))
                    page_slots.append(
                        Slot(pno, SlotRole.SIGNATURE_MARK,
                             _blank_boxes(line)[0], text,
                             for_signer=not judicial,
                             belongs_to=owner)
                    )
                    for idx in pending:
                        page_slots[idx] = replace(
                            page_slots[idx],
                            for_signer=not judicial,
                            belongs_to=owner,
                        )
                    pending = []
                    i += 1
                    continue

                clause = next(
                    (roles for rx, roles in _CLAUSES if rx.search(text)), None
                )
                if clause:
                    # Gather blanks across the clause's own lines, in
                    # printed order, stopping at the signature rule.
                    boxes: list[tuple[float, float, float, float]] = []
                    j = i
                    while j < len(lines) and len(boxes) < len(clause):
                        if j > i and _is_rule(lines[j]):
                            break
                        boxes += _blank_boxes(lines[j])
                        j += 1
                    for role, box in zip(clause, boxes):
                        pending.append(len(page_slots))
                        page_slots.append(Slot(pno, role, box, text))
                    i = max(j, i + 1)
                    continue

                if _DATED_RE.match(text):
                    boxes = _blank_boxes(line)
                    if boxes:
                        pending.append(len(page_slots))
                        page_slots.append(
                            Slot(pno, SlotRole.DATE_FULL, boxes[0], text)
                        )
                i += 1

            found += page_slots

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
            claimed: list[fitz.Rect] = []
            for label in _JC_SIGNATURE_LABELS:
                for rect in page.search_for(label):
                    if any(rect.intersects(c) for c in claimed):
                        continue  # substring of a longer label already taken
                    claimed.append(fitz.Rect(rect))
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
        owner = s.belongs_to or "(unattributed)"
        never = "" if s.for_signer else "  NEVER SIGNED HERE"
        out.append(
            f"  p{s.page + 1}  {s.role.value:<15} {owner:<28}{never}"
        )
    return "\n".join(out)
