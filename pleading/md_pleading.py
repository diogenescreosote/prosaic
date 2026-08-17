#!/usr/bin/env python3
"""Convert Markdown with YAML front matter into a California-style pleading PDF.

Usage:
    python md_pleading.py input.md output.pdf
    python md_pleading.py input.md output.pdf --sign "Jane Roe"
    python md_pleading.py input.md output.pdf --sign "Jane Roe" --date 2026-03-16

Dependencies:
    - reportlab
    - pyyaml
    - pypdf
    - pillow
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import logging
import yaml

logging.getLogger("pypdf").setLevel(logging.ERROR)

from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf._page import PageObject
from reportlab.lib.colors import black, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter  # 612 x 792 pt

# ---------------------------------------------------------------------------
# Font registration
# ---------------------------------------------------------------------------

FONT_DIR = Path(__file__).resolve().parent / "fonts"

_FONT_FILES = {
    "CenturySchoolbook":            "texgyreschola-regular.ttf",
    "CenturySchoolbook-Bold":       "texgyreschola-bold.ttf",
    "CenturySchoolbook-Italic":     "texgyreschola-italic.ttf",
    "CenturySchoolbook-BoldItalic": "texgyreschola-bolditalic.ttf",
}


_SIGNATURE_FONT_FILE = "DancingScript.ttf"
SIGNATURE_FONT = "DancingScript"
SIGNATURE_FONT_SIZE = 20
_signature_font_available = False


def _register_fonts() -> None:
    global _signature_font_available
    for name, filename in _FONT_FILES.items():
        path = FONT_DIR / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Font file not found: {path}\n"
                "Place TeX Gyre Schola .ttf files in the fonts/ directory."
            )
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "CenturySchoolbook",
        normal="CenturySchoolbook",
        bold="CenturySchoolbook-Bold",
        italic="CenturySchoolbook-Italic",
        boldItalic="CenturySchoolbook-BoldItalic",
    )
    sig_path = FONT_DIR / _SIGNATURE_FONT_FILE
    if sig_path.exists():
        pdfmetrics.registerFont(TTFont(SIGNATURE_FONT, str(sig_path)))
        _signature_font_available = True


_register_fonts()

# ---------------------------------------------------------------------------
# Layout constants — California pleading style
# ---------------------------------------------------------------------------

FONT_NAME = "CenturySchoolbook"
FONT_NAME_BOLD = "CenturySchoolbook-Bold"
FONT_NAME_ITALIC = "CenturySchoolbook-Italic"
FONT_NAME_BOLD_ITALIC = "CenturySchoolbook-BoldItalic"
FONT_SIZE = 12
FONT_SIZE_SMALL = 10

LINES_PER_PAGE = 28

TOP_FIRST_LINE = PAGE_HEIGHT - 1.125 * 72       # line 1 baseline: 1.125" from top
BOTTOM_LAST_LINE = 1.125 * 72                    # line 28 baseline: 1.125" from bottom
LEADING = (TOP_FIRST_LINE - BOTTOM_LAST_LINE) / (LINES_PER_PAGE - 1)

# Letters: 1.5-spaced business-letter leading, derived lines-per-page.
# 12 pt body type at 18 pt leading = standard 1.5 spacing.
LETTER_LEADING = 18
LETTER_LINES_PER_PAGE = int((TOP_FIRST_LINE - BOTTOM_LAST_LINE) / LETTER_LEADING) + 1

LINE_RULE_X = 1.125 * 72                          # vertical rule at exactly 1.125"
LEFT_MARGIN = LINE_RULE_X + 0.25 * 72            # text begins 0.25" right of rule
RIGHT_MARGIN = 0.6 * 72                          # 0.6" from right edge
TEXT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

LETTER_LEFT_MARGIN = LEFT_MARGIN / 2
LETTER_TEXT_WIDTH = PAGE_WIDTH - LETTER_LEFT_MARGIN - RIGHT_MARGIN

LINE_NUM_X = LINE_RULE_X - 9                     # right-aligned just left of rule
LINE_RULE_TOP_OVERHANG = 6                       # rule extends above line-1 baseline
LINE_RULE_BOTTOM_OVERHANG = 12                   # ... and below line-28's
FOOTER_RULE_Y = 1.0 * 72                         # 0.125" below bottom margin
PAGE_NUM_Y = FOOTER_RULE_Y - 14
LETTER_PAGE_NUM_Y = 0.5 * 72                    # letters: page number 0.5" from bottom
FOOTER_TITLE_Y = FOOTER_RULE_Y - 26
FOOTER_TITLE_SIDE_INSET = 36                     # footer title narrower than text block (0.5" total)
FOOTER_TITLE_LEADING = FONT_SIZE_SMALL + 2       # single-spaced wrapped footer title

# The `notreal:` banner. Sits in the top margin above the line rule's
# 6pt overhang (line-1 baseline is 1.125" down), so it never competes
# with the 28-line grid.
DRAFT_BANNER_Y = PAGE_HEIGHT - 0.7 * 72
DRAFT_BANNER_FONT_SIZE = 10
DRAFT_BANNER_MIN_FONT_SIZE = 7
DRAFT_BANNER_COLOR = (0.75, 0.0, 0.0)   # red, dark enough to stay legible in grayscale
#: Height of the strip reclaimed at the top of every page for the
#: banner. A JC form has no free top margin, so the band is made by
#: scaling the page's own content down rather than drawn over it.
DRAFT_BANNER_BAND = 26

CENTER_X = PAGE_WIDTH / 2
CAPTION_LEADING = 14                              # single-spaced leading for caption elements
PAREN_X = CENTER_X - 36                           # x position for the ) column
RIGHT_COL_X = PAREN_X + 18                        # right column text starts here
RIGHT_COL_WIDTH = PAGE_WIDTH - RIGHT_MARGIN - RIGHT_COL_X
LEFT_COL_WIDTH = PAREN_X - LEFT_MARGIN - 12       # party names column width
ATTACH_MAX_W = 7.5 * 72
ATTACH_MAX_H = 10 * 72

# --- Inline-rendering geometry (fractions of the font size unless noted) ---
SUPERSCRIPT_SCALE = 0.72        # footnote-marker glyph size vs body size
SUPERSCRIPT_RISE_FRAC = 0.33    # baseline raise for superscript words
HIGHLIGHT_DESCENT_FRAC = 0.28   # yellow box extends this far below baseline
HIGHLIGHT_ASCENT_FRAC = 0.86    # ... and this far above
UNDERLINE_OFFSET_PT = 1.6       # underline rule sits this far below baseline
UNDERLINE_WIDTH_PT = 0.6        # underline rule stroke width

# --- Caption filer block density ---
# The filer block compacts to sub-grid spacing so a long address never
# eats the caption: items are laid at least this many points apart, on a
# span of at least FILER_BLOCK_MIN_GRID_SPAN grid lines.
FILER_BLOCK_TARGET_LEADING = 14.0
FILER_BLOCK_MIN_GRID_SPAN = 2

# --- Footnote area geometry ---
FOOTNOTE_RULE_LENGTH = 2.0 * 72          # separator rule above notes: 2"
FOOTNOTE_RULE_RISE_FRAC = 0.4            # rule sits this fraction of the small
                                         # font size above the note baseline

REQUIRED_FIELDS_PLEADING = [
    "filer_name", "filer_address_lines", "filer_phone", "filer_email",
    "filer_role", "court_name", "court_county", "petitioner",
    "respondent", "paper_title",
]

REQUIRED_FIELDS_LETTER = [
    "filer_name", "filer_address_lines",
    "to_name", "to_address_lines", "paper_title",
]

# Plain documents (contracts, estate instruments, attestations): a
# centered title, ordinary letter-size text, page numbers — no court
# caption, no letterhead, no 28-line grid.
REQUIRED_FIELDS_DOCUMENT = ["paper_title"]

REQUIRED_FIELDS_BY_DOCTYPE = {
    "pleading": REQUIRED_FIELDS_PLEADING,
    "letter": REQUIRED_FIELDS_LETTER,
    "document": REQUIRED_FIELDS_DOCUMENT,
}

SUPPORTED_EXHIBIT_EXTS = {".pdf", ".png", ".jpg", ".jpeg"}

# Sealed-exhibit wording (legal boilerplate; ADR-0010). The exhibit list
# annotates a sealed exhibit's entry; its placeholder tab sheet (public
# packet only — see merge_outputs) carries the uppercase note.
SEALED_EXHIBIT_LIST_ANNOTATION = " [Lodged Conditionally Under Seal]"
SEALED_EXHIBIT_TAB_NOTE = "LODGED CONDITIONALLY UNDER SEAL"
SUPPORTED_VARIANTS = {"sealed", "public"}
SUPPORTED_PUBLIC_DISCLOSURE = {"full", "redacted", "omitted"}

# Variant used when a document carries no redaction/variant-aware content
# and the caller did not request one. Redaction-bearing documents built
# without an explicit --variant default to "public" instead (see
# effective_variant): the least-careful invocation must produce the
# least-sensitive artifact.
DEFAULT_VARIANT = "sealed"

# Suffix appended to the output PDF's filename for the redaction-log
# sidecar (e.g. complaint.pdf -> complaint.pdf.redactions.json). The
# sidecar quotes the verbatim sealed text, so it is written only for
# sealed-variant builds — never into a public output directory.
REDACTION_SIDECAR_SUFFIX = ".redactions.json"

# ---------------------------------------------------------------------------
# Keep-with-signature policy — ONE policy, consumed by both emitters
# (PDF grid math in PleadingPDF; Word keep-with-next in md_to_docx).
# A signature block never splits across pages, and the heading / short
# lead-in paragraph(s) that introduce it ("ORDER", "IT IS SO ORDERED.")
# are never stranded at a page bottom above it. An isolated signature
# page is a known filing-rejection trigger.
# ---------------------------------------------------------------------------

# At most this many consecutive lead-in blocks are pulled onto the
# signature's page (a longer run is body text, not a lead-in).
SIG_KEEP_MAX_LEAD_BLOCKS = 3
# A non-heading block counts as a "short lead" at up to this many grid
# lines as rendered (2 text lines + the trailing blank separator).
# A heading is never stranded at a page bottom: it moves to the next
# page unless at least this many lines of its content fit under it
# (Butterick's keep-with-next; the statutes don't care, readers do).
HEADING_MIN_FOLLOWING_LINES = 2

SIG_LEAD_MAX_GRID_LINES = 3
# DOCX proxy for the grid-line cap: Word does its own wrapping, so the
# docx emitter approximates "≤ 2 wrapped lines" by character count.
SIG_LEAD_MAX_CHARS = 120

# Signature-block heights on the pleading grid. The emitters and the
# keep-together math both read these, so the two can never drift.
SIGNBLOCK_GRID_LINES = 5             # date + blank + rule + blank + name
SIGNBLOCK_ROLE_EXTRA_LINE = 1        # + role line when one prints
JUDGESIGNBLOCK_GRID_LINES = 5        # Dated + blank + rule + blank + title
LETTERSIGNBLOCK_BASE_GRID_LINES = 4  # Sincerely + blank + rule + blank (+1 per name line)

# Barcode blocks (\barcode{format}{data} / \barcodefile{format}{path}):
# machine-readable symbols on the page, sized from physical module
# dimensions so a phone or scanner reads them from paper. Formats: qr
# (qrencode; error correction M tolerates print damage, 4-module quiet
# zone is the spec minimum), code128 and pdf417 (zint). Modules print
# at 0.5 mm; a symbol wider than the text column is scaled down to it.
# PDF417 aims at a 3:1 width:height ratio (its sweet spot for handheld
# scanners), chosen by searching zint's column count.
# Printed module size per format, mm. PDF417 at 0.5 mm (its stacked
# rows tolerate less X-dimension); QR and Code 128 at 0.75 mm, the
# GS1 general-distribution neighborhood, because these symbols must
# survive a recorder's office scanner and camscanned nearly-flat
# paper, not just a crisp screenshot.
BARCODE_MODULE_MM = {"qr": 0.75, "code128": 0.75, "pdf417": 0.5}
MM_TO_PT = 72 / 25.4
# Symbols are scaled UP so their smaller side is at least this: a
# symbol that decodes from a crisp screenshot still has to survive a
# recorder's office scanner and a camscanned page that is almost but
# not quite flat. Modules grow past 0.5 mm as needed; the text-column
# cap still wins for payloads too wide to fit (prefer a 2D format for
# those).
BARCODE_MIN_SIDE_MM = 40
BARCODE_MIN_SIDE_PT = BARCODE_MIN_SIDE_MM * 72 / 25.4
BARCODE_CAPTION_EXTRA_LINE = 1       # + caption line when one prints
BARCODE_PX_PER_MODULE = 8            # render resolution (zint --scale 4)
PDF417_TARGET_ASPECT = 3.0           # width / height
PDF417_COLS_RANGE = range(2, 21)     # zint --cols candidates
CODE128_HEIGHT_MODULES = 30          # 1D bar height at 0.5 mm/module (15 mm)
QR_ERROR_CORRECTION = "M"            # qrencode -l: L/M/Q/H
QR_MARGIN_MODULES = 4                # qrencode -m: quiet-zone width
ZINT_FORMAT_CODES = {"code128": "20", "pdf417": "55"}
BARCODE_FORMATS = ("qr", "code128", "pdf417")

# Fixed-width blocks (\fixedwidth{ ... }): verbatim monospace, exempt
# from every typographic substitution -- the construct for armored key
# blocks, hashes, and anything where a mangled character is corruption
# rather than style. The size fits the block's longest line to the
# text column (Courier advance = 0.6 em).
FIXEDWIDTH_FONT = "Courier"
FIXEDWIDTH_FONT_BOLD = "Courier-Bold"
# \filelink text: gentle, low-saturation blue with a thin underline, the
# conventional affordance that a span is clickable, print-safe in gray.
FILELINK_COLOR_RGB = (110 / 255, 140 / 255, 175 / 255)
FIXEDWIDTH_MAX_SIZE = 12
FIXEDWIDTH_MIN_SIZE = 6
FIXEDWIDTH_ADVANCE_EM = 0.6

# ---------------------------------------------------------------------------
# Notarial certificates (California) — drawn objects, not text expansion.
#
# The wording is statutory and verbatim: Civ. Code 1189 (acknowledgment),
# Gov. Code 8202 (jurat), Civ. Code 1195 (proof of execution by
# subscribing witness), each with the consumer disclosure that must
# appear "in an enclosed box" at the top (all three statutes, as amended
# by SB 1050, eff. 2015). Layout follows the Secretary of State's
# published forms: the whole certificate inside a border, the disclosure
# in its own inner box, venue lines, the certificate paragraph, and a
# signature line with clear space for the seal (which must remain
# photographically reproducible -- a recorder may reject an illegible
# or overlapping seal). A certificate is never split across pages, and
# it renders in its own sans-serif face so it reads as the officer's
# certificate rather than the instrument's prose.
# ---------------------------------------------------------------------------

NOTARIAL_FONT = "Helvetica"
NOTARIAL_FONT_BOLD = "Helvetica-Bold"
NOTARIAL_FONT_SIZE = 9.5
NOTARIAL_LEADING = 12.5              # pt between certificate text lines
NOTARIAL_PAD = 12                    # inner padding of the outer box, pt
NOTARIAL_DISCLOSURE_FRAC = 0.62      # disclosure box width / text width
NOTARIAL_SEAL_W = 190                # clear seal zone, pt (~2.6 in)
NOTARIAL_SEAL_H = 100                # clear seal zone, pt (~1.4 in)
NOTARIAL_RULE = 0.8                  # border line width, pt

NOTARIAL_DISCLOSURE = (
    "A notary public or other officer completing this certificate "
    "verifies only the identity of the individual who signed the "
    "document to which this certificate is attached, and not the "
    "truthfulness, accuracy, or validity of that document."
)

ACK_BODY = (
    "On ____________________ before me, "
    "___________________________________________ (insert name and title "
    "of the officer), personally appeared {signer}, who proved to me on "
    "the basis of satisfactory evidence to be the person(s) whose "
    "name(s) is/are subscribed to the within instrument and acknowledged "
    "to me that he/she/they executed the same in his/her/their "
    "authorized capacity(ies), and that by his/her/their signature(s) on "
    "the instrument the person(s), or the entity upon behalf of which "
    "the person(s) acted, executed the instrument."
)
ACK_PERJURY = (
    "I certify under PENALTY OF PERJURY under the laws of the State of "
    "California that the foregoing paragraph is true and correct."
)
ACK_WITNESS_LINE = "WITNESS my hand and official seal."

JURAT_BODY = (
    "Subscribed and sworn to (or affirmed) before me on this _____ day "
    "of ______________, 20___, by {signer}, proved to me on the basis "
    "of satisfactory evidence to be the person(s) who appeared before me."
)

PROOF_BODY = (
    "On ____________________ (date), before me, "
    "___________________________________________ (name and title of "
    "officer), personally appeared {witness} (name of subscribing "
    "witness), proved to me to be the person whose name is subscribed "
    "to the within instrument, as a witness thereto, on the oath of "
    "____________________ (name of credible witness), a credible "
    "witness who is known to me and provided a satisfactory identifying "
    "document. {witness}, being by me duly sworn, said that he/she was "
    "present and saw/heard {principal} (name[s] of principal[s]), the "
    "same person(s) described in and whose name(s) is/are subscribed to "
    "the within or attached instrument in his/her/their authorized "
    "capacity(ies) as (a) party(ies) thereto, execute or acknowledge "
    "executing the same, and that said affiant subscribed his/her name "
    "to the within or attached instrument as a witness at the request "
    "of {principal}."
)

NOTARIAL_TITLES = {
    "acknowledgment": "ACKNOWLEDGMENT",
    "jurat": "JURAT",
    "proofexec": "PROOF OF EXECUTION BY SUBSCRIBING WITNESS",
}

# Signature blocks are one macro with styles (ADR-0027):
#   \signblock{dated}{NAME}{ROLE?}          Dated line + rule + name
#   \signblock{decl}{NAME}{LOCATION?}{ROLE?} perjury execution line
#   \signblock{judge}{TITLE}                proposed-order judge block
#   \signblock{letter}{Name\\Firm\\Role}    letter closing
#   \signblock{whereof}{NAME}{ROLE?}{INSTRUMENT?}
#       "IN WITNESS WHEREOF, I, {name}, sign this {instrument} on
#       this ____ day of ____________, 20__, at ____________." + rule
#       + name + role. No Dated line: the clause recites the date, so
#       the old pairing of prose + \signblock printed it twice.
# The legacy macros (\declsignblock, \judgesignblock,
# \lettersignblock, and bare \signblock{NAME}) still parse, mapped to
# these styles with a deprecation warning: a live matter mid-filing
# never breaks on a taxonomy change.
SIGNBLOCK_STYLES = ("dated", "decl", "judge", "letter", "whereof")
WHEREOF_CLAUSE = ("IN WITNESS WHEREOF, I, {name}, sign this {instrument} "
                  "on this _____ day of _________________, 20___, at "
                  "_________________________.")
WHEREOF_TAIL_GRID_LINES = 5          # blank + rule + blank + name (+role)

# Every signature area also carries DocuSeal text tags
# ({{Name;role=...;type=...}}, docuseal.com/docs/api) drawn in white
# 6 pt text over the blanks: invisible on paper, machine-readable in
# the text layer, and stripped from the executed document by
# DocuSeal's default remove_tags. Signer roles number in document
# order -- the same order `sc docuseal send --to` assigns them.
ESIGN_TAG_FONT_SIZE = 6
ESIGN_ROLE_PREFIX = "Signer"

# Document-layout primitives for plain instruments (notes, contracts):
#   \leftright{left}{right}   one line, left at margin, right flush right
#   \center{text}             one centered line
#   \sigrow{left label}{right label}
#       side-by-side signature rules with labels beneath -- the
#       borrower/date row of a promissory note. Labels take \\ for a
#       second line ("Sue Yarvin, Lender\\Accepted and agreed").
SIGROW_RULE_FRAC = 0.44              # each rule's width / text width
SIGROW_RIGHT_START_FRAC = 0.54       # right rule's left edge / text width
SIGROW_GRID_LINES_BASE = 4           # blank + rule + label + blank

# Witness signature grids (\witnessattestation): per witness, a
# signature rule plus printed-name, residence, and date lines. Part of
# the instrument (unlike a notarial certificate), so it stays in the
# document face; it is still an object the page-break logic keeps whole.
WITNESS_GRID_LINES_EACH = 6          # rule + name + residing + date + 2 blanks


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TextSpan:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    highlight: bool = False
    # Inline \fixedwidth{...} (or backticks): verbatim monospace (Courier),
    # exempt from typographic substitutions -- file paths, hashes, code.
    mono: bool = False
    # \filelink{path}{text?}: relative file target for a link annotation.
    file_link: Optional[str] = None
    # When set, this span is a footnote *reference* marker (text is ignored;
    # the superscript number is assigned later from document order).
    footnote_id: Optional[str] = None


@dataclass
class StyledWord:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    highlight: bool = False
    mono: bool = False
    superscript: bool = False
    no_space_before: bool = False
    link_target: Optional[str] = None
    # Footnote number this word marks (set on superscript reference markers).
    footnote_num: Optional[int] = None

    def font_name(self) -> str:
        if self.mono:
            return FIXEDWIDTH_FONT_BOLD if self.bold else FIXEDWIDTH_FONT
        if self.bold and self.italic:
            return FONT_NAME_BOLD_ITALIC
        if self.bold:
            return FONT_NAME_BOLD
        if self.italic:
            return FONT_NAME_ITALIC
        return FONT_NAME

    def effective_size(self, font_size: int = FONT_SIZE) -> float:
        return font_size * SUPERSCRIPT_SCALE if self.superscript else font_size

    def width(self, font_size: int = FONT_SIZE) -> float:
        return pdfmetrics.stringWidth(self.text, self.font_name(),
                                      self.effective_size(font_size))


@dataclass
class LinkRect:
    page_index: int
    x: float
    y: float
    width: float
    height: float
    dest: str


@dataclass
class Block:
    """A parsed content block. Field semantics vary by kind:

    heading:       text=heading text, spans=styled content, level=1/2/3
    paragraph:     text=raw text, spans=styled content
    bullet:        text=raw text, spans=styled content
    blockquote:    text=raw text, spans=styled content
    signblock:     text=name line (e.g. "JANE ROE"); dated style
    whereofsignblock: text=name, spans[0]=role, spans[1]=instrument word
    declsignblock: text=name, spans[0].text=location, spans[1].text=role (optional; if empty, no role line printed)
    barcode:       text=payload, spans[0]=format (qr|code128|pdf417), spans[1]=caption
    barcodefile:   text=path whose contents are the payload, spans as barcode
    fixedwidth:    text=verbatim lines joined by newline; no typographic subs
    leftright:     text=left text, spans[0]=right text (both styled)
    centerline:    text=centered line (styled)
    sigrow:        text=left label(s), spans[0]=right label(s); \\ splits lines
    acknowledgment: text=signer name(s), blank lines if empty (CA Civ. Code 1189)
    jurat:          text=signer name(s) (CA Gov. Code 8202)
    proofexec:      text=subscribing witness, spans[0].text=principal(s) (CA Civ. Code 1195)
    witnessattest:  text=witness names separated by \\ (signature grids)
    table:         text="", rows=[[col1, col2, ...], ...] (first row is header)
    """
    kind: str
    text: str
    spans: List[TextSpan] = field(default_factory=list)
    level: int = 0
    rows: Optional[List[List[str]]] = None


@dataclass
class Exhibit:
    shortname: str
    title: str
    path: Optional[Path]
    letter: str
    sealed: bool = False
    pages: Optional[str] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_page_ranges(spec: str, total_pages: int) -> List[int]:
    """Parse a page range spec like '1-3', '2', '1,3-5' into 0-based indices.

    Every referenced page must exist: an out-of-range or reversed range
    fails with a ValueError rather than being silently clamped or
    dropped — a truncated exhibit is a defect, not a convenience.
    """
    def page_number(token: str) -> int:
        try:
            n = int(token.strip())
        except ValueError:
            raise ValueError(f"Invalid pages spec {spec!r}: {token.strip()!r} is not a page number")
        if not 1 <= n <= total_pages:
            raise ValueError(
                f"Out-of-range pages spec {spec!r}: page {n} does not exist "
                f"(PDF has {total_pages} page{'s' if total_pages != 1 else ''})"
            )
        return n

    indices: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            s = page_number(start)
            e = page_number(end)
            if s > e:
                raise ValueError(
                    f"Invalid pages spec {spec!r}: range {part!r} is reversed"
                )
            indices.extend(range(s - 1, e))
        else:
            indices.append(page_number(part) - 1)
    return indices

def roman(num: int) -> str:
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
        (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
        (5, "V"), (4, "IV"), (1, "I"),
    ]
    out: List[str] = []
    for v, s in vals:
        while num >= v:
            out.append(s)
            num -= v
    return "".join(out)


def alpha(num: int) -> str:
    if num < 1:
        raise ValueError("alpha numbering starts at 1")
    out: List[str] = []
    while num:
        num -= 1
        out.append(chr(ord("A") + (num % 26)))
        num //= 26
    return "".join(reversed(out))


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd'][n % 10] if n % 10 < 4 else 'th'}"


def _format_sign_date(d: datetime.date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _format_decl_date(d: datetime.date) -> str:
    return f"{_ordinal(d.day)} day of {d.strftime('%B')}, {d.year}"


def unsigned_decl_execution_line(year: int, location: str) -> str:
    """Fill-in-the-blank execution line for an unsigned \\declsignblock.

    Shared with the TXT renderer so the wording never drifts between
    artifacts of the same source.
    """
    return f"Executed this _____ day of _________________, {year}, at {location}."


def unsigned_dated_line() -> str:
    """Fill-in-the-blank date line for an unsigned \\signblock.

    A bare full-date blank, deliberately: a pre-printed ", <year>"
    reads nicely but forces freeform text into the blank (the year is
    already spoken for) and is wrong the moment a December build is
    signed in January. The blank takes the whole date, so the e-sign
    field can be type=date."""
    return "Dated: _________________________"


def _format_letter_date(raw: str) -> str:
    """Parse a letter date field: 'today', 'YYYY-MM-DD', or pass through as-is."""
    if raw.strip().lower() == "today":
        return _format_sign_date(datetime.date.today())
    try:
        return _format_sign_date(datetime.date.fromisoformat(raw.strip()))
    except (ValueError, TypeError):
        return str(raw)


# ---------------------------------------------------------------------------
# Typographic substitutions
# ---------------------------------------------------------------------------

# Verbatim spans -- inline \fixedwidth{...}, its backtick synonym `...`,
# \filelink{...}{...}, and the block form of \fixedwidth -- carry file
# paths, hashes, and code where a substituted or re-spaced character is
# corruption, not style. Every whole-body or whole-line text transform
# must skip them; _map_outside_verbatim is the one way to do that.
_VERBATIM_SPAN_RE = re.compile(
    r"(\\fixedwidth\{[^{}\n]*\}"
    r"|`[^`\n]+`"
    r"|\\filelink\{[^{}\n]*\}(?:\{[^{}\n]*\})?"
    r"|^\\fixedwidth\{$.*?^\}$)",
    re.M | re.S,
)


def _map_outside_verbatim(text, transform):
    """Apply transform(segment) to everything outside verbatim spans."""
    parts = _VERBATIM_SPAN_RE.split(text)
    if len(parts) == 1:
        return transform(text)
    return "".join(part if i % 2 else transform(part)
                   for i, part in enumerate(parts))


def typographic_subs(text: str) -> str:
    if _VERBATIM_SPAN_RE.search(text):
        return _map_outside_verbatim(text, typographic_subs)
    text = text.replace("---", "\u2014")  # em dash
    text = text.replace("--", "\u2013")   # en dash
    text = re.sub(r'"([^"]*)"', "\u201c\\1\u201d", text)  # smart double quotes
    text = re.sub(r"(?<=\w)'", "\u2019", text)             # apostrophe after letter → '
    # Possessive after an abbreviation's trailing period ("C.E.O.'s") is an
    # apostrophe, not an opening quote; resolve it before the opening-quote
    # rule below would misread it (e.g. C.E.O.'s → C.E.O.\u2019s).
    text = re.sub(r"(?<=\w\.)'(?=\w)", "\u2019", text)
    text = re.sub(r"'(?=\w)", "\u2018", text)              # opening quote before letter → '
    text = text.replace("'", "\u2019")                     # any remaining → '
    return text


# Spaced dashes (" --- " / " -- ") in a source render as spaced glyphs: the
# substitution layer preserves whitespace literally and never refuses (spec:
# specs/pleading/generator.md, non-obvious constraints), so the build warns
# on stderr instead of failing.
_SPACED_DASH_RE = re.compile(r" ---? ")


def warn_spaced_dashes(raw: str, source: Path) -> None:
    """Emit a stderr warning for each source line carrying a spaced dash."""
    for lineno, line in enumerate(raw.split("\n"), start=1):
        if _SPACED_DASH_RE.search(line):
            print(
                f"WARNING: spaced dash in {source.name} line {lineno}: "
                f"{line.strip()[:70]!r} (write 'text---text', no spaces)",
                file=sys.stderr,
            )

# ---------------------------------------------------------------------------
# Inline style parsing (*italic*, **bold**, <u>underline</u>, [^footnote])
# ---------------------------------------------------------------------------

_INLINE_RE = re.compile(
    r"(\*\*\*(.+?)\*\*\*"    # 1/2: ***bold italic***
    r"|\*\*(.+?)\*\*"         # 3: **bold**
    r"|\*(.+?)\*"             # 4: *italic*
    r"|<u>(.+?)</u>"          # 5: <u>underline</u>
    r"|\\highlight\{((?:[^{}]|\{[^{}]*\})*)\}"  # 6: \highlight{...} (yellow bg)
    r"|\\fixedwidth\{([^{}\n]*)\}"  # 7: inline \fixedwidth{...} (verbatim monospace)
    r"|`([^`\n]+)`"              # 8: `...` backtick synonym for \fixedwidth
    r"|\\filelink\{([^{}\n]*)\}(?:\{([^{}\n]*)\})?"  # 9/10: \filelink{path}{text?}
    r"|\[\^([^\]]+?)\]"       # 11: [^footnote-id]  (reference marker)
    r")"
)


def parse_inline_styles(text: str, bold: bool = False, italic: bool = False,
                        underline: bool = False, highlight: bool = False) -> List[TextSpan]:
    """Parse inline emphasis into styled spans.

    Emphasis nests: styles found inside a match inherit the enclosing flags,
    so ``**<u>x</u>**`` yields a bold+underline span. ``<u>..</u>`` toggles
    underline; ``\\highlight{...}`` renders its contents with a yellow
    background (composes with bold/italic/underline, e.g.
    ``\\highlight{**bold**}``); ``\\fixedwidth{...}`` renders its contents
    verbatim in monospace (no nested emphasis parsing -- the braces hold a
    literal token such as a file path); ``[^id]`` becomes a footnote
    reference marker span.
    """
    spans: List[TextSpan] = []
    last = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > last:
            spans.append(TextSpan(text[last:m.start()], bold=bold,
                                  italic=italic, underline=underline,
                                  highlight=highlight))
        if m.group(2) is not None:
            spans.extend(parse_inline_styles(m.group(2), True, True, underline, highlight))
        elif m.group(3) is not None:
            spans.extend(parse_inline_styles(m.group(3), True, italic, underline, highlight))
        elif m.group(4) is not None:
            spans.extend(parse_inline_styles(m.group(4), bold, True, underline, highlight))
        elif m.group(5) is not None:
            spans.extend(parse_inline_styles(m.group(5), bold, italic, True, highlight))
        elif m.group(6) is not None:
            spans.extend(parse_inline_styles(m.group(6), bold, italic, underline, True))
        elif m.group(7) is not None:
            spans.append(TextSpan(m.group(7), bold=bold, italic=italic,
                                  underline=underline, highlight=highlight,
                                  mono=True))
        elif m.group(8) is not None:
            spans.append(TextSpan(m.group(8), bold=bold, italic=italic,
                                  underline=underline, highlight=highlight,
                                  mono=True))
        elif m.group(9) is not None:
            display = m.group(10) if m.group(10) is not None else m.group(9)
            spans.append(TextSpan(display, bold=bold, italic=italic,
                                  underline=True, highlight=highlight,
                                  mono=True, file_link=m.group(9)))
        elif m.group(11) is not None:
            spans.append(TextSpan("", footnote_id=m.group(11).strip()))
        last = m.end()
    if last < len(text):
        spans.append(TextSpan(text[last:], bold=bold, italic=italic,
                              underline=underline, highlight=highlight))
    if not spans:
        spans.append(TextSpan(text, bold=bold, italic=italic,
                              underline=underline, highlight=highlight))
    return spans


_OPENING_PUNCT = set("(\u201c\u2018[")
_CLOSING_PUNCT_CHARS = set(")\u201d\u2019.,;:!?]")


def spans_to_styled_words(spans: List[TextSpan],
                          footnote_numbers: Optional[Dict[str, int]] = None) -> List[StyledWord]:
    words: List[StyledWord] = []
    for span in spans:
        if span.footnote_id is not None:
            num = (footnote_numbers or {}).get(span.footnote_id)
            if num is None:
                # Unknown footnote id: render the literal marker so the error
                # is visible rather than silently dropping text.
                words.append(StyledWord(f"[^{span.footnote_id}]",
                                        no_space_before=bool(words)))
            else:
                words.append(StyledWord(str(num), superscript=True,
                                        no_space_before=bool(words),
                                        footnote_num=num))
            continue
        parts = span.text.split()
        for i, w in enumerate(parts):
            glue = bool(words
                        and i == 0
                        and not span.text[0].isspace()
                        and (words[-1].text[-1] in _OPENING_PUNCT
                             or w[0] in _CLOSING_PUNCT_CHARS))
            words.append(StyledWord(w, bold=span.bold, italic=span.italic,
                                    underline=span.underline,
                                    highlight=span.highlight,
                                    mono=span.mono,
                                    link_target=(f"file:{span.file_link}"
                                                 if span.file_link else None),
                                    no_space_before=glue))
    return words


def tag_exhibit_links(words: List[StyledWord], exhibit_letters: set) -> None:
    """Find 'Exhibit X' or 'Attachment X' word pairs and set link_target on them."""
    for i, word in enumerate(words):
        word_text = word.text.lstrip("([{\"'")
        if word_text in ("Exhibit", "Attachment") and i + 1 < len(words):
            next_text = words[i + 1].text.rstrip(".,;:)")
            if next_text in exhibit_letters:
                dest = f"exhibit_{next_text}"
                word.link_target = dest
                words[i + 1].link_target = dest
                # If the citation is parenthetical, keep the entire parenthetical
                # clickable rather than only the tiny "Exhibit X" token pair.
                if word.text != word_text:
                    for j in range(i + 2, len(words)):
                        words[j].link_target = dest
                        if ")" in words[j].text:
                            break


def glue_clusters(words: List[StyledWord]) -> List[List[StyledWord]]:
    """Group words into break-atomic clusters: a word plus any glued
    (no_space_before) followers. "Kollmer" + "," is one unit — a line
    may never start with the comma that belongs to the word above
    (the comma-orphan bug), nor strand a footnote marker."""
    clusters: List[List[StyledWord]] = []
    for w in words:
        if clusters and w.no_space_before:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    return clusters


def wrap_styled_words(words: List[StyledWord], max_width: float, font_size: int = FONT_SIZE) -> List[List[StyledWord]]:
    if not words:
        return []
    lines: List[List[StyledWord]] = []
    current: List[StyledWord] = []
    space_w = pdfmetrics.stringWidth(" ", FONT_NAME, font_size)
    cur_width = 0.0
    for cluster in glue_clusters(words):
        cw = sum(w.width(font_size) for w in cluster)
        gap = space_w if current else 0.0
        if current and cur_width + gap + cw > max_width:
            lines.append(current)
            current = list(cluster)
            cur_width = cw
        else:
            current.extend(cluster)
            cur_width += gap + cw
    if current:
        lines.append(current)
    return lines


def draw_styled_words(c: canvas.Canvas, x: float, y: float, words: List[StyledWord],
                      font_size: int = FONT_SIZE) -> List[Tuple[float, float, float, str]]:
    """Draw words and return list of (x, width, y, link_dest) for any linked words.

    Underlined runs are drawn as a single continuous rule beneath the text
    (including the spaces between adjacent underlined words). Superscript
    words (footnote markers) are drawn smaller and raised above the baseline.
    """
    space_w = pdfmetrics.stringWidth(" ", FONT_NAME, font_size)

    # First pass: compute each word's start x (identical spacing math to the
    # draw pass below) so contiguous highlighted runs can be filled as a
    # single rectangle *underneath* the text, before any glyphs are drawn.
    starts: List[float] = []
    cx0 = x
    for i, word in enumerate(words):
        if i > 0 and not word.no_space_before:
            cx0 += space_w
        starts.append(cx0)
        cx0 += word.width(font_size)

    hl_y0 = y - font_size * HIGHLIGHT_DESCENT_FRAC
    hl_y1 = y + font_size * HIGHLIGHT_ASCENT_FRAC
    c.saveState()
    c.setFillColorRGB(1, 1, 0)  # yellow
    run_start: Optional[float] = None
    run_end: float = 0.0
    for i, word in enumerate(words):
        if word.highlight:
            if run_start is None:
                run_start = starts[i]
            run_end = starts[i] + word.width(font_size)
        else:
            if run_start is not None:
                c.rect(run_start, hl_y0, run_end - run_start, hl_y1 - hl_y0,
                       fill=1, stroke=0)
                run_start = None
    if run_start is not None:
        c.rect(run_start, hl_y0, run_end - run_start, hl_y1 - hl_y0,
               fill=1, stroke=0)
    c.restoreState()

    cx = x
    link_rects: List[Tuple[float, float, float, str]] = []
    active_link: Optional[str] = None
    link_start_x = 0.0
    ul_active = False
    ul_is_filelink = False
    ul_start_x = 0.0
    ul_y = y - UNDERLINE_OFFSET_PT
    prev_end_x = x

    def flush_underline(end_x: float) -> None:
        nonlocal ul_active
        if ul_active:
            c.setLineWidth(UNDERLINE_WIDTH_PT)
            if ul_is_filelink:
                c.setStrokeColorRGB(*FILELINK_COLOR_RGB)
            c.line(ul_start_x, ul_y, end_x, ul_y)
            c.setStrokeColorRGB(0, 0, 0)
            ul_active = False

    for i, word in enumerate(words):
        # Horizontal advance: add an inter-word space unless glued.
        if i > 0 and not word.no_space_before:
            # An underline run continues across a space only when both the
            # previous and current words are underlined.
            if ul_active and not word.underline:
                flush_underline(prev_end_x)
            cx += space_w
        word_start_x = cx

        # Link rectangle bookkeeping (keyed off word start position).
        if word.link_target and word.link_target != active_link:
            if active_link:
                link_rects.append((link_start_x, word_start_x - link_start_x, y, active_link))
            active_link = word.link_target
            link_start_x = word_start_x
        elif not word.link_target and active_link:
            link_rects.append((link_start_x, prev_end_x - link_start_x, y, active_link))
            active_link = None

        if word.underline and not ul_active:
            ul_active = True
            ul_is_filelink = bool(word.link_target
                                  and word.link_target.startswith("file:"))
            ul_start_x = word_start_x
        elif not word.underline and ul_active:
            flush_underline(prev_end_x)

        size = word.effective_size(font_size)
        wy = y + font_size * SUPERSCRIPT_RISE_FRAC if word.superscript else y
        c.setFont(word.font_name(), size)
        if word.link_target and word.link_target.startswith("file:"):
            c.setFillColorRGB(*FILELINK_COLOR_RGB)
        else:
            c.setFillColorRGB(0, 0, 0)
        c.drawString(word_start_x, wy, word.text)
        cx = word_start_x + word.width(font_size)
        prev_end_x = cx

    flush_underline(prev_end_x)
    if active_link:
        link_rects.append((link_start_x, prev_end_x - link_start_x, y, active_link))
    return link_rects

# ---------------------------------------------------------------------------
# Plain-text wrapping (for captions and other non-styled contexts)
# ---------------------------------------------------------------------------

def wrap_text(text: str, max_width: float, font_name: str, font_size: int) -> List[str]:
    words = text.split()
    if not words:
        return []
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

# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def resolve_variant_value(value, variant: str):
    """Recursively resolve variant-aware YAML values.

    Any mapping whose keys are a subset of {"sealed", "public"} is treated
    as a variant selector and collapsed to the requested branch.
    """
    if isinstance(value, list):
        return [resolve_variant_value(v, variant) for v in value]

    if isinstance(value, dict):
        keys = set(value.keys())
        if keys and keys.issubset(SUPPORTED_VARIANTS):
            if variant not in value:
                raise ValueError(
                    f"Variant-specific value is missing key {variant!r}: {value!r}"
                )
            return resolve_variant_value(value[variant], variant)
        return {k: resolve_variant_value(v, variant) for k, v in value.items()}

    return value


def apply_variant_to_meta(meta: Dict, variant: str) -> Dict:
    """Return a copy of YAML metadata with variant-specific values resolved."""
    if variant not in SUPPORTED_VARIANTS:
        raise ValueError(
            f"Unknown variant: {variant!r} (expected one of {sorted(SUPPORTED_VARIANTS)})"
        )
    resolved = resolve_variant_value(meta, variant)
    if not isinstance(resolved, dict):
        raise ValueError("Resolved YAML front matter must remain a mapping/object")
    return resolved


BLANK_MACRO = re.compile(r"\\blank\{([0-9]*\.?[0-9]+)\s*(in|pt|cm|mm)\}")


def expand_blank_macros(body: str) -> str:
    """``\blank{2in}`` becomes a fill-in rule of that length.

    Sources used to spell blanks as literal underscore runs (and, worse,
    escaped ones), which is unreadable and couples the source to the
    body font's underscore width. The macro names the intent and a
    LENGTH; expansion to underscores happens here, shared by all three
    renderers, so PDF/TXT/DOCX agree and downstream machinery that
    recognizes ``_{3,}`` blank runs (e-sign field placement) keeps
    working. Sized against the body font; a blank inside a heading
    will run a little long, which a blank can afford."""
    unit_pt = {"in": 72.0, "pt": 1.0, "cm": 28.3465, "mm": 2.83465}

    def sub(m: "re.Match[str]") -> str:
        length = float(m.group(1)) * unit_pt[m.group(2)]
        one = pdfmetrics.stringWidth("_", FONT_NAME, FONT_SIZE)
        return "_" * max(3, round(length / one))

    return BLANK_MACRO.sub(sub, body)


def enforce_em_dash_spacing(body: str) -> str:
    """House rule, enforced rather than suggested: em dashes are never
    spaced (`text---text`). A single-spaced ` --- ` (or a spaced
    literal em dash) between non-dash characters is glued; longer dash
    runs (PGP armor, horizontal rules) and en-dash ranges are
    untouched. The stderr warning still fires so the SOURCE gets
    fixed — but the output no longer depends on it."""
    ws = r"(?:[ \t]+|[ \t]*\n[ \t]*)"  # spaces, or ONE line break + indent
    body = re.sub(rf"(?<=[^-\s]){ws}---{ws}(?=[^-\s])", "---", body)
    body = re.sub(rf"(?<=[^\u2014\s]){ws}\u2014{ws}(?=[^\u2014\s])", "\u2014", body)
    return body


def parse_front_matter(text: str) -> Tuple[Dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("Input must begin with YAML front matter delimited by ---")
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        raise ValueError("Could not find closing YAML front matter delimiter")
    raw_yaml = parts[0][4:]
    body = parts[1]
    data = yaml.safe_load(raw_yaml) or {}
    if not isinstance(data, dict):
        raise ValueError("YAML front matter must parse to a mapping/object")
    return data, _map_outside_verbatim(
        body, lambda seg: enforce_em_dash_spacing(expand_blank_macros(seg)))


def _parse_braced_argument(text: str, open_brace_idx: int) -> Tuple[str, int]:
    """Parse one balanced {...} argument and return (content, next_index)."""
    if open_brace_idx >= len(text) or text[open_brace_idx] != "{":
        raise ValueError("Expected '{' while parsing macro argument")
    depth = 0
    i = open_brace_idx
    chars: List[str] = []
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
            if depth > 1:
                chars.append(ch)
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return "".join(chars), i + 1
            chars.append(ch)
        else:
            chars.append(ch)
        i += 1
    raise ValueError("Unterminated braced macro argument")


def substitute_redaction_macros(body: str, meta: Dict, variant: str) -> str:
    """Resolve \\redact{...} macros, including optional justification args."""
    redactions = meta.get("redactions") or {}
    if redactions and not isinstance(redactions, dict):
        raise ValueError("redactions must be a YAML mapping/object if provided")
    for key, value in redactions.items():
        if not isinstance(value, str):
            raise ValueError(
                f"redactions[{key!r}] must resolve to a string, got {type(value).__name__}"
            )

    out: List[str] = []
    redaction_log = meta.setdefault("_redaction_log", [])
    # \redacttext is the legacy alias for \redact (spec, "Legacy note").
    # Longest token first: matching the shorter "\redact" prefix against a
    # "\redacttext" occurrence would pass the macro through literally —
    # leaking the sealed argument into a public build.
    macro_tokens = ("\\redacttext", "\\redact")
    i = 0
    while i < len(body):
        macro = next((t for t in macro_tokens if body.startswith(t, i)), None)
        if macro is not None:
            j = i + len(macro)
            if j >= len(body) or body[j] != "{":
                out.append(body[i])
                i += 1
                continue
            first_arg, next_idx = _parse_braced_argument(body, j)
            second_arg = None
            third_arg = None
            if next_idx < len(body) and body[next_idx] == "{":
                second_arg, next_idx = _parse_braced_argument(body, next_idx)
                if next_idx < len(body) and body[next_idx] == "{":
                    third_arg, next_idx = _parse_braced_argument(body, next_idx)
            if second_arg is not None:
                out.append(first_arg if variant == "sealed" else second_arg)
                if third_arg is not None:
                    redaction_log.append({
                        "sealed": first_arg,
                        "public": second_arg,
                        "justification": third_arg,
                    })
            else:
                # One-argument form: the argument names an entry in the
                # ``redactions:`` map. (A third argument cannot exist here —
                # it is only parsed after a second one.)
                if first_arg not in redactions:
                    raise ValueError(
                        "Unknown redaction literal referenced in body: "
                        f"{first_arg!r}"
                    )
                out.append(first_arg if variant == "sealed" else redactions[first_arg])
            i = next_idx
            continue

        out.append(body[i])
        i += 1

    return "".join(out)


def _derive_public_redacted_path(path: Path) -> Path:
    """Return the conventional public redacted companion path for an exhibit."""
    if path.suffix:
        return path.with_name(f"{path.stem}_redacted{path.suffix}")
    return path.with_name(f"{path.name}_redacted")


def _resolve_exhibit_path(path_str: str, base_dir: Path) -> Path:
    """Resolve an exhibit path.

    Bare filenames default to the sibling `exhibits/` directory next to `src/`.
    Paths containing directory components remain relative to the input Markdown
    file's directory for backward compatibility.
    """
    path = Path(path_str)
    if path.is_absolute():
        return path
    if path.parent == Path("."):
        return (base_dir.parent / "exhibits" / path).resolve()
    return (base_dir / path).resolve()


def _is_variant_mapping(value) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.keys()).issubset(SUPPORTED_VARIANTS)


def _contains_variant_mapping(value) -> bool:
    """True if any nested value in a YAML structure is a sealed/public mapping."""
    if _is_variant_mapping(value):
        return True
    if isinstance(value, dict):
        return any(_contains_variant_mapping(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_variant_mapping(v) for v in value)
    return False


def document_has_redactions(meta: Dict, body: str) -> bool:
    """True if a document's raw front matter or body carries any content
    whose rendering differs between the sealed and public variants.

    Must be called on the *raw* (pre-apply_variant_to_meta) metadata,
    since variant resolution erases the very mappings this looks for.
    """
    if "\\redact" in body:  # \redact, \redacttext, \redactionlog
        return True
    if meta.get("redactions"):
        return True
    if _contains_variant_mapping(meta):
        return True
    for item in meta.get("exhibits") or []:
        if isinstance(item, dict) and (
            item.get("sealed")
            or item.get("public_disclosure")
            or item.get("public_redacted")
        ):
            return True
    return False


def effective_variant(meta: Dict, body: str, requested: Optional[str]) -> str:
    """Resolve the variant to build when the caller may not have named one.

    An explicit request always wins. Without one, a redaction-bearing
    document builds its PUBLIC variant — an unscoped/default build must
    never silently render sealed content — and a document with no
    variant-sensitive content builds DEFAULT_VARIANT (the two variants
    are identical for it anyway).
    """
    if requested:
        return requested
    return "public" if document_has_redactions(meta, body) else DEFAULT_VARIANT


def _resolve_public_disclosure(raw_item: Dict, item_resolved: Dict, variant: str) -> str:
    """Determine how an exhibit should appear in the public build.

    Preferred schema is `public_disclosure: full|redacted|omitted`.
    Older fields are translated for backward compatibility.
    """
    disclosure = item_resolved.get("public_disclosure")
    if disclosure is not None:
        disclosure = str(disclosure).strip().lower()
        if disclosure not in SUPPORTED_PUBLIC_DISCLOSURE:
            raise ValueError(
                "public_disclosure must be one of "
                f"{sorted(SUPPORTED_PUBLIC_DISCLOSURE)}, got {disclosure!r}"
            )
        return disclosure

    # Backward compatibility: old public_redacted flag.
    if bool(item_resolved.get("public_redacted", False)):
        return "redacted"

    # Backward compatibility: old variant-aware sealed boolean used to mean
    # "omit from public" when public=True and sealed=False.
    raw_sealed = raw_item.get("sealed")
    if variant == "public" and _is_variant_mapping(raw_sealed):
        sealed_public = bool(resolve_variant_value(raw_sealed, "public"))
        sealed_sealed = bool(resolve_variant_value(raw_sealed, "sealed"))
        if sealed_public and not sealed_sealed:
            return "omitted"

    return "full"


def _parse_exhibits(meta: Dict, base_dir: Path, variant: str) -> List[Exhibit]:
    """Parse the 'exhibits' list from YAML metadata into Exhibit objects.

    Shared by validate_meta (for the current file) and load_external_exhibits
    (for cross-file exhibit references via exhibit_source).
    """
    exhibits_raw = meta.get("exhibits") or []
    if not isinstance(exhibits_raw, list):
        raise ValueError("exhibits must be a YAML list if provided")

    exhibits: List[Exhibit] = []
    seen: set = set()
    for idx, item in enumerate(exhibits_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"exhibits[{idx}] must be a mapping/object")
        raw_has_variant_path = _is_variant_mapping(item.get("path"))
        item_resolved = resolve_variant_value(item, variant)
        if not isinstance(item_resolved, dict):
            raise ValueError(f"exhibits[{idx}] must resolve to a mapping/object")
        for fld in ("shortname", "title"):
            if fld not in item_resolved or not isinstance(item_resolved[fld], str) or not item_resolved[fld].strip():
                raise ValueError(f"exhibits[{idx}] missing required string field: {fld}")
        shortname = item_resolved["shortname"].strip()
        if shortname in seen:
            raise ValueError(f"Duplicate exhibit shortname: {shortname}")
        seen.add(shortname)
        # YAML titles bypass markdown processing; apply typographic_subs so
        # `--` → en dash (and other substitutions) matches the pleading body.
        title = typographic_subs(item_resolved["title"].strip())
        public_disclosure = _resolve_public_disclosure(item, item_resolved, variant)
        if raw_has_variant_path and public_disclosure == "redacted":
            # Allowed: explicit public path overrides the _redacted convention.
            pass
        is_sealed = bool(item_resolved.get("sealed", False))
        if variant == "public" and public_disclosure == "omitted":
            is_sealed = True
        pages_spec = item_resolved.get("pages")
        if pages_spec is not None:
            pages_spec = str(pages_spec).strip()
        if is_sealed:
            exhibits.append(Exhibit(shortname=shortname, title=title,
                                    path=None, letter=alpha(idx), sealed=True))
        else:
            if "path" not in item_resolved or not isinstance(item_resolved["path"], str) or not item_resolved["path"].strip():
                raise ValueError(f"exhibits[{idx}] missing required string field: path")
            path = _resolve_exhibit_path(item_resolved["path"], base_dir)
            if (
                variant == "public"
                and public_disclosure == "redacted"
                and not raw_has_variant_path
            ):
                path = _derive_public_redacted_path(path)
            ext = path.suffix.lower()
            if ext not in SUPPORTED_EXHIBIT_EXTS:
                raise ValueError(f"Unsupported exhibit type for {shortname}: {path.suffix}")
            if not path.exists():
                raise ValueError(f"Exhibit file not found for {shortname}: {path}")
            exhibits.append(Exhibit(shortname=shortname, title=title,
                                    path=path, letter=alpha(idx), pages=pages_spec))
    return exhibits


def validate_meta(meta: Dict, input_path: Path, variant: str) -> List[Exhibit]:
    doctype = meta.get("doctype", "pleading")
    required = REQUIRED_FIELDS_BY_DOCTYPE.get(doctype)
    if required is None:
        raise ValueError(f"Unknown doctype: {doctype!r} (expected one of {list(REQUIRED_FIELDS_BY_DOCTYPE)})")
    missing = [k for k in required if k not in meta]
    if missing:
        raise ValueError(f"Missing required YAML fields for doctype={doctype!r}: {', '.join(missing)}")
    if "filer_address_lines" in meta:
        if not isinstance(meta["filer_address_lines"], list) or not all(
            isinstance(x, str) for x in meta["filer_address_lines"]
        ):
            raise ValueError("filer_address_lines must be a YAML list of strings")
    if "to_address_lines" in meta:
        if not isinstance(meta["to_address_lines"], list) or not all(
            isinstance(x, str) for x in meta["to_address_lines"]
        ):
            raise ValueError("to_address_lines must be a YAML list of strings")
    exhibits = _parse_exhibits(meta, input_path.parent.resolve(), variant)
    if meta.get("cover_sheet_only") and exhibits:
        # cover_sheet_only skips building any body at all, and an
        # exhibit appendix has nothing to attach behind -- there is no
        # document for it to follow.
        raise ValueError(
            "cover_sheet_only: true has no body to attach exhibits to -- "
            "remove `exhibits:` or drop `cover_sheet_only`"
        )
    return exhibits


def load_external_exhibits(source_path: Path, variant: str) -> List[Exhibit]:
    """Load exhibit definitions from another markdown file's YAML frontmatter.

    Used by the exhibit_source feature: a petition or memo can reference
    exhibits defined in a declaration by setting exhibit_source: "declaration.md"
    in its own YAML. Only the exhibits list is extracted; REQUIRED_FIELDS
    validation is skipped since we only need the exhibit map, not the full
    pleading metadata.
    """
    with open(source_path, "r", encoding="utf-8") as f:
        raw = f.read()
    ext_meta, _ = parse_front_matter(raw)
    return _parse_exhibits(ext_meta, source_path.parent.resolve(), variant)


# ---------------------------------------------------------------------------
# Consumer/employee notices (Code Civ. Proc. §§ 1985.3, 1985.6)
# ---------------------------------------------------------------------------
#
# A records subpoena that reaches an identifiable individual's records is
# invalid unless that individual is separately served with a Notice to
# Consumer or Employee (SUBP-025) and a copy of the subpoena. One notice
# per person, each addressed differently — so the source declares them as
# data and the build emits one filled form per recipient beside the
# subpoena's own PDF.

#: Front-matter key holding the list of notices a source must serve.
CONSUMER_NOTICES_KEY = "consumer_notices"
#: The registered form each entry fills.
CONSUMER_NOTICE_FORM = "subp025"
#: Output naming, relative to the source's own PDF.
CONSUMER_NOTICE_NAME = "{stem}.{form}.{slug}.pdf"
#: Entry keys that steer generation instead of filling a form field.
CONSUMER_NOTICE_CONTROL_KEYS = ("slug",)
#: The one entry key that is both required and a form field.
CONSUMER_NOTICE_RECIPIENT_KEY = "consumer"
#: Slugs name files; keep them short enough to stay readable in a packet.
CONSUMER_NOTICE_SLUG_MAX = 40


def _notice_slug(text: str) -> str:
    """Filename-safe short name for a notice recipient."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return slug[:CONSUMER_NOTICE_SLUG_MAX] or "consumer"


def consumer_notices(meta: Dict) -> List[Dict]:
    """Normalize the ``consumer_notices:`` front matter.

    Returns one ``{"slug": str, "data": dict}`` per recipient, where
    ``data`` carries that recipient's SUBP-025 field/checkbox values
    (including ``consumer``) to layer over the shared
    ``forms.subp025`` block. Every malformed entry raises: a skipped
    notice is an unserved consumer and an invalid subpoena, which must
    never be a silent outcome of a build.
    """
    raw = meta.get(CONSUMER_NOTICES_KEY)
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{CONSUMER_NOTICES_KEY} must be a YAML list of mappings")

    notices: List[Dict] = []
    seen: Dict[str, str] = {}
    for i, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{CONSUMER_NOTICES_KEY}[{i}] must be a mapping with a "
                f"'{CONSUMER_NOTICE_RECIPIENT_KEY}' key")
        consumer = str(entry.get(CONSUMER_NOTICE_RECIPIENT_KEY) or "").strip()
        if not consumer:
            raise ValueError(
                f"{CONSUMER_NOTICES_KEY}[{i}] is missing "
                f"'{CONSUMER_NOTICE_RECIPIENT_KEY}' (the person whose records "
                "are sought)")
        slug = str(entry.get("slug") or "").strip() or _notice_slug(consumer)
        if slug in seen:
            raise ValueError(
                f"{CONSUMER_NOTICES_KEY}: '{consumer}' and '{seen[slug]}' both "
                f"resolve to the file slug '{slug}'; give one an explicit "
                "'slug:' so neither notice overwrites the other")
        seen[slug] = consumer
        data = {k: v for k, v in entry.items()
                if k not in CONSUMER_NOTICE_CONTROL_KEYS}
        data[CONSUMER_NOTICE_RECIPIENT_KEY] = consumer
        notices.append({"slug": slug, "data": data})
    return notices


def consumer_notice_names(meta: Dict, stem: str) -> List[str]:
    """File names of the notices a source emits beside its own PDF."""
    return [
        CONSUMER_NOTICE_NAME.format(
            stem=stem, form=CONSUMER_NOTICE_FORM, slug=notice["slug"])
        for notice in consumer_notices(meta)
    ]


def emit_consumer_notices(meta: Dict, output_pdf: Path) -> List[Path]:
    """Fill one SUBP-025 per declared recipient next to ``output_pdf``.

    Shared values come from the ``forms.subp025`` block in the same
    front matter; the per-recipient entry overrides them. An entry key
    that is not a SUBP-025 field fails the build rather than filling a
    notice with a value the recipient will never see.
    """
    notices = consumer_notices(meta)
    if not notices:
        return []
    import form_fill

    output_pdf = Path(output_pdf)
    written: List[Path] = []
    for notice, name in zip(notices, consumer_notice_names(meta, output_pdf.stem)):
        out = output_pdf.parent / name
        res = form_fill.fill(CONSUMER_NOTICE_FORM, out, meta=meta,
                             data=dict(notice["data"]))
        unknown = [w for w in res.warnings if "unknown field" in w]
        if unknown:
            raise ValueError(
                f"{CONSUMER_NOTICES_KEY} entry for "
                f"{notice['data'][CONSUMER_NOTICE_RECIPIENT_KEY]!r}: "
                + "; ".join(unknown))
        for w in res.warnings:
            print(f"  [form {CONSUMER_NOTICE_FORM}] {w}", file=sys.stderr)
        written.append(out)
    return written


def dependency_info(input_path: Path, requested_variant: Optional[str] = None) -> Dict:
    """Build-dependency metadata for one source file.

    Importable API for build_envelope's staleness checks (replacing an
    inline ``python -c`` probe): the resolved input + exhibit file paths,
    plus the ``exhibit_source`` reference, under the same
    effective-variant resolution the build itself uses.
    """
    input_path = Path(input_path).resolve()
    with open(input_path, "r", encoding="utf-8") as f:
        raw = f.read()
    meta, body = parse_front_matter(raw)
    variant = effective_variant(meta, body, requested_variant)
    meta = apply_variant_to_meta(meta, variant)
    exhibits = validate_meta(meta, input_path, variant)
    deps = [str(input_path)]
    deps.extend(str(ex.path.resolve()) for ex in exhibits if ex.path is not None)
    exhibit_source = meta.get("exhibit_source")
    return {
        "deps": deps,
        "has_exhibit_source": exhibit_source is not None,
        "exhibit_source": exhibit_source,
        # Companion notices this source also emits (file names only, in
        # the same directory as the source's own PDF), so a build driver
        # can treat them as outputs for staleness purposes.
        "consumer_notice_names": consumer_notice_names(meta, input_path.stem),
    }


def _format_page_citation(pages_spec: str) -> str:
    """Format a pages spec for inline citation, e.g. '2-3' → 'pp. 2–3', '2' → 'p. 2'."""
    parts = [p.strip() for p in pages_spec.split(",")]
    is_single = len(parts) == 1 and "-" not in parts[0]
    formatted = ", ".join(p.replace("-", "\u2013") for p in parts)
    return f"p. {formatted}" if is_single else f"pp. {formatted}"


def _collect_redaction_log_from_sources(
    source_files: List[str], variant: str, base_dir: Path
) -> Dict[str, List[Dict]]:
    """Scan source files for three-parameter \\redact entries and return log entries grouped by file.

    A listed source that is missing or unparseable fails the build: the
    redaction log exists to demonstrate completeness to a court, so a
    typo'd filename must never silently shorten it.
    """
    entries_by_source: Dict[str, List[Dict]] = {}
    for source_file in source_files:
        source_path = (base_dir / source_file).resolve()
        if not source_path.exists():
            raise ValueError(
                f"redaction_log_sources entry not found: {source_file!r} "
                f"(resolved to {source_path})"
            )
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                raw = f.read()
            source_meta, source_body = parse_front_matter(raw)
            source_meta = apply_variant_to_meta(source_meta, variant)
            substitute_redaction_macros(source_body, source_meta, variant)
        except Exception as exc:
            raise ValueError(
                f"redaction_log_sources entry could not be processed: "
                f"{source_file!r}: {exc}"
            ) from exc
        log_entries = source_meta.get("_redaction_log", [])
        if log_entries:
            entries_by_source[source_file] = log_entries
    return entries_by_source


def substitute_redaction_log_macro(
    body: str, meta: Dict, variant: str, input_path: Path
) -> str:
    r"""Replace \redactionlog with an auto-generated numbered log.

    The log is built from three-parameter \redact{}{}{} entries found in the
    source files listed under ``redaction_log_sources`` in the YAML front
    matter, plus any entries collected from the current file.
    """
    if "\\redactionlog" not in body:
        return body

    source_files = meta.get("redaction_log_sources") or []
    entries_by_source = _collect_redaction_log_from_sources(
        source_files, variant, input_path.parent
    )

    current_entries = meta.get("_redaction_log", [])
    if current_entries:
        entries_by_source.setdefault(input_path.name, []).extend(current_entries)

    if not entries_by_source:
        return body.replace(
            "\\redactionlog",
            "No redaction entries with justifications were found in the source files.",
        )

    lines: List[str] = []
    entry_num = 1
    for source, entries in entries_by_source.items():
        display = Path(source).stem.replace("_", " ").title()
        for entry in entries:
            justification = entry.get("justification", "")
            if not justification:
                continue

            lines.append(
                f"{entry_num}. *{display}* \u2014 {justification}"
            )
            lines.append("")
            entry_num += 1

    return body.replace("\\redactionlog", "\n".join(lines))


def exhibit_label_for_doctype(doctype: str) -> str:
    """Return the citation word used for attachments in a given doctype.

    Pleadings use "Exhibit"; letters use "Attachment". Both \\exhibit{} and
    \\attachment{} macros resolve to the doctype-appropriate label.
    """
    return "Attachment" if doctype == "letter" else "Exhibit"


def substitute_exhibit_refs(body: str, exhibit_map: Dict[str, Exhibit],
                            doctype: str = "pleading") -> str:
    """Replace \\exhibit{shortname} or \\attachment{shortname} with the
    doctype-appropriate citation (e.g. 'Exhibit A' for pleadings,
    'Attachment A' for letters). If the exhibit has a pages spec,
    appends 'pp. X-Y' to the citation."""
    label = exhibit_label_for_doctype(doctype)

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in exhibit_map:
            raise ValueError(f"Unknown exhibit shortname referenced in body: {key}")
        ex = exhibit_map[key]
        cite = f"{label} {ex.letter}"
        if ex.pages:
            cite += f", {_format_page_citation(ex.pages)}"
        return cite
    return re.sub(r"\\(?:exhibit|attachment)\{([A-Za-z0-9_\-]+)\}", repl, body)


def substitute_date_macro(body: str, meta: Dict) -> str:
    """Replace \\date with the date from YAML metadata."""
    date_str = meta.get("date", "_______________")
    return body.replace("\\date", str(date_str))


def flatten_lettersignblock(body: str) -> str:
    r"""Collapse multi-line \lettersignblock{...} into a single line.

    The block-level parser matches \lettersignblock{...} only when the entire
    macro fits on one source line. This preprocessor lets authors write the
    macro across multiple lines using ``\\`` as a line break inside the braces,
    which renders to a newline-separated name block.

    Input forms accepted:

        \lettersignblock{Name\\Firm\\Role}

        \lettersignblock{Name\\
        Firm\\
        Role}

    Both collapse to a single source line with internal ``\\n`` markers that
    the renderer splits on at draw time.
    """
    def collapse(content: str) -> str:
        content = re.sub(r"\s*\\\\\s*", r"\\n", content)
        content = re.sub(r"\s*\n\s*", " ", content)
        return re.sub(r"\s+", " ", content).strip()

    body = re.sub(
        r"\\lettersignblock\{([^}]*)\}",
        lambda m: "\\lettersignblock{" + collapse(m.group(1)) + "}",
        body, flags=re.DOTALL)
    # The styled spelling accepts the same multi-line form.
    body = re.sub(
        r"\\signblock\{letter\}\{([^}]*)\}",
        lambda m: "\\signblock{letter}{" + collapse(m.group(1)) + "}",
        body, flags=re.DOTALL)
    return body


# CCP § 1010.6 / § 1013a proof-of-service boilerplate lives in editable
# template files, not code (ADR-0010: legal boilerplate text is a decision
# someone revisits). One file per numbered paragraph / clause.
_POSBLOCK_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "posblock"


def _posblock_template(name: str, **fields) -> str:
    text = (_POSBLOCK_TEMPLATE_DIR / f"{name}.md.tmpl").read_text(
        encoding="utf-8").rstrip("\n")
    return text.format(**fields) if fields else text


def substitute_posblock_macro(body: str, meta: Dict) -> str:
    r"""Replace \posblock with an expanded California Proof of Service.

    Reads the ``proof_of_service`` mapping from YAML front matter and
    expands ``\posblock`` (a bare single-line macro) into a complete
    proof-of-service section: a heading, four numbered declaration
    paragraphs, recipient/document lists, the perjury clause, and a
    declaration signature block.

    Schema for ``proof_of_service``:

    .. code-block:: yaml

        proof_of_service:
          method: email          # or "U.S. Mail" / "personal delivery"
          date: "May 8, 2026"    # optional; blank for hand-dating
          documents:
            - "Stipulation for Dismissal With Prejudice"
            - "[Proposed] Order ..."
          recipients:
            - name: "Alex Fenwick, General Manager"
              email: "afenwick@example.org"
              role: "For Respondent Bayside Municipal Transit District"
          server:                # optional; defaults to filer block
            name: "Jane Roe"
            address: "123 Main Street, Springfield, CA 90000"
            email: "jane.roe@example.com"
            city_state: "San Francisco, California"

    Both electronic and non-electronic service are supported. For
    non-electronic methods, ``email`` on each recipient becomes a
    mailing address; the surrounding language adapts.
    """

    if "\\posblock" not in body:
        return body

    pos = meta.get("proof_of_service") or {}
    if not pos:
        raise SystemExit(
            r"\posblock used but no 'proof_of_service:' section found "
            "in YAML front matter."
        )

    method_raw = str(pos.get("method") or "email").strip()
    is_electronic = method_raw.lower() in {"email", "electronic", "e-mail"}

    server = pos.get("server") or {}
    server_name = str(
        server.get("name") or meta.get("filer_name") or ""
    ).strip()
    server_address = str(server.get("address") or "").strip()
    if not server_address:
        addr_lines = [
            str(a).strip()
            for a in (meta.get("filer_address_lines") or [])
            if str(a).strip()
        ]
        server_address = ", ".join(addr_lines)
    server_email = str(
        server.get("email") or meta.get("filer_email") or ""
    ).strip()
    server_city_state = str(server.get("city_state") or "").strip()

    date_raw = pos.get("date")
    date_str = str(date_raw).strip() if date_raw else "_______________"

    documents = list(pos.get("documents") or [])
    recipients = list(pos.get("recipients") or [])
    if not documents:
        raise SystemExit(
            r"\posblock requires 'proof_of_service.documents' to list "
            "at least one document."
        )
    if not recipients:
        raise SystemExit(
            r"\posblock requires 'proof_of_service.recipients' to list "
            "at least one recipient."
        )

    lines: List[str] = []
    lines.append(_posblock_template("opener", server_name=server_name))
    lines.append("")
    lines.append(_posblock_template("server_qualification",
                                    server_address=server_address))
    lines.append("")

    if is_electronic:
        lines.append(_posblock_template("electronic_address",
                                        server_email=server_email))
        lines.append("")
        lines.append(_posblock_template("electronic_service_date",
                                        date=date_str))
    else:
        lines.append(_posblock_template("mail_service_date", date=date_str))

    lines.append("")
    for doc in documents:
        lines.append(f"- {doc}")
    lines.append("")

    if is_electronic:
        item4 = _posblock_template("electronic_delivery")
    else:
        item4 = _posblock_template("other_delivery", method=method_raw)
    lines.append(item4)
    lines.append("")

    for r in recipients:
        name = str(r.get("name") or "").strip()
        email = str(r.get("email") or "").strip()
        addr = str(r.get("address") or "").strip()
        role = str(r.get("role") or "").strip()
        contact = email if is_electronic else (addr or email)
        bullet = f"- {name}"
        if role:
            bullet += f", {role}"
        if contact:
            # Em dash, never spaced: the generator's own boilerplate obeys
            # the house dash rule (generator.md promise 3).
            bullet += f"---{contact}"
        lines.append(bullet)
    lines.append("")

    lines.append(_posblock_template("perjury"))
    lines.append("")

    if server_city_state:
        sigblock = "\\signblock{decl}{" + server_name.upper() + "}{" + server_city_state + "}"
    else:
        sigblock = "\\signblock{decl}{" + server_name.upper() + "}{}"
    lines.append(sigblock)

    return body.replace("\\posblock", "\n".join(lines))


def _parse_table_line(line: str) -> List[str]:
    """Split a markdown table row '| a | b | c |' into ['a', 'b', 'c']."""
    cells = line.split("|")
    # Strip leading empty from initial '|' and trailing empty from final '|'
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _is_table_separator(line: str) -> bool:
    """Check if a line is a markdown table separator like |---|---|."""
    return bool(re.match(r"^\|[\s\-:|]+\|$", line.strip()))


_AUTONUM_RE = re.compile(r"^#\.[ \t]+")


def autonumber_list_items(body: str) -> str:
    """Replace leading ``#. `` sentinels with a running document-wide counter.

    Gives pleadings a flat, auto-incrementing paragraph numbering that does not
    reset at interspersed section headings (unlike the ``###``-heading outline
    numbering, which restarts under each parent heading). Author paragraphs as
    ``#. text``; they render as ``1. text``, ``2. text`` … in source order,
    so inserting or removing a paragraph never desynchronizes the numbering.
    Only lines beginning with the ``#. `` sentinel are affected; blockquote
    sub-items and ordinary text are untouched.
    """
    out: List[str] = []
    n = 0
    for line in body.split("\n"):
        if _AUTONUM_RE.match(line):
            n += 1
            line = _AUTONUM_RE.sub(f"{n}. ", line, count=1)
        out.append(line)
    return "\n".join(out)


_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+?)\]:\s?(.*)$")


def extract_footnote_defs(body: str) -> Tuple[str, Dict[str, str]]:
    """Pull footnote definitions (``[^id]: text``) out of the body.

    A definition may span multiple source lines: indented lines immediately
    following the definition are appended to it. Returns the body with the
    definition lines removed and a mapping ``id -> text``. Footnote
    *references* (``[^id]``) are left in place for inline parsing.
    """
    out_lines: List[str] = []
    defs: Dict[str, str] = {}
    lines = body.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _FOOTNOTE_DEF_RE.match(lines[i])
        if not m:
            out_lines.append(lines[i])
            i += 1
            continue
        fid = m.group(1).strip()
        parts = [m.group(2).strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and lines[i][:1] in (" ", "\t"):
            parts.append(lines[i].strip())
            i += 1
        defs[fid] = normalize_whitespace(" ".join(p for p in parts if p))
    return "\n".join(out_lines), defs


def parse_markdown_blocks(body: str, doctype: str = "pleading") -> List[Block]:
    """Parse a Markdown body into blocks.

    When doctype=="letter", lines matching ``^(\\d+)\\.\\s+`` are parsed as
    numbered-list items (kind="numbered"). In pleadings the same syntax is
    reserved for paragraph numbering and is left inside regular paragraphs.
    """
    lines = body.replace("\r\n", "\n").split("\n")
    blocks: List[Block] = []
    para_lines: List[str] = []
    table_rows: List[List[str]] = []

    bq_lines: List[str] = []
    numbered_lines: List[str] = []
    numbered_level: int = 0

    def flush_blockquote() -> None:
        nonlocal bq_lines
        if bq_lines:
            raw = normalize_whitespace(" ".join(bq_lines))
            raw = typographic_subs(raw)
            if raw:
                spans = parse_inline_styles(raw)
                blocks.append(Block("blockquote", raw, spans=spans))
        bq_lines = []

    def flush_numbered() -> None:
        nonlocal numbered_lines, numbered_level
        if numbered_lines:
            raw = normalize_whitespace(" ".join(numbered_lines))
            raw = typographic_subs(raw)
            if raw:
                spans = parse_inline_styles(raw)
                blocks.append(Block("numbered", raw, spans=spans, level=numbered_level))
        numbered_lines = []
        numbered_level = 0

    def flush_para(keep_blockquote: bool = False) -> None:
        nonlocal para_lines
        # A ``>`` line flushes the paragraph it interrupts but must NOT
        # flush the block quote it is still accumulating -- otherwise every
        # source line becomes its own Block and the quote renders one short
        # line per source line, each followed by the trailing blank a Block
        # emits (i.e. double-spaced). Consecutive ``>`` lines merge.
        if not keep_blockquote:
            flush_blockquote()
        flush_numbered()
        if para_lines:
            raw = normalize_whitespace(" ".join(para_lines))
            raw = typographic_subs(raw)
            if raw:
                spans = parse_inline_styles(raw)
                blocks.append(Block("paragraph", raw, spans=spans))
        para_lines = []

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            # Apply typographic subs to cell contents
            processed = []
            for row in table_rows:
                processed.append([typographic_subs(cell) for cell in row])
            blocks.append(Block("table", "", rows=processed))
        table_rows = []

    in_comment = False
    fw_lines: Optional[List[str]] = None
    for raw_line in lines:
        # \fixedwidth{ ... } collects lines VERBATIM until a lone `}`:
        # no comment stripping, no typographic substitution, no
        # wrapping. A mangled character in an armored block is
        # corruption, not style, so this runs before everything.
        if fw_lines is not None:
            if raw_line.strip() == "}":
                blocks.append(Block("fixedwidth", "\n".join(fw_lines)))
                fw_lines = None
            else:
                fw_lines.append(raw_line.rstrip())
            continue
        if raw_line.strip() == "\\fixedwidth{":
            flush_para()
            fw_lines = []
            continue

        line = raw_line.rstrip()

        # Strip HTML comments (non-rendering annotations for literate-programming style revision notes)
        if in_comment:
            if "-->" in line:
                line = line[line.index("-->") + 3:]
                in_comment = False
                if not line.strip():
                    continue
            else:
                continue
        while "<!--" in line:
            before = line[:line.index("<!--")]
            rest = line[line.index("<!--") + 4:]
            if "-->" in rest:
                line = before + rest[rest.index("-->") + 3:]
            else:
                line = before
                in_comment = True
                break
        if in_comment and not line.strip():
            continue
        line = line.rstrip()

        # Table continuation: accumulate rows, skip separator lines
        if table_rows and line.strip().startswith("|"):
            if not _is_table_separator(line):
                table_rows.append(_parse_table_line(line))
            continue

        # Table start: a line starting with '|' when not already in a table
        if not table_rows and line.strip().startswith("|") and not _is_table_separator(line):
            flush_para()
            table_rows.append(_parse_table_line(line))
            continue

        # Non-table line: flush any accumulated table
        if table_rows:
            flush_table()

        if not line.strip():
            flush_para()
            continue
        m_sign = re.match(r"^\\signblock((?:\{[^{}]*\})+)\s*$", line)
        if m_sign:
            flush_para()
            args = re.findall(r"\{([^{}]*)\}", m_sign.group(1))
            args = [a.strip() for a in args]
            style = args[0] if args and args[0] in SIGNBLOCK_STYLES else None
            if style == "dated":
                blocks.append(Block("signblock", args[1] if len(args) > 1 else "",
                                    spans=[TextSpan(args[2] if len(args) > 2 else "")]))
            elif style == "decl":
                blocks.append(Block("declsignblock", args[1] if len(args) > 1 else "",
                                    spans=[TextSpan(args[2] if len(args) > 2 else ""),
                                           TextSpan(args[3] if len(args) > 3 else "")]))
            elif style == "judge":
                blocks.append(Block("judgesignblock", args[1] if len(args) > 1 else ""))
            elif style == "letter":
                blocks.append(Block("lettersignblock", args[1] if len(args) > 1 else ""))
            elif style == "whereof":
                blocks.append(Block("whereofsignblock", args[1] if len(args) > 1 else "",
                                    spans=[TextSpan(args[2] if len(args) > 2 else ""),
                                           TextSpan(args[3] if len(args) > 3 else "")]))
            else:
                # Legacy bare form \signblock{NAME}{ROLE?} -> dated.
                print(f"WARNING: \\signblock{{{args[0] if args else ''}}} uses the "
                      f"legacy form; write \\signblock{{dated}}{{NAME}}{{ROLE}} "
                      f"(styles: {', '.join(SIGNBLOCK_STYLES)})", file=sys.stderr)
                blocks.append(Block("signblock", args[0] if args else "",
                                    spans=[TextSpan(args[1] if len(args) > 1 else "")]))
            continue
        m_decl = re.match(r"^\\declsignblock\{(.+?)\}\{(.+?)\}(?:\{(.*?)\})?\s*$", line)
        if m_decl:
            flush_para()
            print("WARNING: \\declsignblock is deprecated; write "
                  "\\signblock{decl}{NAME}{LOCATION}{ROLE}", file=sys.stderr)
            role_override = (m_decl.group(3) or "").strip()
            blocks.append(Block("declsignblock", m_decl.group(1).strip(), level=0,
                                spans=[TextSpan(m_decl.group(2).strip()),
                                       TextSpan(role_override)]))
            continue
        m_judge = re.match(r"^\\judgesignblock\{(.+)\}\s*$", line)
        if m_judge:
            flush_para()
            print("WARNING: \\judgesignblock is deprecated; write "
                  "\\signblock{judge}{TITLE}", file=sys.stderr)
            blocks.append(Block("judgesignblock", m_judge.group(1).strip()))
            continue
        m_letter_sign = re.match(r"^\\lettersignblock\{(.+)\}\s*$", line)
        if m_letter_sign:
            flush_para()
            print("WARNING: \\lettersignblock is deprecated; write "
                  "\\signblock{letter}{Name\\\\Firm\\\\Role}", file=sys.stderr)
            blocks.append(Block("lettersignblock", m_letter_sign.group(1).strip()))
            continue
        m_lr = re.match(r"^\\leftright\{(.*?)\}\{(.*?)\}\s*$", line)
        if m_lr:
            flush_para()
            blocks.append(Block("leftright",
                                typographic_subs(m_lr.group(1).strip()),
                                spans=[TextSpan(typographic_subs(m_lr.group(2).strip()))]))
            continue
        m_ctr = re.match(r"^\\center\{(.*?)\}\s*$", line)
        if m_ctr:
            flush_para()
            blocks.append(Block("centerline", typographic_subs(m_ctr.group(1).strip())))
            continue
        m_srow = re.match(r"^\\sigrow\{(.*?)\}\{(.*?)\}\s*$", line)
        if m_srow:
            flush_para()
            blocks.append(Block("sigrow", m_srow.group(1).strip(),
                                spans=[TextSpan(m_srow.group(2).strip())]))
            continue
        m_bar = re.match(r"^\\barcode\{([a-z0-9]+)\}\{(.+?)\}(?:\{(.*?)\})?\s*$", line)
        if m_bar:
            flush_para()
            blocks.append(Block("barcode", m_bar.group(2).strip(),
                                spans=[TextSpan(m_bar.group(1).strip()),
                                       TextSpan((m_bar.group(3) or "").strip())]))
            continue
        m_barfile = re.match(r"^\\barcodefile\{([a-z0-9]+)\}\{(.+?)\}(?:\{(.*?)\})?\s*$", line)
        if m_barfile:
            flush_para()
            blocks.append(Block("barcodefile", m_barfile.group(2).strip(),
                                spans=[TextSpan(m_barfile.group(1).strip()),
                                       TextSpan((m_barfile.group(3) or "").strip())]))
            continue
        m_ack = re.match(r"^\\acknowledgment\{(.*?)\}\s*$", line)
        if m_ack:
            flush_para()
            blocks.append(Block("acknowledgment", m_ack.group(1).strip()))
            continue
        m_jurat = re.match(r"^\\jurat\{(.*?)\}\s*$", line)
        if m_jurat:
            flush_para()
            blocks.append(Block("jurat", m_jurat.group(1).strip()))
            continue
        m_proof = re.match(r"^\\proofofexecution\{(.*?)\}\{(.*?)\}\s*$", line)
        if m_proof:
            flush_para()
            blocks.append(Block("proofexec", m_proof.group(1).strip(),
                                spans=[TextSpan(m_proof.group(2).strip())]))
            continue
        m_watt = re.match(r"^\\witnessattestation\{(.+?)\}\s*$", line)
        if m_watt:
            flush_para()
            blocks.append(Block("witnessattest", m_watt.group(1).strip()))
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            flush_para()
            heading_text = typographic_subs(normalize_whitespace(m.group(2)))
            spans = parse_inline_styles(heading_text)
            blocks.append(Block("heading", heading_text, spans=spans, level=len(m.group(1))))
            continue
        if re.match(r"^>\s?", line):
            flush_para(keep_blockquote=True)
            bq_lines.append(re.sub(r"^>\s?", "", line))
            continue
        if bq_lines:
            flush_blockquote()
        if re.match(r"^[-*]\s+", line):
            flush_para()
            bullet_text = typographic_subs(normalize_whitespace(re.sub(r"^[-*]\s+", "", line)))
            spans = parse_inline_styles(bullet_text)
            blocks.append(Block("bullet", bullet_text, spans=spans))
            continue
        if doctype == "letter":
            m_num = re.match(r"^(\d+)\.\s+(.*)$", line)
            if m_num:
                flush_para()  # also flushes any pending numbered item
                numbered_level = int(m_num.group(1))
                numbered_lines = [m_num.group(2)]
                continue
            if numbered_lines and line[:1] in (' ', '\t'):
                # Indented continuation of a multi-line numbered item.
                numbered_lines.append(line.strip())
                continue
            if numbered_lines:
                flush_numbered()
        para_lines.append(line)

    flush_table()
    flush_para()
    return blocks


def number_headings(blocks: List[Block]) -> List[Block]:
    h1 = h2 = h3 = 0
    out: List[Block] = []
    for b in blocks:
        if b.kind != "heading":
            out.append(b)
            continue
        if b.level == 1:
            h1 += 1; h2 = h3 = 0
            prefix = f"{roman(h1)}."
        elif b.level == 2:
            h2 += 1; h3 = 0
            prefix = f"{alpha(h2)}."
        else:
            h3 += 1
            prefix = f"{h3}."
        new_text = f"{prefix} {b.text}"
        new_spans = [TextSpan(f"{prefix} ", bold=False)] + b.spans
        out.append(Block("heading", new_text, spans=new_spans, level=b.level))
    return out


# ---------------------------------------------------------------------------
# Styled-text line generation for blocks
# ---------------------------------------------------------------------------

def _block_to_styled_lines(block: Block, exhibit_letters: Optional[set] = None,
                           text_width: float = TEXT_WIDTH,
                           footnote_numbers: Optional[Dict[str, int]] = None,
                           ) -> List[Tuple[List[StyledWord], float]]:
    """Return list of (styled_words, indent) tuples for a block, plus a blank separator."""
    if block.kind == "heading":
        indent = 0 if block.level <= 2 else 18
        width = text_width - indent
        words = spans_to_styled_words(block.spans, footnote_numbers)
        for w in words:
            w.bold = True
        if exhibit_letters:
            tag_exhibit_links(words, exhibit_letters)
        wrapped = wrap_styled_words(words, width)
        result = [(line_words, indent) for line_words in wrapped]
        result.append(([], 0))  # blank separator line
        return result

    if block.kind in ("bullet", "numbered"):
        indent = 18
        if block.kind == "bullet":
            prefix = "\u2022  "
        else:
            prefix = f"{block.level}. "
        hanging = pdfmetrics.stringWidth(prefix, FONT_NAME, FONT_SIZE)
        words = spans_to_styled_words(block.spans, footnote_numbers)
        if exhibit_letters:
            tag_exhibit_links(words, exhibit_letters)
        # The prefix stays its own word (regular font) so the first content
        # word keeps ALL of its style flags -- merging them into one
        # StyledWord used to drop mono/underline/highlight on the lead word.
        # no_space_before glues the pair, so the prefix's own trailing
        # spaces set the gap and the hanging indent still lines up.
        prefix_word = StyledWord(prefix)
        if words:
            words[0].no_space_before = True
        all_words = [prefix_word] + words
        lines_out: List[Tuple[List[StyledWord], float]] = []
        space_w = pdfmetrics.stringWidth(" ", FONT_NAME, FONT_SIZE)
        first_line = True
        max_w = text_width - indent

        clusters = glue_clusters(all_words)
        current = list(clusters[0])
        cur_w = sum(w.width() for w in current)
        for cluster in clusters[1:]:
            cw = sum(w.width() for w in cluster)
            trial = cur_w + space_w + cw
            if trial <= max_w:
                current.extend(cluster)
                cur_w = trial
            else:
                lines_out.append((current, indent if first_line else indent + hanging))
                current = list(cluster)
                cur_w = cw
                first_line = False
                max_w = text_width - indent - hanging
        lines_out.append((current, indent if first_line else indent + hanging))
        lines_out.append(([], 0))
        return lines_out

    if block.kind == "blockquote":
        indent = 36
        words = spans_to_styled_words(block.spans, footnote_numbers)
        if exhibit_letters:
            tag_exhibit_links(words, exhibit_letters)
        wrapped = wrap_styled_words(words, text_width - indent)
        result = [(line_words, indent) for line_words in wrapped]
        result.append(([], 0))
        return result

    # paragraph
    words = spans_to_styled_words(block.spans, footnote_numbers)
    if exhibit_letters:
        tag_exhibit_links(words, exhibit_letters)
    wrapped = wrap_styled_words(words, text_width)
    result = [(line_words, 0.0) for line_words in wrapped]
    result.append(([], 0))
    return result


# ---------------------------------------------------------------------------
# PDF generation — shared pleading-paper chrome (line numbers, footer)
# ---------------------------------------------------------------------------

def draw_grid_line_numbers(c: canvas.Canvas, line_y, lines_per_page: int) -> None:
    """Draw the 1..N line numbers and the vertical rule at 1.125".

    ``line_y`` maps a 1-based line number to its baseline y. Shared by
    PleadingPDF (body pages) and LineGridPDF (exhibit list pages).
    """
    c.setFont(FONT_NAME, FONT_SIZE_SMALL)
    for i in range(1, lines_per_page + 1):
        c.drawRightString(LINE_NUM_X, line_y(i), str(i))
    c.line(LINE_RULE_X, line_y(1) + LINE_RULE_TOP_OVERHANG,
           LINE_RULE_X, line_y(lines_per_page) - LINE_RULE_BOTTOM_OVERHANG)


FRONT_MATTER_KEYS_FILE = Path(__file__).resolve().parent / "front_matter_keys.yaml"
# Local modules (ADR-0032): a deployment's extra keys live in the
# gitignored local/ overlay and merge into the recognized set.
LOCAL_FRONT_MATTER_KEYS_FILE = (Path(__file__).resolve().parent.parent
                                / "local" / "pleading" / "front_matter_keys.yaml")

_warned_unknown_keys: set = set()


def recognized_front_matter_keys() -> set:
    """Every top-level key the generator understands, from the schema file
    plus the local/ overlay's additions when present."""
    keys = set()
    for schema in (FRONT_MATTER_KEYS_FILE, LOCAL_FRONT_MATTER_KEYS_FILE):
        try:
            groups = yaml.safe_load(schema.read_text()) or {}
        except OSError:
            continue
        for names in groups.values():
            keys.update(names or [])
    return keys


def warn_unknown_front_matter_keys(meta: Dict, source_name: str) -> None:
    """Say so when a source sets a key nothing reads.

    A warning, never an error. An unrecognized key means the author
    expected something that will not happen — worth saying out loud,
    not worth refusing to build a filing over. `plain: true` is the
    case in point: it sat in six sources for months, did nothing, and
    nothing ever said so, because the renderer simply ignored what it
    did not recognize.

    Top level only. `forms:` holds per-descriptor field names owned by
    the form registry, and the structured lists validate themselves.
    """
    recognized = recognized_front_matter_keys()
    if not recognized:
        return
    # Underscore keys are the build system's own (e.g. _final, set by
    # the --final flag after sources are stripped of it); the warning
    # is about keys an AUTHOR wrote that nothing reads.
    unknown = sorted(k for k in meta if k not in recognized and not k.startswith("_"))
    for key in unknown:
        token = (source_name, key)
        if token in _warned_unknown_keys:
            continue
        _warned_unknown_keys.add(token)
        print(
            f"WARNING: {source_name}: front-matter key `{key}` is not read by "
            f"anything and has no effect.\n"
            f"         Recognized keys: pleading/front_matter_keys.yaml. If it "
            f"is a note for a human, make it a comment.",
            file=sys.stderr, flush=True,
        )


def suppresses_caption(meta: Dict) -> bool:
    """Whether this source renders without the standalone-pleading caption.

    `no_caption:` is the key. `plain:` is accepted because six sources
    across two matters already said it, believing it worked — it never
    did. Nothing read the key, so the renderer put a full caption on
    every JC-form attachment, every rebuild, and the fix looked like an
    agent that would not follow instructions rather than a config key
    that was never wired up. Honoring it retroactively makes those
    sources correct without a migration anyone has to remember.

    `cover_sheet_only:` also counts, and does not need `no_caption:`
    alongside it: a cover_sheet_only source never builds a body page at
    all, so there is no caption-rendering code path for the key to
    suppress in the first place. Requiring it would just be a second
    flag saying the same thing the first one already guarantees.
    """
    if meta.get("cover_sheet_only"):
        return True
    if meta.get("no_caption"):
        return True
    if meta.get("plain"):
        print(
            "WARNING: `plain:` is the old spelling of `no_caption:` and was "
            "silently ignored until now. It works, but rename it.",
            file=sys.stderr, flush=True,
        )
        return True
    return False


#: Cover sheets whose accompanying prose is always a continuation of a
#: numbered item on the form, never a document of its own. SUBP-010
#: item 3 literally reads "described in Attachment 3", so whatever
#: follows it *is* Attachment 3; on SUBP-002 the records demand is
#: declaration item 2 and continues on Attachment 2.
ATTACHMENT_COVER_SHEETS = {"subp002", "subp010", "subp025"}


def form_display_id(form_id: str) -> str:
    """`subp010` -> `SUBP-010`: the id a clerk, a caption, and the
    Judicial Council itself use, rather than the registry's filename
    spelling.

    Registry ids are lowercase and unpunctuated because they are also
    filenames; every JC id is letters then digits, so one rule restores
    the hyphen for all of them.
    """
    return re.sub(r"^([A-Za-z]+)-?(\d+)$", r"\1-\2", form_id).upper()


def is_form_attachment(meta: Dict) -> bool:
    """Whether this source is a continuation of a JC form item.

    Two signals, either sufficient. A `paper_title` that begins
    "ATTACHMENT" is the document describing itself. A subpoena cover
    sheet settles it regardless of title.

    Note what this deliberately does NOT catch: a declaration behind a
    motion's own cover form. That is a distinct document incorporated by it,
    and California practice captions it normally. The rule here is
    about text that continues a form, not about everything that
    happens to sit behind one.
    """
    title = str(meta.get("paper_title") or "").strip().upper()
    if title.startswith("ATTACHMENT"):
        return True
    return str(meta.get("cover_sheet") or "").lower() in ATTACHMENT_COVER_SHEETS


def require_attachment_has_no_caption(meta: Dict, source_name: str) -> None:
    """A form attachment is not a standalone pleading, and must not look like one.

    An attachment to a Judicial Council form continues that form. It
    does not reintroduce the attorney block, the court name, or the
    two-column party caption — the form carried all of it one page
    earlier, and repeating it presents the attachment as a separate
    paper that was separately filed. It is not; it has no independent
    existence.

    A hard error rather than a warning because this is the exact
    mistake that kept coming back. It was pointed out repeatedly,
    corrected by hand, and reintroduced on the next rebuild — because
    the only thing standing against it was that somebody would notice.
    """
    if not is_form_attachment(meta) or suppresses_caption(meta):
        return
    why = (f"`cover_sheet: {meta['cover_sheet']}`"
           if str(meta.get("cover_sheet") or "").lower() in ATTACHMENT_COVER_SHEETS
           else f"a paper_title beginning \"ATTACHMENT\"")
    raise SystemExit(
        f"{source_name}: this source has {why}, so it is a continuation of "
        f"a Judicial Council form — but it has no `no_caption: true`, so it "
        f"would print the attorney block, court name and party caption as "
        f"though it were a standalone pleading.\n\n"
        f"An attachment continues the form; the form already carried the "
        f"caption. Add `no_caption: true` to the front matter.\n\n"
        f"If this really is a standalone document that merely travels "
        f"behind a form (a declaration attached to a motion's cover form, "
           f"say), give it "
        f"a paper_title that does not begin \"ATTACHMENT\"."
    )


def require_cover_sheet_only_has_cover_sheet(meta: Dict, source_name: str) -> None:
    """`cover_sheet_only: true` has nothing to output without a form.

    The flag exists so a source that is solely a filled Judicial
    Council form -- MC-050 Substitution of Attorney, say, with no
    accompanying declaration or motion text -- can skip the otherwise
    automatic, mostly-blank body page. That only makes sense when a
    `cover_sheet:` names the form that becomes the entire output;
    without one there is no document at all.
    """
    if meta.get("cover_sheet_only") and not meta.get("cover_sheet"):
        raise SystemExit(
            f"{source_name}: `cover_sheet_only: true` requires "
            f"`cover_sheet: <form_id>` alongside it -- with no cover "
            f"sheet, this source has nothing to output."
        )


# Every build is a draft until someone says otherwise (--final): the
# rendered artifact is what circulates, and an unmarked draft is the
# accident waiting to happen. Per-doctype defaults, because "not
# filed", "not executed", and "not sent" are different facts.
DEFAULT_DRAFT_BANNER = {
    "pleading": "DRAFT—NOT FILED",
    "document": "DRAFT—NOT EXECUTED",
    "letter": "DRAFT—NOT SENT",
}
# PDF metadata key stamped alongside the banner, so outbound tooling
# (sc docuseal) can refuse a draft deterministically whatever the text.
DRAFT_METADATA_KEY = "/ProsaicDraftBanner"


def draft_banner_text(meta: Dict) -> Optional[str]:
    """The banner a not-yet-real document carries, or None.

    Driven by the `notreal:` marker, which until now was a note to
    readers of the *source* and left no trace in the rendered PDF. The
    output is the dangerous artifact: a draft declaration and a filed
    one are the same object on screen and on paper, and the difference
    between them is not recoverable by looking. So the marker prints.

    The banner is the marker's own words, upper-cased, so it says why
    the document is not real rather than a generic "DRAFT" — "not
    filed" and "not sent" are different facts, and a simulation is a
    third thing. Removing `notreal:` is what clears the banner, which
    makes clearing it a deliberate act by someone who knows the
    document is going out.
    """
    if meta.get("_final"):
        # Set only by the build system's --final flag (main() strips
        # any front-matter attempt): suppression is a per-invocation
        # act, never a property a source can grant itself.
        return None
    marker = meta.get("notreal")
    if marker is None:
        doctype = str(meta.get("doctype", "pleading"))
        return DEFAULT_DRAFT_BANNER.get(doctype, "DRAFT")
    text = typographic_subs(str(marker)).strip().upper()
    # `notreal:` markers predate being rendered, so they are written
    # however their author felt — usually with spaces around the dash.
    # The banner is output, and output obeys the dash rule.
    text = re.sub(r"\s*—\s*", "—", text)
    text = re.sub(r"\s+", " ", text)
    return text or None


def draw_draft_banner(c: canvas.Canvas, text: Optional[str],
                      page_width: float = PAGE_WIDTH,
                      page_height: float = PAGE_HEIGHT) -> None:
    """Draw the not-yet-real banner in a page's top margin, in red.

    Sits above the line-number rule's overhang, so it occupies margin
    nothing else uses and cannot displace a line of the 28-line grid —
    a banner that reflowed the body would change pagination between a
    draft and its filed version, which is exactly the sort of surprise
    it exists to prevent.

    Shrinks to fit rather than wrapping, for the same reason: one line,
    always, whatever the marker says.
    """
    if not text:
        return
    size = DRAFT_BANNER_FONT_SIZE
    max_width = page_width - 2 * RIGHT_MARGIN
    while (size > DRAFT_BANNER_MIN_FONT_SIZE
           and pdfmetrics.stringWidth(text, FONT_NAME_BOLD, size) > max_width):
        size -= 0.5
    c.setFont(FONT_NAME_BOLD, size)
    c.setFillColorRGB(*DRAFT_BANNER_COLOR)
    c.drawCentredString(page_width / 2,
                        page_height - (PAGE_HEIGHT - DRAFT_BANNER_Y),
                        text)
    c.setFillColor(black)


def _banner_layout(text: str, page_width: float) -> Tuple[List[str], float]:
    """Fit the banner to the page: shrink first, then wrap.

    Markers are prose, and useful ones get long — "DRAFT---not served
    as of August 8, 2026; AT&T Mobility LLC registered-agent address
    must be verified against CA SOS bizfile before service" is 133
    characters and does not fit on one line at any legible size. An
    earlier version shrank to a floor and then drew anyway, running off
    both edges: the page rendered "RAFT—…SERVIC", losing the word that
    matters most at the very start.

    So: shrink to the floor, and if it still does not fit, wrap.
    """
    max_width = page_width - 2 * RIGHT_MARGIN
    size = DRAFT_BANNER_FONT_SIZE
    while (size > DRAFT_BANNER_MIN_FONT_SIZE
           and pdfmetrics.stringWidth(text, FONT_NAME_BOLD, size) > max_width):
        size -= 0.5
    if pdfmetrics.stringWidth(text, FONT_NAME_BOLD, size) <= max_width:
        return ([text], size)
    return (wrap_text(text, max_width, FONT_NAME_BOLD, size), size)


def stamp_draft_banner(pdf_path: Path, text: Optional[str]) -> None:
    """Stamp the banner onto **every** page of an assembled document.

    Done here, over the finished PDF, rather than by each page-drawing
    class, because a packet is not only the pages this generator draws.
    A deposition subpoena is a filled SUBP-010 cover sheet, then the
    attachment, then exhibits — and the cover sheet is the page that
    looks most like something ready to serve. Stamping only what the
    renderer drew left page 1 clean and pages 3 onward marked, which is
    worse than not marking at all: it reads as a deliberate statement
    that the form is final.

    That means the stamp lands on mandatory Judicial Council forms and
    on copies of third-party exhibits. Both are intentional. The form
    is not being altered for filing — the banner exists precisely
    because the document is *not* being filed, and it goes away when
    `notreal:` does. An exhibit page carrying it says "this copy is
    part of a draft packet," which is true and is the point.

    The band is *reclaimed*, not overlaid. A pleading page has an inch
    of unused top margin; a Judicial Council form has none — its own
    header starts a quarter inch from the paper edge, and a banner
    drawn there lands on top of "ATTORNEY OR PARTY WITHOUT ATTORNEY"
    and makes both unreadable. So every page's content is scaled down
    by a few percent, anchored at the bottom and centred, and the
    banner goes in the strip that frees up. Uniform, and it cannot
    collide with anything on any page whatever the page holds.

    Pagination is untouched — this happens after rendering, so nothing
    reflows and a page-and-line citation taken against the draft still
    finds the same words on the same line of the same page.
    """
    if not text or not pdf_path.exists():
        return
    from pypdf import Transformation

    reader = PdfReader(str(pdf_path))
    # clone_from, not a fresh writer: a consumer notice is a filled JC
    # form, and its values live in the document-level /AcroForm. A new
    # writer takes the pages and leaves that behind, which blanks every
    # field on the notice — the stamp would silently gut the document
    # it was meant to label.
    writer = PdfWriter(clone_from=reader)

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    geometry = []
    for page in reader.pages:
        # Honor each page's own geometry: exhibits are scaled onto
        # letter pages today, but nothing guarantees that forever, and
        # a banner off the edge of the paper is a banner nobody sees.
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if (int(page.get("/Rotate", 0) or 0) // 90) % 2 == 1:
            width, height = height, width
        lines, size = _banner_layout(text, width)
        band = DRAFT_BANNER_BAND + (len(lines) - 1) * (size + 2)
        scale = (height - band) / height
        tx = (1 - scale) * width / 2
        geometry.append((scale, tx))
        c.setPageSize((width, height))
        c.setFont(FONT_NAME_BOLD, size)
        c.setFillColorRGB(*DRAFT_BANNER_COLOR)
        y = height - band + 6 + (len(lines) - 1) * (size + 2)
        for line in lines:
            c.drawCentredString(width / 2, y, line)
            y -= size + 2
        c.showPage()
    c.save()
    buf.seek(0)

    overlay = PdfReader(buf)
    # Machine-readable twin of the visual stamp: outbound tools (sc
    # docuseal send) refuse a PDF carrying this key unless overridden.
    writer.add_metadata({DRAFT_METADATA_KEY: text})
    for i, page in enumerate(writer.pages):
        scale, tx = geometry[i]
        page.add_transformation(Transformation().scale(scale).translate(tx, 0))
        # The content stream moved; annotation rectangles do not follow
        # it on their own, and a link, a form widget, or a redaction
        # label left at its old coordinates is worse than no banner.
        _transform_annotations(page, scale, tx, 0)
        page.merge_page(overlay.pages[i])
    with open(pdf_path, "wb") as f:
        writer.write(f)


def draw_pleading_footer(c: canvas.Canvas, page_num: int, footer_title: str) -> None:
    """Draw the CRC 2.110 footer: rule, centered page number, wrapped title.

    Shared by PleadingPDF (non-letter pages) and LineGridPDF.
    """
    c.setLineWidth(0.5)
    c.line(LEFT_MARGIN, FOOTER_RULE_Y, PAGE_WIDTH - RIGHT_MARGIN, FOOTER_RULE_Y)
    c.setFont(FONT_NAME, FONT_SIZE_SMALL)
    c.drawCentredString(CENTER_X, PAGE_NUM_Y, str(page_num))
    footer_max_width = (PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
                        - FOOTER_TITLE_SIDE_INSET)
    y = FOOTER_TITLE_Y
    for line in wrap_text(footer_title, footer_max_width, FONT_NAME,
                          FONT_SIZE_SMALL):
        c.drawCentredString(CENTER_X, y, line)
        y -= FOOTER_TITLE_LEADING


# ---------------------------------------------------------------------------
# PDF generation — pleading body
# ---------------------------------------------------------------------------

class PleadingPDF:
    def __init__(self, meta: Dict, body_blocks: List[Block], output_path: str,
                 exhibit_letters: Optional[set] = None,
                 sign_name: Optional[str] = None,
                 sign_date: Optional[datetime.date] = None,
                 footnote_defs: Optional[Dict[str, str]] = None) -> None:
        self.meta = meta
        self.blocks = body_blocks
        self.output_path = output_path
        self.exhibit_letters = exhibit_letters or set()
        self.sign_name = sign_name
        self.sign_date = sign_date
        self.is_letter = meta.get("doctype") == "letter"
        self.is_document = meta.get("doctype") == "document"
        # Documents share the letter geometry: same margins, same
        # single-spaced leading — they differ only in the header.
        plain = self.is_letter or self.is_document
        self.left_margin = LETTER_LEFT_MARGIN if plain else LEFT_MARGIN
        self.text_width = LETTER_TEXT_WIDTH if plain else TEXT_WIDTH
        self.leading = LETTER_LEADING if plain else LEADING
        self.lines_per_page = LETTER_LINES_PER_PAGE if plain else LINES_PER_PAGE
        self.c = canvas.Canvas(output_path, pagesize=letter)
        self.c.setTitle(meta.get("paper_title", "Pleading"))
        # The footer always carries the caption's paper title (spec:
        # pleading_markdown_spec.md schema; CRC 2.110). `short_title` is a JC
        # cover-form key (jc_common.py) and never overrides the footer.
        self.footer_title = typographic_subs(
            meta.get("paper_title", "Pleading")).upper()
        self.draft_banner = draft_banner_text(meta)
        self.page_num = 0
        self.link_rects: List[LinkRect] = []
        self.esign_fields: List[Dict] = []  # sidecar e-sign fields (points, top-left origin)

        # Footnotes: assign numbers in document (reading) order, then cache
        # wrapped text. Per-page state tracks which notes land on the current
        # page and how many grid lines they reserve at the page bottom.
        # Only *defined* ids get numbers: a reference with no matching
        # definition falls through spans_to_styled_words' literal-marker
        # fallback and renders as "[^id]" so the error is visible.
        self.footnote_defs = footnote_defs or {}
        self.footnote_numbers: Dict[str, int] = {}
        for block in self.blocks:
            for span in block.spans:
                fid = getattr(span, "footnote_id", None)
                if (fid is not None and fid in self.footnote_defs
                        and fid not in self.footnote_numbers):
                    self.footnote_numbers[fid] = len(self.footnote_numbers) + 1
        self._footnote_lines_cache: Dict[int, List[List[StyledWord]]] = {}
        self._page_fn_nums: List[int] = []
        self._fn_area_lines: int = 0
        # DocuSeal signer roles, assigned in document order across
        # signature blocks and witness grids (ADR-0027).
        self._esign_role = 0

    def line_y(self, line_no: int) -> float:
        return TOP_FIRST_LINE - (line_no - 1) * self.leading

    def draw_line_numbers(self) -> None:
        draw_grid_line_numbers(self.c, self.line_y, self.lines_per_page)

    def draw_footer(self) -> None:
        if self.is_letter or self.is_document:
            self.c.setFont(FONT_NAME, FONT_SIZE_SMALL)
            self.c.drawCentredString(CENTER_X, LETTER_PAGE_NUM_Y, str(self.page_num))
        else:
            draw_pleading_footer(self.c, self.page_num, self.footer_title)

    def start_page(self) -> None:
        if self.page_num > 0:
            self._render_page_footnotes()
            self.c.showPage()
        self.page_num += 1
        self._page_fn_nums = []
        self._fn_area_lines = 0
        self.c.setStrokeColor(black)
        self.c.setFillColor(black)
        if not (self.is_letter or self.is_document):
            self.draw_line_numbers()
        self.draw_footer()
        # The `notreal:` banner is NOT drawn here. It is stamped over
        # the finished document (stamp_draft_banner), so it reaches the
        # JC cover sheet and the exhibits too, and so there is one
        # implementation rather than one per page-drawing class.

    def _footnote_wrapped(self, num: int) -> List[List[StyledWord]]:
        """Lazily wrap a footnote's text (small font), incl. its leading marker."""
        if num in self._footnote_lines_cache:
            return self._footnote_lines_cache[num]
        fid = next((k for k, v in self.footnote_numbers.items() if v == num), None)
        text = self.footnote_defs.get(fid, "") if fid is not None else ""
        raw = typographic_subs(text)
        words = spans_to_styled_words(parse_inline_styles(raw), self.footnote_numbers)
        words = [StyledWord(str(num), superscript=True)] + words
        lines = wrap_styled_words(words, self.text_width, FONT_SIZE_SMALL)
        self._footnote_lines_cache[num] = lines
        return lines

    def _fn_area_for(self, nums: List[int]) -> int:
        """Grid lines reserved at page bottom for the given footnotes.

        One spacer line for the separator rule, plus one line per wrapped
        footnote text line.
        """
        if not nums:
            return 0
        return 1 + sum(len(self._footnote_wrapped(n)) for n in nums)

    def _render_page_footnotes(self) -> None:
        if not self._page_fn_nums:
            return
        area = self._fn_area_for(self._page_fn_nums)
        sep_line = self.lines_per_page - area + 1
        rule_y = self.line_y(sep_line) + FONT_SIZE_SMALL * FOOTNOTE_RULE_RISE_FRAC
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(black)
        self.c.line(self.left_margin, rule_y,
                    self.left_margin + FOOTNOTE_RULE_LENGTH, rule_y)
        ln = sep_line + 1
        for num in self._page_fn_nums:
            for line_words in self._footnote_wrapped(num):
                if line_words:
                    draw_styled_words(self.c, self.left_margin, self.line_y(ln),
                                      line_words, font_size=FONT_SIZE_SMALL)
                ln += 1

    def draw_text_line(self, line_no: int, text: str, indent: float = 0,
                       font: str = FONT_NAME, size: int = FONT_SIZE) -> None:
        self.c.setFont(font, size)
        self.c.drawString(self.left_margin + indent, self.line_y(line_no), text)

    def draw_styled_line(self, line_no: int, words: List[StyledWord], indent: float = 0) -> None:
        rects = draw_styled_words(self.c, self.left_margin + indent, self.line_y(line_no), words)
        for lx, lw, ly, dest in rects:
            self.link_rects.append(LinkRect(
                page_index=self.page_num - 1, x=lx, y=ly - 2,
                width=lw, height=FONT_SIZE + 4, dest=dest,
            ))

    def _draw_caption_text(self, x: float, y: float, text: str,
                           font: str = FONT_NAME, size: int = FONT_SIZE) -> None:
        self.c.setFont(font, size)
        self.c.drawString(x, y, text)

    def _draw_right_aligned(self, line_no: int, text: str,
                            font: str = FONT_NAME, size: int = FONT_SIZE) -> None:
        self.c.setFont(font, size)
        x = PAGE_WIDTH - RIGHT_MARGIN - pdfmetrics.stringWidth(text, font, size)
        self.c.drawString(x, self.line_y(line_no), text)

    def _letter_header(self) -> int:
        """Render the first-page header for doctype=letter."""
        cur = 1

        # From block (right-aligned, wrapped if needed). Header metadata is
        # YAML and bypasses the markdown pipeline; apply typographic_subs so
        # it renders the same as body text.
        from_lines = [
            self.meta["filer_name"],
            *[str(a) for a in self.meta["filer_address_lines"]],
        ]
        if self.meta.get("filer_phone"):
            from_lines.append(self.meta["filer_phone"])
        if self.meta.get("filer_email"):
            from_lines.append(self.meta["filer_email"])
        from_lines = [typographic_subs(str(t)) for t in from_lines]
        for text in from_lines:
            for wrapped in wrap_text(text, self.text_width, FONT_NAME, FONT_SIZE):
                self._draw_right_aligned(cur, wrapped)
                cur += 1
        cur += 2  # blank

        # To block (left-aligned, wrapped if needed)
        to_lines = [
            typographic_subs(str(t)) for t in (
                self.meta["to_name"],
                *[str(a) for a in self.meta["to_address_lines"]],
            )
        ]
        for text in to_lines:
            for wrapped in wrap_text(text, self.text_width, FONT_NAME, FONT_SIZE):
                self.draw_text_line(cur, wrapped)
                cur += 1
        cur += 1  # blank

        # Date (left-aligned, below recipient)
        date_str = _format_letter_date(self.meta.get("date", "_______________"))
        self.draw_text_line(cur, date_str)
        cur += 1

        # Service method (if specified)
        service_method = self.meta.get("service_method")
        if service_method:
            self.draw_text_line(cur, str(service_method), font=FONT_NAME_BOLD, size=FONT_SIZE)
            cur += 1
        cur += 1  # blank

        # Re: line (wrap if title is long)
        re_label = "Re: " + typographic_subs(self.meta["paper_title"])
        re_lines = wrap_text(re_label, self.text_width, FONT_NAME_BOLD, FONT_SIZE)
        for rl in re_lines:
            self.draw_text_line(cur, rl, font=FONT_NAME_BOLD, size=FONT_SIZE)
            cur += 1
        cur += 1  # blank after re line

        return cur

    def _document_header(self) -> int:
        """A plain document opens with its centered bold title."""
        title = typographic_subs(str(self.meta["paper_title"]))
        cur = 1
        for line in wrap_text(title.upper(), self.text_width,
                              FONT_NAME_BOLD, FONT_SIZE):
            self.c.setFont(FONT_NAME_BOLD, FONT_SIZE)
            self.c.drawCentredString(CENTER_X, self.line_y(cur), line)
            cur += 1
        return cur + 1

    def first_page_caption_end_line(self) -> int:
        if self.is_document:
            return self._document_header()
        if self.is_letter:
            return self._letter_header()

        if suppresses_caption(self.meta):
            return 1

        cur = 1  # current grid line number

        # --- Caption geometry (per-document overrides) ---
        # caption_divider_shift: points to shift the ")" divider column to the
        # right of its default position. Useful when a long party name (e.g. a
        # federal agency) would otherwise wrap onto too many lines in the left
        # column. Defaults to 0 (the legacy geometry).
        divider_shift = float(self.meta.get("caption_divider_shift", 0) or 0)
        paren_x = PAREN_X + divider_shift
        right_col_x = paren_x + 18
        right_col_width = PAGE_WIDTH - RIGHT_MARGIN - right_col_x
        left_col_width = paren_x - LEFT_MARGIN - 12

        # --- Filer block — compact within lines 1‑N, sub-grid spacing ---
        # Caption metadata is YAML, so it bypasses the markdown pipeline;
        # apply typographic_subs here so `--`/quotes render the same as in
        # the body (mirrors the exhibit-title handling in _parse_exhibits).
        filer_items: List[str] = [
            typographic_subs(str(item)) for item in (
                self.meta["filer_name"],
                *[str(a) for a in self.meta["filer_address_lines"]],
                self.meta["filer_phone"],
                self.meta["filer_email"],
            )
        ]
        # The filer block sits above the caption with nothing to its right, so
        # it may use the full text width; wrap only truly long lines.
        filer_width = self.text_width
        filer_rendered: List[str] = []
        for raw in filer_items:
            filer_rendered.extend(wrap_text(raw, filer_width, FONT_NAME, FONT_SIZE))
        n_filer = len(filer_rendered)
        # Allocate enough grid lines so that items are at least
        # FILER_BLOCK_TARGET_LEADING pt apart. ceil((n-1)*lead / LEADING)
        # gives the number of grid-line spans needed; add 1 so the first
        # item sits on a grid line baseline.
        filer_grid_span = max(
            FILER_BLOCK_MIN_GRID_SPAN,
            math.ceil(max(n_filer - 1, 1) * FILER_BLOCK_TARGET_LEADING / LEADING) + 1)
        filer_leading = (filer_grid_span - 1) * LEADING / max(n_filer - 1, 1)
        fy = self.line_y(cur)
        for i, text in enumerate(filer_rendered):
            self._draw_caption_text(LEFT_MARGIN, fy - i * filer_leading, text)
        cur += filer_grid_span

        # --- Filer role ---
        role_text = typographic_subs(self.meta["filer_role"]).upper()
        self._draw_caption_text(LEFT_MARGIN, self.line_y(cur), role_text)
        cur += 2

        # --- Court name (centered, bold) ---
        self.c.setFont(FONT_NAME_BOLD, FONT_SIZE)
        self.c.drawCentredString(CENTER_X, self.line_y(cur),
                                 typographic_subs(self.meta["court_name"]))
        cur += 1
        self.c.drawCentredString(CENTER_X, self.line_y(cur),
                                 typographic_subs(self.meta["court_county"]))
        cur += 2

        # --- Two-column caption table ---
        table_start = cur
        label_indent = 36

        left_lines: List[Tuple[str, str, float]] = []
        for wrapped in wrap_text(typographic_subs(self.meta["petitioner"]),
                                 left_col_width, FONT_NAME_BOLD, FONT_SIZE):
            left_lines.append((wrapped, FONT_NAME_BOLD, 0))
        cap_first = self.meta.get("caption_first_party_label", "Petitioner")
        cap_second = self.meta.get("caption_second_party_label", "Respondent")
        # caption_versus_label: "vs." (California default) or "v." (federal).
        versus_label = self.meta.get("caption_versus_label", "vs.")
        left_lines.append(("", FONT_NAME, 0))
        left_lines.append((f"{cap_first},", FONT_NAME, label_indent))
        left_lines.append(("", FONT_NAME, 0))
        left_lines.append((versus_label, FONT_NAME_BOLD, label_indent - 12))
        left_lines.append(("", FONT_NAME, 0))
        for wrapped in wrap_text(typographic_subs(self.meta["respondent"]),
                                 left_col_width, FONT_NAME_BOLD, FONT_SIZE):
            left_lines.append((wrapped, FONT_NAME_BOLD, 0))
        left_lines.append(("", FONT_NAME, 0))
        left_lines.append((f"{cap_second}.", FONT_NAME, label_indent))

        right_lines: List[Tuple[str, str, float]] = []
        case_num = typographic_subs(
            str(self.meta.get("case_number", "_______________")))
        right_lines.append((f"Case No.: {case_num}", FONT_NAME, 0))
        right_lines.append(("", FONT_NAME, 0))

        title_text = typographic_subs(self.meta["paper_title"]).upper()
        for wrapped in wrap_text(title_text, right_col_width, FONT_NAME_BOLD, FONT_SIZE):
            right_lines.append((wrapped, FONT_NAME_BOLD, 0))

        subtitle = self.meta.get("paper_subtitle")
        if subtitle:
            right_lines.append(("", FONT_NAME, 0))
            for wrapped in wrap_text(typographic_subs(str(subtitle)),
                                     right_col_width, FONT_NAME, FONT_SIZE):
                right_lines.append((wrapped, FONT_NAME, 0))

        statutory_basis = self.meta.get("statutory_basis")
        if statutory_basis:
            right_lines.append(("", FONT_NAME, 0))
            for wrapped in wrap_text(typographic_subs(str(statutory_basis)),
                                     right_col_width, FONT_NAME, FONT_SIZE):
                right_lines.append((wrapped, FONT_NAME, 0))

        hearing_bits: List[str] = []
        for key, label in [("hearing_date", "Date"), ("hearing_time", "Time"),
                           ("hearing_dept", "Dept."), ("judge", "Judge")]:
            if self.meta.get(key):
                hearing_bits.append(
                    f"{label}: {typographic_subs(str(self.meta[key]))}")
        if hearing_bits:
            right_lines.append(("", FONT_NAME, 0))
            for bit in hearing_bits:
                wrapped_lines = wrap_text(bit, right_col_width, FONT_NAME, FONT_SIZE)
                if not wrapped_lines:
                    right_lines.append((bit, FONT_NAME, 0))
                    continue
                # First line at indent 0 (contains the "Date:"/"Time:"/etc. label);
                # continuation lines indented so the wrapped text aligns under the value,
                # not under the label.
                right_lines.append((wrapped_lines[0], FONT_NAME, 0))
                for continuation in wrapped_lines[1:]:
                    right_lines.append((continuation, FONT_NAME, 10))

        concurrent = self.meta.get("concurrent_filings")
        if concurrent and isinstance(concurrent, list):
            right_lines.append(("", FONT_NAME, 0))
            right_lines.append(("Filed concurrently with:", FONT_NAME, 0))
            for item in concurrent:
                bullet_text = f"\u2022  {typographic_subs(str(item))}"
                wrapped_lines = wrap_text(bullet_text, right_col_width - 10, FONT_NAME, FONT_SIZE)
                if not wrapped_lines:
                    right_lines.append((bullet_text, FONT_NAME, 10))
                    continue
                right_lines.append((wrapped_lines[0], FONT_NAME, 10))
                for continuation in wrapped_lines[1:]:
                    right_lines.append((continuation, FONT_NAME, 22))

        num_rows = max(len(left_lines), len(right_lines))
        self.c.setFont(FONT_NAME, FONT_SIZE)

        for row in range(num_rows):
            y = self.line_y(table_start + row)
            if row < len(left_lines):
                text, font, indent = left_lines[row]
                if text:
                    self._draw_caption_text(LEFT_MARGIN + indent, y, text, font=font)
            self._draw_caption_text(paren_x, y, ")")
            if row < len(right_lines):
                text, font, indent = right_lines[row]
                if text:
                    self._draw_caption_text(right_col_x + indent, y, text, font=font)

        # --- Horizontal rule ---
        rule_line = table_start + num_rows
        rule_y = (self.line_y(rule_line - 1) + self.line_y(rule_line)) / 2
        self.c.setLineWidth(0.75)
        self.c.line(LEFT_MARGIN, rule_y, PAGE_WIDTH - RIGHT_MARGIN, rule_y)

        return rule_line + 1

    def _advance_line(self, current_line: int) -> int:
        if current_line > self.lines_per_page - self._fn_area_lines:
            self.start_page()
            return 1
        return current_line

    def _emit_table(self, block: Block, current_line: int) -> int:
        """Render a markdown table on the pleading grid.

        Column widths are fitted to the text block: each column's natural
        width is measured, and if the total overflows, columns are shrunk
        proportionally but never below the width of their longest single
        word. That keeps every cell inside the right margin, which the
        previous "last column gets whatever is left" rule did not -- it
        could hand the final column a negative width, pushing its text off
        the page and inflating the row's line count with invisible wraps.

        Cell text is parsed for inline styles, so bold, italic, verbatim
        and links render inside tables as they do everywhere else.
        """
        rows = block.rows or []
        if not rows:
            return current_line
        num_cols = max(len(r) for r in rows)
        col_gap = 12.0  # pt of gutter between columns

        # Parse every cell once into styled words.
        grid: List[List[List[StyledWord]]] = []
        for row in rows:
            cells = []
            for ci in range(num_cols):
                raw = row[ci] if ci < len(row) else ""
                cells.append(spans_to_styled_words(parse_inline_styles(raw)))
            grid.append(cells)

        def words_width(words: List[StyledWord]) -> float:
            if not words:
                return 0.0
            space_w = pdfmetrics.stringWidth(" ", FONT_NAME, FONT_SIZE)
            w = sum(x.width(FONT_SIZE) for x in words)
            w += space_w * sum(1 for x in words[1:] if not x.no_space_before)
            return w

        # Natural width (longest unwrapped cell) and floor (longest single
        # word) for each column.
        natural = [0.0] * num_cols
        floor = [0.0] * num_cols
        for cells in grid:
            for ci in range(num_cols):
                natural[ci] = max(natural[ci], words_width(cells[ci]))
                for w in cells[ci]:
                    floor[ci] = max(floor[ci], w.width(FONT_SIZE))

        gutters = col_gap * (num_cols - 1)
        avail = self.text_width - gutters
        if avail <= 0:
            return current_line

        if sum(natural) <= avail:
            widths = list(natural)
            widths[-1] += avail - sum(natural)
        else:
            # Shrink proportionally, holding each column at or above its
            # longest word so nothing is forced to break mid-word.
            widths = [max(f, n * avail / sum(natural))
                      for n, f in zip(natural, floor)]
            over = sum(widths) - avail
            if over > 0:
                # Reclaim the overshoot from columns that still have slack.
                slack = [max(0.0, w - f) for w, f in zip(widths, floor)]
                total_slack = sum(slack)
                if total_slack > 0:
                    widths = [w - over * (s / total_slack)
                              for w, s in zip(widths, slack)]
                else:
                    widths = [w * avail / sum(widths) for w in widths]

        col_x = [0.0] * num_cols
        for ci in range(1, num_cols):
            col_x[ci] = col_x[ci - 1] + widths[ci - 1] + col_gap

        for ri, cells in enumerate(grid):
            wrapped = []
            row_lines = 1
            for ci in range(num_cols):
                lines = wrap_styled_words(cells[ci], widths[ci]) or [[]]
                wrapped.append(lines)
                row_lines = max(row_lines, len(lines))

            is_header = (ri == 0)
            if is_header:
                for lines in wrapped:
                    for ln in lines:
                        for w in ln:
                            w.bold = True

            # Keep a short row whole rather than splitting it across pages.
            if row_lines <= 4:
                remaining = self.lines_per_page - self._fn_area_lines - current_line
                if remaining < row_lines:
                    self.start_page()
                    current_line = 1

            row_start = current_line
            for line_idx in range(row_lines):
                current_line = self._advance_line(current_line)
                if line_idx == 0:
                    row_start = current_line
                for ci in range(num_cols):
                    if line_idx < len(wrapped[ci]):
                        self.draw_styled_line(current_line, wrapped[ci][line_idx],
                                              indent=col_x[ci])
                current_line += 1

            if is_header:
                # Rule under the header, on the same page it ended on.
                y = self.line_y(current_line - 1) - 3
                self.c.setLineWidth(0.5)
                self.c.line(self.left_margin, y,
                            self.left_margin + self.text_width, y)

        # Trailing blank line after table
        current_line = self._advance_line(current_line)
        current_line += 1
        return current_line

    def _draw_signature_line(self, line_no: int) -> None:
        """Draw either a cursive signature with underline or a blank rule.

        When signed, the underline extends ~30% past the rendered name to
        create the look of a signature on a line. When unsigned, a plain
        underscore rule is drawn.
        """
        y = self.line_y(line_no)
        rule_y = y - 2  # slightly below baseline
        if self.sign_name:
            self.c.setFont(SIGNATURE_FONT, SIGNATURE_FONT_SIZE)
            sig_width = pdfmetrics.stringWidth(
                self.sign_name, SIGNATURE_FONT, SIGNATURE_FONT_SIZE)
            self.c.drawString(self.left_margin, y, self.sign_name)
            line_end = self.left_margin + sig_width * 1.35
            self.c.setLineWidth(0.5)
            self.c.line(self.left_margin, rule_y, line_end, rule_y)
        else:
            self.draw_text_line(line_no, "____________________________________")

    def _next_esign_role(self) -> int:
        self._esign_role += 1
        return self._esign_role

    def _esign_tag(self, x: float, y: float, text: str) -> None:
        """A DocuSeal text tag, white and small: invisible on paper,
        present in the text layer, removed from the executed document
        by DocuSeal's default remove_tags.

        `esign: false` in front matter suppresses every tag: a wet-ink
        instrument (California UETA excludes UCC Article 3, so a
        negotiable note cannot be e-signed) must not carry them."""
        if self.meta.get("esign") is False:
            return
        self.c.setFillColor(white)
        self.c.setFont(NOTARIAL_FONT, ESIGN_TAG_FONT_SIZE)
        self.c.drawString(x, y, text)
        self.c.setFillColor(black)

    # Field geometry (first live test-mode run): DocuSeal anchors a
    # field on the tag TEXT's own box — a 6 pt tag 9 pt below the
    # line gave a sliver of a field hanging under the rule. So every
    # tag now carries explicit width/height (DocuSeal reads the PDF
    # at 72 dpi, so its "pixels" are page points), and the tag text
    # is placed so the field's BOTTOM edge sits on the rule or blank
    # it fills — ink above the line, like a pen.
    # A drawn signature can fill its whole box (typed values render
    # baseline-snug, so THEIR boxes stay tight), which makes the box
    # top the only edge needing air: 28 pt leaves ~2/3 of the grid
    # gap clear below the preceding printed line, while the bottom
    # stays ON the rule — a signature belongs on its line, and
    # descenders dipping under it read as pen work.
    ESIGN_SIG_FIELD_HEIGHT = 28   # signature box above its rule
    ESIGN_TEXT_FIELD_HEIGHT = 15  # one-line text/date entry
    ESIGN_TAG_ASCENT = 5          # ~cap height of the 6 pt tag text

    def _esign_field(self, x: float, rule_y: float, spec: str,
                     width: float, height: float) -> None:
        """A field of explicit size whose bottom edge rests on rule_y.

        Three modes, set by front-matter `esign`:
        - absent (default): the field is RECORDED for the sidecar
          (<pdf>.fields.json) and nothing enters the PDF text layer —
          embedded tags were invisible on paper but rode along on
          every copy-paste from the document.
        - `tags`: DocuSeal text tags drawn in white 6 pt (the only
          mode the free web UI's tag parser can read). DocuSeal takes
          the tag text's top-left corner as the field's top-left and
          extends the box down by height, so the tag's baseline goes
          at rule_y + height - ascent.
        - `false`: nothing at all (wet-ink instruments).
        """
        mode = self.meta.get("esign")
        if mode is False:
            return
        name, _, rest = spec.partition(";")
        attrs = dict(kv.split("=", 1) for kv in rest.split(";") if "=" in kv)
        if mode == "tags":
            tag = f"{{{{{spec};width={round(width)};height={round(height)}}}}}"
            self._esign_tag(x, rule_y + height - self.ESIGN_TAG_ASCENT, tag)
            return
        self.esign_fields.append({
            "name": name,
            "role": attrs.get("role", "Signer"),
            "type": attrs.get("type", "text"),
            "page": self.page_num,
            "x": round(x, 2),
            "y_top": round(PAGE_HEIGHT - (rule_y + height), 2),
            "w": round(width, 2),
            "h": round(height, 2),
        })

    def _tag_blanks(self, line_no: int, text: str, specs: List[Optional[str]],
                    font: str = FONT_NAME, size: int = FONT_SIZE) -> None:
        """Place fields over the ``___`` blank runs of a drawn line, in
        order; a None spec skips that blank. Each field is sized to
        its blank and bottoms out on the underscore rule. A 6 pt tag
        is wider than the gap between adjacent blanks, so tags that
        would overlap stagger one level UP -- overprinted tags
        interleave in the text layer and DocuSeal would read garbage
        -- with the field height grown to keep its bottom edge on the
        same rule."""
        rule_y = self.line_y(line_no) - 2  # underscores sit under the baseline
        level_end_x: List[float] = []
        for m, tag in zip(re.finditer(r"_{3,}", text), specs):
            if tag is None:
                continue
            x = self.left_margin + pdfmetrics.stringWidth(text[:m.start()], font, size) + 2
            blank_w = pdfmetrics.stringWidth(m.group(0), font, size)
            tag_probe = f"{{{{{tag};width=000;height=00}}}}"
            tag_w = pdfmetrics.stringWidth(tag_probe, NOTARIAL_FONT, ESIGN_TAG_FONT_SIZE)
            level = next((i for i, end in enumerate(level_end_x) if x >= end + 4),
                         len(level_end_x))
            if level == len(level_end_x):
                level_end_x.append(0.0)
            level_end_x[level] = x + tag_w
            height = self.ESIGN_TEXT_FIELD_HEIGHT
            if self.meta.get("esign") == "tags":
                height += level * (ESIGN_TAG_FONT_SIZE + 1)
            self._esign_field(x, rule_y, tag, blank_w, height)

    UNSIGNED_RULE = "____________________________________"

    def _tag_signature(self, line_no: int, role: int,
                       width: Optional[float] = None) -> None:
        if width is None:
            width = pdfmetrics.stringWidth(self.UNSIGNED_RULE, FONT_NAME, FONT_SIZE)
        self._esign_field(self.left_margin + 4, self.line_y(line_no) - 2,
                          f"Signature {role};role={ESIGN_ROLE_PREFIX} {role}"
                          f";type=signature",
                          width - 4, self.ESIGN_SIG_FIELD_HEIGHT)

    def _emit_signblock(self, block: Block, current_line: int) -> int:
        """Render a \\signblock or \\declsignblock.

        Both forms take the signer's name as text and pull the role from
        filer_role in the YAML metadata. declsignblock additionally reads
        spans[0].text as the location for the "Executed this..." date line.
        """
        is_decl = block.kind == "declsignblock"
        location = block.spans[0].text if is_decl and block.spans else "San Francisco, California"

        if is_decl:
            name_line = block.text
            if len(block.spans) >= 2 and block.spans[1].text:
                role = block.spans[1].text.title()
            else:
                role = ""
        else:
            name_line = block.text
            role_override = block.spans[0].text if block.spans else ""
            if role_override:
                role = role_override.title()
            else:
                role = self.meta.get("filer_role", "").title()

        if self.sign_date:
            if is_decl:
                date_text = f"Executed this {_format_decl_date(self.sign_date)}, at {location}."
            else:
                date_text = f"Dated: {_format_sign_date(self.sign_date)}"
        else:
            year = datetime.date.today().year
            if is_decl:
                date_text = unsigned_decl_execution_line(year, location)
            else:
                date_text = unsigned_dated_line()

        # Keep the entire signature block on one page (heights defined once
        # at module top, shared with _sig_block_lines_needed).
        lines_needed = SIGNBLOCK_GRID_LINES + (SIGNBLOCK_ROLE_EXTRA_LINE if role else 0)
        if current_line + lines_needed - 1 > self.lines_per_page:
            self.start_page()
            current_line = 1

        self.draw_text_line(current_line, date_text)
        if not self.sign_name:
            n = self._next_esign_role()
            if is_decl:
                self._tag_blanks(current_line, date_text, [
                    f"Day {n};role={ESIGN_ROLE_PREFIX} {n};type=text",
                    f"Month {n};role={ESIGN_ROLE_PREFIX} {n};type=text"])
            else:
                self._tag_blanks(current_line, date_text, [
                    f"Date {n};role={ESIGN_ROLE_PREFIX} {n};type=date"])
        current_line += 2  # skip blank line
        self._draw_signature_line(current_line)
        if not self.sign_name:
            self._tag_signature(current_line, n)
        current_line += 2  # skip blank line
        self.draw_text_line(current_line, name_line)
        current_line += 1
        if role:
            self.draw_text_line(current_line, role)
            current_line += 1
        current_line += 1  # trailing blank line after signature block

        return current_line

    def _emit_whereofsignblock(self, block: Block, current_line: int) -> int:
        """The testamentary execution clause and its signature area as
        ONE block, so the date is recited exactly once (the old
        prose + \\signblock pairing printed a second Dated line).
        Day, month, year, and location stay blank for the ceremony."""
        name = block.text
        role = block.spans[0].text if block.spans else ""
        instrument = (block.spans[1].text
                      if len(block.spans) > 1 and block.spans[1].text
                      else "instrument")
        clause = WHEREOF_CLAUSE.format(name=name, instrument=instrument)
        clause_lines = wrap_text(clause, self.text_width, FONT_NAME, FONT_SIZE)

        lines_needed = len(clause_lines) + WHEREOF_TAIL_GRID_LINES + (1 if role else 0)
        if current_line != 1 and current_line + lines_needed - 1 > self.lines_per_page:
            self.start_page()
            current_line = 1

        n = self._next_esign_role()
        blank_tags = [
            f"Day {n};role={ESIGN_ROLE_PREFIX} {n};type=text",
            f"Month {n};role={ESIGN_ROLE_PREFIX} {n};type=text",
            f"Year {n};role={ESIGN_ROLE_PREFIX} {n};type=text",
            f"Location {n};role={ESIGN_ROLE_PREFIX} {n};type=text",
        ]
        for text in clause_lines:
            self.draw_text_line(current_line, text)
            n_blanks = len(re.findall(r"_{3,}", text))
            if n_blanks:
                self._tag_blanks(current_line, text, blank_tags[:n_blanks])
                blank_tags = blank_tags[n_blanks:]
            current_line += 1
        current_line += 1  # blank line before the rule
        self._draw_signature_line(current_line)
        self._tag_signature(current_line, n)
        current_line += 2
        self.draw_text_line(current_line, name)
        current_line += 1
        if role:
            self.draw_text_line(current_line, role)
            current_line += 1
        current_line += 1  # trailing blank

        return current_line

    def _emit_lettersignblock(self, block: Block, current_line: int) -> int:
        """Render a \\lettersignblock: 'Sincerely,' + signature + name lines."""
        name_lines = block.text.split("\\n")
        lines_needed = LETTERSIGNBLOCK_BASE_GRID_LINES + len(name_lines)
        if current_line + lines_needed - 1 > self.lines_per_page:
            self.start_page()
            current_line = 1

        self.draw_text_line(current_line, "Sincerely,")
        current_line += 2
        self._draw_signature_line(current_line)
        current_line += 2
        for nl in name_lines:
            self.draw_text_line(current_line, nl.strip())
            current_line += 1
        current_line += 1
        return current_line

    def _emit_judgesignblock(self, block: Block, current_line: int) -> int:
        """Render a judge signature block for proposed orders."""
        title_line = block.text
        lines_needed = JUDGESIGNBLOCK_GRID_LINES
        if current_line + lines_needed - 1 > self.lines_per_page:
            self.start_page()
            current_line = 1

        self.draw_text_line(current_line, "Dated: _________________")
        current_line += 2
        self._draw_signature_line(current_line)
        current_line += 2
        self.draw_text_line(current_line, title_line)
        current_line += 1

        return current_line

    def _emit_barcode(self, block: Block, current_line: int) -> int:
        """Render a \\barcode symbol at the text margin at its printed
        module size (0.5 mm/module), scaled down to the text column
        when wider, with an optional caption on the line below."""
        caption = block.spans[1].text if len(block.spans) > 1 else ""
        fmt = barcode_format(block)
        payload = barcode_payload(block)
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            draw_w, draw_h = barcode_image(fmt, payload, tmp.name)
            if draw_w > self.text_width:
                scale = self.text_width / draw_w
                draw_w, draw_h = self.text_width, draw_h * scale

            symbol_lines = math.ceil(draw_h / self.leading) + 1
            lines_needed = symbol_lines + (BARCODE_CAPTION_EXTRA_LINE if caption else 0)
            if current_line != 1 and current_line + lines_needed - 1 > self.lines_per_page:
                self.start_page()
                current_line = 1

            top_y = self.line_y(current_line) + FONT_SIZE
            self.c.drawImage(ImageReader(tmp.name), self.left_margin,
                             top_y - draw_h, width=draw_w, height=draw_h)
        current_line += symbol_lines
        if caption:
            self.draw_text_line(current_line, caption)
            current_line += 1
        current_line += 1  # trailing blank line after the block

        return current_line

    def _barcode_lines_needed(self, block: Block) -> int:
        """Keep-together estimate without rendering: generous, from the
        payload length (a QR of an armored key runs ~6-8 lines)."""
        caption = block.spans[1].text if len(block.spans) > 1 else ""
        return 8 + (BARCODE_CAPTION_EXTRA_LINE if caption else 0)

    def _styled_width(self, words, font_size: int = FONT_SIZE) -> float:
        """Width draw_styled_words will occupy (same spacing math)."""
        space_w = pdfmetrics.stringWidth(" ", FONT_NAME, font_size)
        total = 0.0
        for i, w in enumerate(words):
            if i > 0 and not w.no_space_before:
                total += space_w
            total += w.width(font_size)
        return total

    def _emit_leftright(self, block: Block, current_line: int) -> int:
        """One line: left text at the margin, right text flush right --
        the note-header idiom ($20,000.00 ... August 13, 2026)."""
        if current_line > self.lines_per_page - self._fn_area_lines:
            self.start_page()
            current_line = 1
        y = self.line_y(current_line)
        left_words = spans_to_styled_words(parse_inline_styles(block.text),
                                           self.footnote_numbers)
        right_text = block.spans[0].text if block.spans else ""
        right_words = spans_to_styled_words(parse_inline_styles(right_text),
                                            self.footnote_numbers)
        draw_styled_words(self.c, self.left_margin, y, left_words)
        rw = self._styled_width(right_words)
        draw_styled_words(self.c, self.left_margin + self.text_width - rw, y,
                          right_words)
        return current_line + 1

    def _emit_centerline(self, block: Block, current_line: int) -> int:
        if current_line > self.lines_per_page - self._fn_area_lines:
            self.start_page()
            current_line = 1
        words = spans_to_styled_words(parse_inline_styles(block.text),
                                      self.footnote_numbers)
        w = self._styled_width(words)
        draw_styled_words(self.c,
                          self.left_margin + (self.text_width - w) / 2,
                          self.line_y(current_line), words)
        return current_line + 1

    def _emit_sigrow(self, block: Block, current_line: int) -> int:
        """Side-by-side signature rules with labels beneath: the left
        rule takes the signature, the right typically the date. One
        signer per row (e-sign role assigned accordingly)."""
        left_labels = [s.strip() for s in block.text.split("\\\\")]
        right_labels = [s.strip() for s in
                        (block.spans[0].text if block.spans else "").split("\\\\")]
        lines_needed = SIGROW_GRID_LINES_BASE + max(len(left_labels),
                                                    len(right_labels)) - 1
        if current_line + lines_needed - 1 > self.lines_per_page:
            self.start_page()
            current_line = 1

        current_line += 1  # breathing room above the rules
        rule_w = self.text_width * SIGROW_RULE_FRAC
        rx = self.left_margin + self.text_width * SIGROW_RIGHT_START_FRAC
        y = self.line_y(current_line)
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(black)
        self.c.line(self.left_margin, y, self.left_margin + rule_w, y)
        self.c.line(rx, y, rx + rule_w, y)
        n = self._next_esign_role()
        self._esign_field(self.left_margin + 4, y,
                          f"Signature {n};role={ESIGN_ROLE_PREFIX} {n}"
                          f";type=signature",
                          rule_w - 4, self.ESIGN_SIG_FIELD_HEIGHT)
        self._esign_field(rx + 4, y,
                          f"Date {n};role={ESIGN_ROLE_PREFIX} {n};type=date",
                          rule_w - 4, self.ESIGN_TEXT_FIELD_HEIGHT)
        current_line += 1
        for i in range(max(len(left_labels), len(right_labels))):
            ly = self.line_y(current_line)
            if i < len(left_labels) and left_labels[i]:
                self.c.setFont(FONT_NAME, FONT_SIZE)
                self.c.drawString(self.left_margin, ly,
                                  typographic_subs(left_labels[i]))
            if i < len(right_labels) and right_labels[i]:
                self.c.setFont(FONT_NAME, FONT_SIZE)
                self.c.drawString(rx, ly, typographic_subs(right_labels[i]))
            current_line += 1
        current_line += 1  # trailing blank

        return current_line

    def _fixedwidth_size(self, block: Block) -> float:
        longest = max((len(ln) for ln in block.text.split("\n")), default=1)
        fitted = self.text_width / max(longest, 1) / FIXEDWIDTH_ADVANCE_EM
        return max(FIXEDWIDTH_MIN_SIZE, min(FIXEDWIDTH_MAX_SIZE, fitted))

    def _emit_fixedwidth(self, block: Block, current_line: int) -> int:
        """Verbatim monospace lines, one per grid line, splitting at
        page bottoms like any text (an armored block outlasting a page
        is content, not an object)."""
        size = self._fixedwidth_size(block)
        for raw in block.text.split("\n"):
            if current_line > self.lines_per_page - self._fn_area_lines:
                self.start_page()
                current_line = 1
            self.draw_text_line(current_line, raw,
                                font=FIXEDWIDTH_FONT, size=int(size))
            current_line += 1
        current_line += 1  # trailing blank line
        return current_line

    _NOTARIAL_KINDS = ("acknowledgment", "jurat", "proofexec")

    def _notarial_layout(self, block: Block) -> dict:
        """Wrapped text and measured heights for a notarial certificate.

        One source of truth for geometry: the emitter draws from this,
        and the keep-together math reads the same total, so the two
        cannot disagree about whether the certificate fits a page.
        """
        inner_w = self.text_width - 2 * NOTARIAL_PAD
        disc_w = inner_w * NOTARIAL_DISCLOSURE_FRAC - 12
        disclosure = wrap_text(NOTARIAL_DISCLOSURE, disc_w,
                               NOTARIAL_FONT, NOTARIAL_FONT_SIZE)
        body = wrap_text(notarial_text(block), inner_w,
                         NOTARIAL_FONT, NOTARIAL_FONT_SIZE)
        perjury = (wrap_text(ACK_PERJURY, inner_w, NOTARIAL_FONT,
                             NOTARIAL_FONT_SIZE)
                   if block.kind == "acknowledgment" else [])

        h = NOTARIAL_PAD                              # top padding
        h += NOTARIAL_LEADING * 1.5                   # title
        h += len(disclosure) * NOTARIAL_LEADING + 14  # disclosure box + pad
        h += NOTARIAL_LEADING * 0.6                   # gap
        h += 2 * NOTARIAL_LEADING                     # venue lines
        h += NOTARIAL_LEADING * 0.6                   # gap
        h += len(body) * NOTARIAL_LEADING
        if perjury:
            h += NOTARIAL_LEADING * 0.6
            h += len(perjury) * NOTARIAL_LEADING
        if block.kind in ("acknowledgment", "proofexec"):
            h += NOTARIAL_LEADING * 0.8
            h += NOTARIAL_LEADING                     # WITNESS my hand...
        h += NOTARIAL_SEAL_H                          # clear zone for the seal
        h += NOTARIAL_LEADING                         # signature row
        h += NOTARIAL_PAD                             # bottom padding
        return {"disclosure": disclosure, "body": body, "perjury": perjury,
                "height": h}

    def _notarial_lines_needed(self, block: Block) -> int:
        return math.ceil(self._notarial_layout(block)["height"] / self.leading) + 1

    def _emit_notarial(self, block: Block, current_line: int) -> int:
        """Draw a California notarial certificate as one bordered object.

        Never split across pages: a certificate the notary cannot read
        whole, sign, and seal in one place is a defective certificate.
        The seal zone stays clear because the stamp must remain
        photographically reproducible.
        """
        lines_needed = self._notarial_lines_needed(block)
        if current_line != 1 and current_line + lines_needed - 1 > self.lines_per_page:
            self.start_page()
            current_line = 1

        lay = self._notarial_layout(block)
        c = self.c
        left = self.left_margin
        right = self.left_margin + self.text_width
        top = self.line_y(current_line) + FONT_SIZE
        bottom = top - lay["height"]

        c.setLineWidth(NOTARIAL_RULE)
        c.setStrokeColor(black)
        c.rect(left, bottom, self.text_width, lay["height"])

        x = left + NOTARIAL_PAD
        y = top - NOTARIAL_PAD - NOTARIAL_LEADING
        c.setFont(NOTARIAL_FONT_BOLD, NOTARIAL_FONT_SIZE + 1)
        c.drawCentredString((left + right) / 2, y, NOTARIAL_TITLES[block.kind])
        y -= NOTARIAL_LEADING * 0.5

        # The statutory consumer disclosure, in its own enclosed box.
        disc_h = len(lay["disclosure"]) * NOTARIAL_LEADING + 10
        disc_w = (self.text_width - 2 * NOTARIAL_PAD) * NOTARIAL_DISCLOSURE_FRAC
        c.rect(x, y - disc_h, disc_w, disc_h)
        ty = y - 6 - NOTARIAL_FONT_SIZE
        c.setFont(NOTARIAL_FONT, NOTARIAL_FONT_SIZE)
        for line in lay["disclosure"]:
            c.drawString(x + 6, ty, line)
            ty -= NOTARIAL_LEADING
        y -= disc_h + NOTARIAL_LEADING * 0.6

        y -= NOTARIAL_FONT_SIZE
        c.drawString(x, y, "State of California")
        y -= NOTARIAL_LEADING
        c.drawString(x, y, "County of _____________________________ )")
        y -= NOTARIAL_LEADING * 0.6 + NOTARIAL_FONT_SIZE

        for line in lay["body"]:
            c.drawString(x, y, line)
            y -= NOTARIAL_LEADING
        if lay["perjury"]:
            y -= NOTARIAL_LEADING * 0.6
            for line in lay["perjury"]:
                c.drawString(x, y, line)
                y -= NOTARIAL_LEADING
        if block.kind in ("acknowledgment", "proofexec"):
            y -= NOTARIAL_LEADING * 0.8
            c.drawString(x, y, ACK_WITNESS_LINE)
            y -= NOTARIAL_LEADING

        # Signature row at the bottom; everything above it (the seal
        # zone) stays clear for the stamp.
        sig_y = bottom + NOTARIAL_PAD + 2
        c.drawString(x, sig_y,
                     "Signature _________________________________")
        c.setFont(NOTARIAL_FONT_BOLD, NOTARIAL_FONT_SIZE)
        c.drawString(x + 250, sig_y, "(Seal)")

        return current_line + lines_needed + 1  # + trailing blank line

    def _emit_witnessattest(self, block: Block, current_line: int) -> int:
        """Signature grids for attesting witnesses: per witness, a
        signature rule with a date line, then printed-name and
        residence lines. The attestation prose stays document text;
        this is the structured signing area under it."""
        names = [n.strip() for n in block.text.split("\\") if n.strip()]
        for name in names:
            lines_needed = WITNESS_GRID_LINES_EACH
            if current_line + lines_needed - 1 > self.lines_per_page:
                self.start_page()
                current_line = 1
            n = self._next_esign_role()
            rule_y = self.line_y(current_line)
            self.c.setLineWidth(0.5)
            self.c.setStrokeColor(black)
            self.c.line(self.left_margin, rule_y, self.left_margin + 220, rule_y)
            self._tag_signature(current_line, n, width=220)
            self.draw_text_line(current_line, "Date: _______________", indent=260)
            self._esign_field(
                self.left_margin + 260
                + pdfmetrics.stringWidth("Date: ", FONT_NAME, FONT_SIZE) + 2,
                rule_y - 2,
                f"Date {n};role={ESIGN_ROLE_PREFIX} {n};type=date",
                pdfmetrics.stringWidth("_______________", FONT_NAME, FONT_SIZE),
                self.ESIGN_TEXT_FIELD_HEIGHT)
            current_line += 1
            self.draw_text_line(current_line, f"Signature of {name}",
                                font=FONT_NAME, size=FONT_SIZE_SMALL)
            current_line += 2
            rule_y = self.line_y(current_line)
            self.c.line(self.left_margin, rule_y, self.left_margin + 220, rule_y)
            self._esign_field(
                self.left_margin + 4, rule_y,
                f"Residence {n};role={ESIGN_ROLE_PREFIX} {n};type=text",
                216, self.ESIGN_TEXT_FIELD_HEIGHT)
            current_line += 1
            self.draw_text_line(current_line, "Residing at (city and state)",
                                font=FONT_NAME, size=FONT_SIZE_SMALL)
            current_line += 2
        return current_line

    _SIG_KINDS = {"sigrow", "signblock", "declsignblock", "whereofsignblock", "judgesignblock",
                  "lettersignblock", "barcode", "barcodefile", "acknowledgment",
                  "jurat", "proofexec", "witnessattest"}

    def _is_lead_block(self, block: Block) -> bool:
        """A heading or short paragraph/list item that must not be stranded
        at a page bottom above the signature block it introduces."""
        if block.kind == "heading":
            return True
        if block.kind in ("paragraph", "numbered", "bullet"):
            return len(_block_to_styled_lines(
                block, self.exhibit_letters, self.text_width,
                self.footnote_numbers)) <= SIG_LEAD_MAX_GRID_LINES
        return False

    def _block_grid_lines(self, block: Block) -> int:
        return len(_block_to_styled_lines(
            block, self.exhibit_letters, self.text_width, self.footnote_numbers))

    def _sig_block_lines_needed(self, block: Block) -> int:
        if block.kind in self._NOTARIAL_KINDS:
            return self._notarial_lines_needed(block)
        if block.kind == "witnessattest":
            names = [n for n in block.text.split("\\") if n.strip()]
            return WITNESS_GRID_LINES_EACH * max(len(names), 1)
        if block.kind == "sigrow":
            return SIGROW_GRID_LINES_BASE + 1
        if block.kind in ("barcode", "barcodefile"):
            return self._barcode_lines_needed(block)
        if block.kind == "whereofsignblock":
            return 2 + WHEREOF_TAIL_GRID_LINES + 1  # ~2 clause lines + tail
        if block.kind == "judgesignblock":
            return JUDGESIGNBLOCK_GRID_LINES
        if block.kind == "lettersignblock":
            return LETTERSIGNBLOCK_BASE_GRID_LINES + len(block.text.split("\\n"))
        # sign/declsign: conservative — assume the role line prints.
        return SIGNBLOCK_GRID_LINES + SIGNBLOCK_ROLE_EXTRA_LINE

    def _compute_keep_groups(self) -> Dict[int, int]:
        """Map the start index of a run of lead-in blocks (heading / short
        paragraphs) that ends in a signature block to the grid lines that run
        needs, so the lead-in never strands above its signature on a page
        break. This is the default; it needs no per-document markup.

        The block immediately before that run, regardless of its own length,
        is also pulled into the group when it fits: a signature block must
        never land on a page with no substantive body text at all (an
        isolated signature page is a known filing-rejection trigger), and a
        closing paragraph is often longer than the short-lead-in cap below.
        """
        groups: Dict[int, int] = {}
        n = len(self.blocks)
        i = 0
        while i < n:
            if self._is_lead_block(self.blocks[i]):
                j = i
                while (j < n and self._is_lead_block(self.blocks[j])
                       and (j - i) < SIG_KEEP_MAX_LEAD_BLOCKS):
                    j += 1
                if j < n and self.blocks[j].kind in self._SIG_KINDS:
                    start = i
                    total = (sum(self._block_grid_lines(self.blocks[k])
                                 for k in range(i, j))
                             + self._sig_block_lines_needed(self.blocks[j]))
                    if start > 0:
                        prev = self.blocks[start - 1]
                        if prev.kind not in self._SIG_KINDS and prev.kind != "heading":
                            prev_lines = self._block_grid_lines(prev)
                            if total + prev_lines <= self.lines_per_page:
                                start -= 1
                                total += prev_lines
                    # Then keep walking back over LEAD blocks. The single
                    # step above pulls in one closing paragraph, which is
                    # often longer than the short-lead cap; what sits above
                    # THAT is frequently the section label introducing it
                    # ("4. Duration."). A bold label on its own line is a
                    # PARAGRAPH to the parser, not a heading block, so the
                    # heading keep-with-next rule never sees it and it was
                    # left stranded above a run of blank numbered lines
                    # while the group it introduces broke to a fresh page.
                    while start > 0:
                        prev = self.blocks[start - 1]
                        if (prev.kind in self._SIG_KINDS
                                or not self._is_lead_block(prev)):
                            break
                        prev_lines = self._block_grid_lines(prev)
                        if total + prev_lines > self.lines_per_page:
                            break
                        start -= 1
                        total += prev_lines
                    groups[start] = total
                    i = j + 1
                    continue
            i += 1
        return groups

    def emit_body(self) -> None:
        self.start_page()
        current_line = self.first_page_caption_end_line()

        list_kinds = {"bullet", "numbered"}
        keep_groups = self._compute_keep_groups()
        for i, block in enumerate(self.blocks):
            # Keep-with-next (default): a heading or short lead-in paragraph
            # must not be stranded at a page bottom while the signature block it
            # introduces breaks to the next page. If the whole lead(s) +
            # signature group cannot finish on this page but fits on a fresh
            # one, break before the group so it stays together.
            grp = keep_groups.get(i)
            if (grp is not None and current_line != 1
                    and grp <= self.lines_per_page
                    and current_line + grp - 1 > self.lines_per_page - self._fn_area_lines):
                self.start_page()
                current_line = 1
            if block.kind in ("signblock", "declsignblock"):
                current_line = self._emit_signblock(block, current_line)
                continue
            if block.kind == "whereofsignblock":
                current_line = self._emit_whereofsignblock(block, current_line)
                continue
            if block.kind == "judgesignblock":
                current_line = self._emit_judgesignblock(block, current_line)
                continue
            if block.kind == "lettersignblock":
                current_line = self._emit_lettersignblock(block, current_line)
                continue
            if block.kind in ("barcode", "barcodefile"):
                current_line = self._emit_barcode(block, current_line)
                continue
            if block.kind == "fixedwidth":
                current_line = self._emit_fixedwidth(block, current_line)
                continue
            if block.kind == "leftright":
                current_line = self._emit_leftright(block, current_line)
                continue
            if block.kind == "centerline":
                current_line = self._emit_centerline(block, current_line)
                continue
            if block.kind == "sigrow":
                current_line = self._emit_sigrow(block, current_line)
                continue
            if block.kind in self._NOTARIAL_KINDS:
                current_line = self._emit_notarial(block, current_line)
                continue
            if block.kind == "witnessattest":
                current_line = self._emit_witnessattest(block, current_line)
                continue
            if block.kind == "table":
                current_line = self._emit_table(block, current_line)
                continue

            # Keep-with-next for every heading: a heading whose content
            # starts on the next page reads as a mistake (the stranded
            # "Witness Attestation" incident). The sig-block keep-groups
            # above handle heading+signature units; this covers headings
            # over ordinary prose.
            if (block.kind == "heading" and current_line != 1
                    and i + 1 < len(self.blocks)):
                needed = 2 + HEADING_MIN_FOLLOWING_LINES  # heading + blank + content
                if current_line + needed - 1 > self.lines_per_page - self._fn_area_lines:
                    self.start_page()
                    current_line = 1

            block_lines = _block_to_styled_lines(block, self.exhibit_letters,
                                                  self.text_width, self.footnote_numbers)
            # Tight spacing between consecutive list items of the same kind:
            # drop the trailing blank separator so items don't render double-spaced.
            next_block = self.blocks[i + 1] if i + 1 < len(self.blocks) else None
            if (block.kind in list_kinds
                    and next_block is not None
                    and next_block.kind == block.kind
                    and block_lines
                    and not block_lines[-1][0]):
                block_lines = block_lines[:-1]
            for words, indent in block_lines:
                # Footnotes newly referenced on this line shrink the usable
                # body area; account for them before the page-break decision so
                # a marker and its note always land on the same page.
                new_nums: List[int] = []
                for w in words:
                    if (w.footnote_num is not None
                            and w.footnote_num not in self._page_fn_nums
                            and w.footnote_num not in new_nums):
                        new_nums.append(w.footnote_num)
                bottom = self.lines_per_page - self._fn_area_for(self._page_fn_nums + new_nums)
                if current_line > bottom:
                    if not words:
                        # Drop overflowed separator lines so they do not create
                        # blank trailing pages at the end of a document.
                        continue
                    self.start_page()
                    current_line = 1
                    new_nums = []
                    for w in words:
                        if w.footnote_num is not None and w.footnote_num not in new_nums:
                            new_nums.append(w.footnote_num)
                if new_nums:
                    self._page_fn_nums.extend(new_nums)
                    self._fn_area_lines = self._fn_area_for(self._page_fn_nums)
                if words:
                    self.draw_styled_line(current_line, words, indent=indent)
                current_line += 1

        # Render footnotes accumulated on the final page.
        self._render_page_footnotes()

    def build(self) -> None:
        self.emit_body()
        self.c.save()


# ---------------------------------------------------------------------------
# PDF generation — exhibit list (line-numbered grid)
# ---------------------------------------------------------------------------

class LineGridPDF:
    def __init__(self, output_path: str, footer_title: str, title: str = "",
                 draft_banner: Optional[str] = None) -> None:
        self.output_path = output_path
        self.footer_title = footer_title
        self.c = canvas.Canvas(output_path, pagesize=letter)
        if title:
            self.c.setTitle(title)
        self.draft_banner = draft_banner
        self.page_num = 0

    def line_y(self, line_no: int) -> float:
        return TOP_FIRST_LINE - (line_no - 1) * LEADING

    def draw_line_numbers(self) -> None:
        draw_grid_line_numbers(self.c, self.line_y, LINES_PER_PAGE)

    def draw_footer(self) -> None:
        draw_pleading_footer(self.c, self.page_num, self.footer_title)

    def start_page(self) -> None:
        if self.page_num > 0:
            self.c.showPage()
        self.page_num += 1
        self.c.setStrokeColor(black)
        self.c.setFillColor(black)
        self.draw_line_numbers()
        self.draw_footer()

    def draw_text_line(self, line_no: int, text: str, indent: float = 0) -> None:
        self.c.setFont(FONT_NAME, FONT_SIZE)
        self.c.drawString(LEFT_MARGIN + indent, self.line_y(line_no), text)

    def build_exhibit_list(self, exhibits: List[Exhibit],
                           label: str = "Exhibit") -> None:
        """Render the list page.

        ``label`` controls both the page heading ("EXHIBIT LIST" vs
        "ATTACHMENT LIST") and the per-entry prefix ("Exhibit A" vs
        "Attachment A"). The per-entry prefix is rendered in bold and
        separated from the title by a colon, with the title wrapping
        with a hanging indent so the prefix stands out as a label.
        """
        self.start_page()
        line = 2
        heading = f"{label.upper()} LIST"
        self.c.setFont(FONT_NAME_BOLD, FONT_SIZE)
        self.c.drawCentredString(CENTER_X, self.line_y(line), heading)
        line += 2
        space_w = pdfmetrics.stringWidth(" ", FONT_NAME, FONT_SIZE)
        for ex in exhibits:
            seal_note = SEALED_EXHIBIT_LIST_ANNOTATION if ex.sealed else ""
            prefix = f"{label} {ex.letter}:"
            prefix_w = pdfmetrics.stringWidth(prefix, FONT_NAME_BOLD, FONT_SIZE)
            # First-line text width is reduced by the bold prefix + one space;
            # continuation lines hang-indent to align under the start of the title.
            hang_indent = prefix_w + space_w
            first_width = TEXT_WIDTH - hang_indent
            title_text = f"{ex.title}{seal_note}"
            first_chunk_lines = wrap_text(title_text, first_width, FONT_NAME, FONT_SIZE)
            if not first_chunk_lines:
                first_chunk_lines = [""]
            first_line = first_chunk_lines[0]
            remaining = title_text[len(first_line):].lstrip()
            cont_lines = (wrap_text(remaining, TEXT_WIDTH - hang_indent,
                                    FONT_NAME, FONT_SIZE) if remaining else [])
            if line > LINES_PER_PAGE:
                self.start_page()
                line = 1
            # Bold prefix at the line's left margin.
            self.c.setFont(FONT_NAME_BOLD, FONT_SIZE)
            self.c.drawString(LEFT_MARGIN, self.line_y(line), prefix)
            # Title text starts after the prefix on the same baseline.
            self.c.setFont(FONT_NAME, FONT_SIZE)
            self.c.drawString(LEFT_MARGIN + hang_indent, self.line_y(line), first_line)
            line += 1
            for cont in cont_lines:
                if line > LINES_PER_PAGE:
                    self.start_page()
                    line = 1
                self.c.setFont(FONT_NAME, FONT_SIZE)
                self.c.drawString(LEFT_MARGIN + hang_indent, self.line_y(line), cont)
                line += 1
            line += 1
        self.c.save()


# ---------------------------------------------------------------------------
# Exhibit tab sheets and attachments
# ---------------------------------------------------------------------------

def build_tab_sheet_pdf(exhibit: Exhibit, out_path: str,
                        status_note: Optional[str] = None,
                        label: str = "Exhibit") -> None:
    c = canvas.Canvas(out_path, pagesize=letter)
    c.setTitle(f"{label} {exhibit.letter}")
    c.setFillColor(black)

    heading = f"{label.upper()} {exhibit.letter}"
    heading_size = 24
    title_size = 14
    note_size = 12
    gap = 20

    c.setFont(FONT_NAME_BOLD, heading_size)
    heading_width = pdfmetrics.stringWidth(heading, FONT_NAME_BOLD, heading_size)
    title_lines = wrap_text(exhibit.title, PAGE_WIDTH - 144, FONT_NAME, title_size)
    title_block_h = max(1, len(title_lines)) * title_size * 1.25
    note_lines: List[str] = []
    note_gap = 16
    note_block_h = 0.0
    if status_note:
        note_lines = wrap_text(status_note, PAGE_WIDTH - 144, FONT_NAME_BOLD, note_size)
        note_block_h = max(1, len(note_lines)) * note_size * 1.25
    total_h = heading_size + gap + title_block_h
    if note_lines:
        total_h += note_gap + note_block_h
    start_y = (PAGE_HEIGHT + total_h) / 2

    c.drawString((PAGE_WIDTH - heading_width) / 2, start_y - heading_size, heading)

    c.setFont(FONT_NAME, title_size)
    y = start_y - heading_size - gap - title_size
    for line in title_lines:
        line_w = pdfmetrics.stringWidth(line, FONT_NAME, title_size)
        c.drawString((PAGE_WIDTH - line_w) / 2, y, line)
        y -= title_size * 1.25

    if note_lines:
        y -= note_gap - (title_size * 0.25)
        c.setFont(FONT_NAME_BOLD, note_size)
        for line in note_lines:
            line_w = pdfmetrics.stringWidth(line, FONT_NAME_BOLD, note_size)
            c.drawString((PAGE_WIDTH - line_w) / 2, y, line)
            y -= note_size * 1.25

    c.save()


def blank_letter_page() -> PageObject:
    return PageObject.create_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)


def _transform_annotations(page: PageObject, scale: float, tx: float, ty: float) -> None:
    """Apply a scale+translate to all annotation /Rect entries on a page.

    merge_transformed_page transforms the content stream but not annotation
    rectangles. Overlaid elements like redaction labels, form fields, and
    free-text annotations will appear at wrong positions unless we apply the
    same transformation to their /Rect coordinates.
    """
    from pypdf.generic import ArrayObject, FloatObject, NameObject
    annots = page.get("/Annots")
    if not annots:
        return
    for annot_ref in annots:
        annot = annot_ref.get_object() if hasattr(annot_ref, "get_object") else annot_ref
        rect = annot.get("/Rect")
        if not rect or len(rect) < 4:
            continue
        coords = [float(v) for v in rect]
        transformed = ArrayObject([
            FloatObject(coords[0] * scale + tx),
            FloatObject(coords[1] * scale + ty),
            FloatObject(coords[2] * scale + tx),
            FloatObject(coords[3] * scale + ty),
        ])
        annot[NameObject("/Rect")] = transformed


def scale_and_center_page(src_page: PageObject,
                          max_w: float = ATTACH_MAX_W,
                          max_h: float = ATTACH_MAX_H) -> PageObject:
    """Scale a source page to fit within max_w x max_h, centered on a letter page.

    Handles both content stream and annotation positions so that overlaid
    elements (redaction labels, form fields, etc.) stay aligned.
    """
    src_w = float(src_page.mediabox.width)
    src_h = float(src_page.mediabox.height)
    if src_w <= 0 or src_h <= 0:
        raise ValueError("Source PDF page has invalid dimensions")
    scale = min(max_w / src_w, max_h / src_h, 1.0)
    tx = (PAGE_WIDTH - src_w * scale) / 2
    ty = (PAGE_HEIGHT - src_h * scale) / 2
    dest = blank_letter_page()
    try:
        dest.merge_transformed_page(src_page, Transformation().scale(scale, scale).translate(tx, ty))
    except Exception as exc:
        # Documented fallback for malformed exhibit PDFs (spec: exhibit
        # attachments) — but never a silent one, or misscaled output could
        # not be traced back to it.
        print(
            "WARNING: could not scale/center an exhibit page; passing it "
            f"through unmodified ({exc})",
            file=sys.stderr,
        )
        return src_page
    _transform_annotations(dest, scale, tx, ty)
    return dest


def image_to_letter_pdf(image_path: Path, out_path: str) -> None:
    img = Image.open(image_path)
    img.load()
    iw, ih = img.size
    scale = min(ATTACH_MAX_W / iw, ATTACH_MAX_H / ih, 1.0)
    draw_w = iw * scale
    draw_h = ih * scale
    x = (PAGE_WIDTH - draw_w) / 2
    y = (PAGE_HEIGHT - draw_h) / 2
    c = canvas.Canvas(out_path, pagesize=letter)
    c.drawImage(ImageReader(img), x, y, width=draw_w, height=draw_h,
                preserveAspectRatio=True, mask='auto')
    c.save()


BLANK_SIGNER = "_______________________________________________"


def notarial_text(block: Block) -> str:
    """The certificate paragraph for a notarial block, statutory wording
    with the typed name(s) inserted (or ruled blanks when none given)."""
    if block.kind == "acknowledgment":
        return ACK_BODY.format(signer=block.text or BLANK_SIGNER)
    if block.kind == "jurat":
        return JURAT_BODY.format(signer=block.text or BLANK_SIGNER)
    if block.kind == "proofexec":
        principal = block.spans[0].text if block.spans else ""
        return PROOF_BODY.format(witness=block.text or BLANK_SIGNER,
                                 principal=principal or BLANK_SIGNER)
    raise ValueError(f"not a notarial block: {block.kind}")


def barcode_payload(block: Block) -> str:
    """The text a barcode encodes: inline payload, or a file's contents.

    \\barcodefile paths resolve against the working directory; envelope
    builds run from the matter directory, so matter-relative paths (a
    key block in assets/, a detached signature) work unchanged.
    """
    if block.kind != "barcodefile":
        return block.text
    path = Path(block.text).expanduser()
    if not path.exists():
        raise SystemExit(
            f"\\barcodefile: {block.text} not found (paths resolve against "
            f"the working directory; builds run from the matter)")
    return path.read_text().strip()


def barcode_format(block: Block) -> str:
    fmt = block.spans[0].text if block.spans else ""
    if fmt not in BARCODE_FORMATS:
        raise SystemExit(
            f"\\barcode: unknown format {fmt!r} (one of {', '.join(BARCODE_FORMATS)})")
    return fmt


def _run_symbol_tool(cmd: List[str], payload: str, tool: str) -> None:
    try:
        proc = subprocess.run(cmd, input=payload.encode("utf-8"),
                              capture_output=True)
    except FileNotFoundError:
        raise SystemExit(
            f"\\barcode needs {tool} (apt/brew install {tool}; "
            f"see system-dependencies.yaml)") from None
    if proc.returncode != 0:
        raise SystemExit(f"{tool} failed: {proc.stderr.decode().strip()}")


def render_barcode_png(fmt: str, payload: str, out_path: str,
                       cols: Optional[int] = None) -> None:
    """Encode payload as a symbol PNG: qrencode for qr, zint for the
    rest. Payload arrives on stdin (qrencode) or via a temp file
    (zint): key blocks overflow argv comfort and a command line leaks
    into process listings.
    """
    if fmt == "qr":
        _run_symbol_tool(
            ["qrencode", "-o", out_path, "-l", QR_ERROR_CORRECTION,
             "-s", str(BARCODE_PX_PER_MODULE), "-m", str(QR_MARGIN_MODULES)],
            payload, "qrencode")
        return
    with tempfile.NamedTemporaryFile(suffix=".txt") as data:
        data.write(payload.encode("utf-8"))
        data.flush()
        cmd = ["zint", "--barcode", ZINT_FORMAT_CODES[fmt],
               "--output", out_path, "--filetype", "PNG",
               "--scale", str(BARCODE_PX_PER_MODULE / 2),
               "--input", data.name, "--binary", "--quietzones"]
        if fmt == "code128":
            cmd += ["--height", str(CODE128_HEIGHT_MODULES), "--notext"]
        if cols is not None:
            cmd += ["--cols", str(cols)]
        _run_symbol_tool(cmd, payload, "zint")


def barcode_image(fmt: str, payload: str, out_path: str) -> Tuple[float, float]:
    """Render the symbol and return its printed size in points at
    BARCODE_MODULE_MM per module. PDF417 searches zint's column count
    for the geometry nearest the 3:1 width:height target."""
    if fmt == "pdf417":
        best = None
        for cols in PDF417_COLS_RANGE:
            try:
                render_barcode_png(fmt, payload, out_path, cols=cols)
            except SystemExit:
                continue
            img = Image.open(out_path)
            aspect = img.width / img.height
            score = abs(aspect - PDF417_TARGET_ASPECT)
            if best is None or score < best[0]:
                best = (score, cols)
        if best is None:
            raise SystemExit("zint could not encode the payload as pdf417")
        render_barcode_png(fmt, payload, out_path, cols=best[1])
    else:
        render_barcode_png(fmt, payload, out_path)
    img = Image.open(out_path)
    module_pt = BARCODE_MODULE_MM[fmt] * MM_TO_PT
    w = img.width / BARCODE_PX_PER_MODULE * module_pt
    h = img.height / BARCODE_PX_PER_MODULE * module_pt
    # Enforce the scannability floor: grow the symbol (uniformly, so
    # module geometry survives) until its smaller side reaches the
    # minimum. The emitter's text-column cap still applies after.
    smaller = min(w, h)
    if smaller < BARCODE_MIN_SIDE_PT:
        scale = BARCODE_MIN_SIDE_PT / smaller
        w, h = w * scale, h * scale
    return w, h


def append_pdf_scaled(writer: PdfWriter, pdf_path: Path,
                      pages_spec: Optional[str] = None) -> None:
    reader = PdfReader(str(pdf_path))
    if pages_spec:
        indices = parse_page_ranges(pages_spec, len(reader.pages))
        for i in indices:
            writer.add_page(scale_and_center_page(reader.pages[i]))
    else:
        for page in reader.pages:
            writer.add_page(scale_and_center_page(page))


def append_exhibit_attachment(writer: PdfWriter, exhibit: Exhibit, temp_dir: Path) -> None:
    ext = exhibit.path.suffix.lower()
    if ext == ".pdf":
        append_pdf_scaled(writer, exhibit.path, exhibit.pages)
        return
    if ext in {".png", ".jpg", ".jpeg"}:
        tmp = temp_dir / f"exhibit_{exhibit.letter}_image.pdf"
        image_to_letter_pdf(exhibit.path, str(tmp))
        append_pdf_scaled(writer, tmp)
        return
    raise ValueError(f"Unsupported exhibit attachment type: {exhibit.path}")


def append_pdf_direct(writer: PdfWriter, pdf_path: Path) -> None:
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        writer.add_page(page)


def _add_file_link_annotation(writer: PdfWriter, page_idx: int,
                              rect: Tuple[float, float, float, float],
                              rel_path: str) -> None:
    """A \\filelink annotation: /GoToR with a RELATIVE file spec, so the
    link resolves against wherever the PDF itself lives. Desktop viewers
    (Acrobat and peers) follow it when the target travels beside the PDF;
    web previews generally do not -- callers should say so in the text."""
    from pypdf.generic import (
        ArrayObject, DictionaryObject, FloatObject, NameObject,
        NumberObject, TextStringObject,
    )
    annot = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Link"),
        NameObject("/Rect"): ArrayObject([
            FloatObject(rect[0]), FloatObject(rect[1]),
            FloatObject(rect[2]), FloatObject(rect[3]),
        ]),
        NameObject("/A"): DictionaryObject({
            NameObject("/S"): NameObject("/GoToR"),
            NameObject("/F"): TextStringObject(rel_path),
        }),
        NameObject("/Border"): ArrayObject([
            NumberObject(0), NumberObject(0), NumberObject(0),
        ]),
    })
    page = writer.pages[page_idx]
    if "/Annots" in page:
        page["/Annots"].append(writer._add_object(annot))
    else:
        from pypdf.generic import ArrayObject as _AO
        page[NameObject("/Annots")] = _AO([writer._add_object(annot)])


def _add_link_annotation(writer: PdfWriter, page_idx: int, rect: Tuple[float, float, float, float],
                         target_page_idx: int) -> None:
    from pypdf.generic import (
        ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject,
    )
    target_ref = writer.pages[target_page_idx].indirect_reference
    annot = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Link"),
        NameObject("/Rect"): ArrayObject([
            FloatObject(rect[0]), FloatObject(rect[1]),
            FloatObject(rect[2]), FloatObject(rect[3]),
        ]),
        NameObject("/A"): DictionaryObject({
            NameObject("/S"): NameObject("/GoTo"),
            NameObject("/D"): ArrayObject([
                target_ref, NameObject("/Fit"),
            ]),
        }),
        NameObject("/Border"): ArrayObject([
            NumberObject(0), NumberObject(0), NumberObject(0),
        ]),
    })
    page = writer.pages[page_idx]
    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    page[NameObject("/Annots")].append(writer._add_object(annot))


def merge_outputs(main_pdf: Path, exhibit_list_pdf: Optional[Path],
                  exhibits: List[Exhibit], output_pdf: Path,
                  link_rects: Optional[List[LinkRect]] = None,
                  variant: str = DEFAULT_VARIANT,
                  label: str = "Exhibit") -> None:
    writer = PdfWriter()
    append_pdf_direct(writer, main_pdf)

    if exhibit_list_pdf and exhibit_list_pdf.exists():
        append_pdf_direct(writer, exhibit_list_pdf)

    tab_page_map: Dict[str, int] = {}

    with tempfile.TemporaryDirectory(prefix="md_pleading_exhibits_") as td:
        temp_dir = Path(td)
        for exhibit in exhibits:
            # Sealed-exhibit tab asymmetry, by design: the sealed packet is
            # accompanied by the separately-lodged originals, so a sealed
            # exhibit is skipped entirely there (no tab sheet); the PUBLIC
            # packet must show the gap, so it gets a placeholder tab (with
            # the seal note) and no attachment pages.
            if exhibit.sealed and variant != "public":
                continue
            tab_pdf = temp_dir / f"tab_{exhibit.letter}.pdf"
            status_note = None
            if exhibit.sealed:
                status_note = SEALED_EXHIBIT_TAB_NOTE
            build_tab_sheet_pdf(exhibit, str(tab_pdf),
                                status_note=status_note, label=label)
            tab_page_idx = len(writer.pages)
            tab_page_map[f"exhibit_{exhibit.letter}"] = tab_page_idx
            append_pdf_scaled(writer, tab_pdf)
            if exhibit.sealed:
                continue
            append_exhibit_attachment(writer, exhibit, temp_dir)

        if link_rects:
            for lr in link_rects:
                rect = (lr.x, lr.y, lr.x + lr.width, lr.y + lr.height)
                if lr.dest.startswith("file:"):
                    _add_file_link_annotation(writer, lr.page_index, rect,
                                              lr.dest[len("file:"):])
                    continue
                target_idx = tab_page_map.get(lr.dest)
                if target_idx is not None:
                    _add_link_annotation(
                        writer, lr.page_index, rect,
                        target_idx,
                    )

        with open(output_pdf, "wb") as f:
            writer.write(f)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Markdown into a California-style pleading PDF.")
    parser.add_argument("input_md", help="Path to input Markdown file with YAML front matter")
    parser.add_argument("output_pdf", help="Path to output PDF file")
    parser.add_argument("--variant", choices=sorted(SUPPORTED_VARIANTS),
                        default=None,
                        help="Render variant to use for variant-aware metadata "
                             "and redactions. When omitted, redaction-bearing "
                             "documents build the PUBLIC variant (with a "
                             f"warning); others build {DEFAULT_VARIANT!r}.")
    parser.add_argument("--sign", metavar="NAME", default=None,
                        help="Sign all \\signblock and \\declsignblock blocks with a cursive rendering of NAME")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Fill in signature block dates (default: today)")
    parser.add_argument("--final", action="store_true",
                        help="Suppress the default DRAFT banner: this build is "
                             "the one going into the world")
    args = parser.parse_args()

    sign_name: Optional[str] = args.sign
    sign_date: Optional[datetime.date] = None
    if sign_name:
        if not _signature_font_available:
            raise SystemExit(
                f"--sign requires {_SIGNATURE_FONT_FILE} in {FONT_DIR}")
        if args.date:
            sign_date = datetime.date.fromisoformat(args.date)
        else:
            sign_date = datetime.date.today()

    input_path = Path(args.input_md).resolve()
    output_path = Path(args.output_pdf).resolve()

    with open(input_path, "r", encoding="utf-8") as f:
        raw = f.read()

    warn_spaced_dashes(raw, input_path)

    meta, body = parse_front_matter(raw)
    # Deployment- and matter-level front-matter defaults (ADR-0035):
    # local/config.yaml < matter.yaml < the source's own front matter.
    import form_fill as _ff
    import jc_common as _jc
    _defaults = _jc.front_matter_defaults(_ff.find_case_dir(input_path))
    if _defaults:
        meta = {**_defaults, **meta}
    variant = effective_variant(meta, body, args.variant)
    if args.variant is None and variant == "public":
        print(
            f"WARNING: {input_path.name} carries redactions or "
            "variant-aware content but no --variant was given; building "
            "the PUBLIC (redacted) variant. Pass --variant sealed "
            "explicitly to render sealed content.",
            file=sys.stderr,
            flush=True,
        )
    meta = apply_variant_to_meta(meta, variant)
    # A source cannot self-finalize: only the build flag clears the
    # default draft banner, and it does so per invocation.
    meta.pop("_final", None)
    if args.final:
        if meta.get("notreal") is not None:
            # `notreal:` is the human's declaration that this source is
            # not ready to be real. --final must not outrank it: the
            # execution sequence is remove the marker (the human's
            # act), THEN build final — never a final build of a source
            # its author still disclaims.
            raise SystemExit(
                f"{input_path.name}: refusing --final while the source "
                f"carries notreal: {meta['notreal']!r}. Removing that "
                f"marker is the author's declaration that the document "
                f"is ready; do that first, then rebuild --final."
            )
        meta["_final"] = True
    warn_unknown_front_matter_keys(meta, input_path.name)
    require_attachment_has_no_caption(meta, input_path.name)
    require_cover_sheet_only_has_cover_sheet(meta, input_path.name)
    exhibits = validate_meta(meta, input_path, variant)
    exhibit_map = {ex.shortname: ex for ex in exhibits}

    # exhibit_source: allows a file to resolve \exhibit{} refs against another
    # file's exhibit list (e.g. a petition referencing a declaration's exhibits).
    # External exhibits are used only for name→letter resolution; they are NOT
    # attached to this PDF.
    exhibit_source = meta.get("exhibit_source")
    if exhibit_source:
        source_path = Path(exhibit_source)
        if not source_path.is_absolute():
            source_path = (input_path.parent / source_path).resolve()
        for ex in load_external_exhibits(source_path, variant):
            if ex.shortname not in exhibit_map:
                exhibit_map[ex.shortname] = ex

    doctype = meta.get("doctype", "pleading")
    attachment_label = exhibit_label_for_doctype(doctype)
    cover_sheet = meta.get("cover_sheet")
    cover_sheet_only = bool(meta.get("cover_sheet_only"))
    pleading = None

    if cover_sheet_only:
        # No body at all: the filled cover sheet below becomes the
        # entire output. Nothing here to macro-substitute, paginate,
        # build a PleadingPDF for, or merge with an exhibit list --
        # validate_meta already refused `exhibits:` alongside this flag.
        os.makedirs(output_path.parent, exist_ok=True)
    else:
        body = substitute_redaction_macros(body, meta, variant)
        body = substitute_redaction_log_macro(body, meta, variant, input_path)
        body = substitute_posblock_macro(body, meta)
        body = substitute_exhibit_refs(body, exhibit_map, doctype=doctype)
        body = substitute_date_macro(body, meta)
        body = flatten_lettersignblock(body)
        body = autonumber_list_items(body)
        body, footnote_defs = extract_footnote_defs(body)
        blocks = parse_markdown_blocks(body, doctype=doctype)
        # heading_numbers: false — for documents whose headings carry their
        # own enumeration ("Article I. ..."), auto-numbering would double it.
        if meta.get("heading_numbers", True):
            blocks = number_headings(blocks)

        os.makedirs(output_path.parent, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="md_pleading_") as td:
            temp_dir = Path(td)
            main_pdf = temp_dir / "main.pdf"
            exhibit_letters = {
                ex.letter for ex in exhibits
                if not ex.sealed or variant == "public"
            }
            pleading = PleadingPDF(meta, blocks, str(main_pdf),
                                   exhibit_letters=exhibit_letters,
                                   sign_name=sign_name, sign_date=sign_date,
                                   footnote_defs=footnote_defs)
            pleading.build()

            exhibit_list_pdf: Optional[Path] = None
            if exhibits and not meta.get("no_exhibit_list"):
                exhibit_list_pdf = temp_dir / "exhibit_list.pdf"
                list_title = f"{attachment_label} List"
                LineGridPDF(str(exhibit_list_pdf), footer_title=list_title,
                            title=list_title,
                            draft_banner=draft_banner_text(meta)).build_exhibit_list(
                    exhibits, label=attachment_label)

            merge_outputs(main_pdf, exhibit_list_pdf, exhibits, output_path,
                          link_rects=pleading.link_rects, variant=variant,
                          label=attachment_label)

    cover_path: Optional[Path] = None
    if cover_sheet:
        # Anything registered in forms/registry/ is handled generically
        # by form_fill.py (descriptor-driven fill; see docs/forms.md).
        import form_fill
        try:
            descriptor = form_fill.load_descriptor(cover_sheet)
            pages_attached_field = descriptor.get("pages_attached_field")
            if pages_attached_field and not cover_sheet_only:
                # Some cover forms state the attached document's page
                # count (declared as `pages_attached_field` in the
                # descriptor), known only after the body renders —
                # inject it, then use the generic descriptor path like
                # every other form. Moot for cover_sheet_only: there is
                # no attached document, only the form itself.
                pages_attached = len(PdfReader(str(output_path)).pages)
                meta = dict(meta)
                forms_block = dict(meta.get("forms") or {})
                form_block = dict(forms_block.get(cover_sheet) or {})
                form_block.setdefault(pages_attached_field, str(pages_attached))
                forms_block[cover_sheet] = form_block
                meta["forms"] = forms_block
            cover_path = form_fill.ensure_cached(cover_sheet, meta, input_path)
        except FileNotFoundError as exc:
            raise SystemExit(
                f"Unsupported cover_sheet value: {cover_sheet!r}. {exc}"
            )
        if cover_sheet_only:
            # The filled form IS the document: write it straight to
            # output_path rather than prepending it onto a body that
            # was never built.
            shutil.copyfile(cover_path, output_path)
            print(f"Wrote {form_display_id(cover_sheet)} as the entire "
                  f"output ({output_path}) from {cover_path}")
        else:
            form_fill.prepend(output_path, cover_path)
            print(f"Prepended {form_display_id(cover_sheet)} cover sheet from {cover_path}")

    # Consumer/employee notices ride alongside the document, not inside
    # it: each is served on a different person, with a copy of the
    # subpoena, on its own statutory clock.
    try:
        notices = emit_consumer_notices(meta, output_path)
    except ValueError as exc:
        raise SystemExit(f"{input_path.name}: {exc}")
    # Last, over the assembled packet: cover sheet, body, exhibit list,
    # tab sheets and exhibits alike. The notices are separately served
    # documents, so each gets its own stamp.
    banner = draft_banner_text(meta)
    if banner:
        stamp_draft_banner(output_path, banner)
        for path in notices:
            stamp_draft_banner(Path(path), banner)

    for path in notices:
        print(f"Wrote {form_display_id(CONSUMER_NOTICE_FORM)} consumer notice {path}")

    print(f"Wrote {output_path}")

    # E-sign field sidecar (<pdf>.fields.json): geometry for `sc
    # docuseal send`, kept OUT of the PDF so nothing invisible rides
    # the clipboard. Page numbers account for a prepended cover sheet.
    fields_path = output_path.with_name(output_path.name + ".fields.json")
    esign_fields = list(getattr(pleading, "esign_fields", []) or [])
    if esign_fields:
        offset = 0
        if cover_sheet and cover_path:
            offset = len(PdfReader(str(cover_path)).pages)
        if offset:
            esign_fields = [{**f, "page": f["page"] + offset} for f in esign_fields]
        fields_path.write_text(json.dumps({
            "page_width": PAGE_WIDTH,
            "page_height": PAGE_HEIGHT,
            "origin": "top-left",
            "units": "pt",
            "fields": esign_fields,
        }, indent=2) + "\n")
        print(f"Wrote {fields_path}")
    elif fields_path.exists():
        fields_path.unlink()
        print(f"Removed stale {fields_path}")

    # The sidecar quotes the verbatim sealed text, so it accompanies only
    # the sealed variant: a public/unscoped output directory may be shipped
    # as "the public packet" and must stay free of sealed bytes.
    redaction_log = meta.get("_redaction_log") or []
    log_path = output_path.with_suffix(output_path.suffix + REDACTION_SIDECAR_SUFFIX)
    if redaction_log and variant == "sealed":
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(redaction_log, f, indent=2, ensure_ascii=True)
            f.write("\n")
        print(f"Wrote {log_path}")
    elif log_path.exists():
        # A sidecar from an earlier build of this path would otherwise sit,
        # stale, next to a current PDF that no longer warrants one.
        log_path.unlink()
        print(f"Removed stale {log_path}")


if __name__ == "__main__":
    main()
