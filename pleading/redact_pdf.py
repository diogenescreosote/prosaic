#!/usr/bin/env python3
"""General-purpose PDF redaction tool for pleading_gen.

Reads a JSON config file describing a set of redaction operations and
produces a redacted copy of the source PDF.  The output is cached: if the
output file exists and is newer than both the source PDF and the config
file, nothing is rebuilt (unless --force is passed).

CONFIG FILE FORMAT (JSON)
─────────────────────────
{
  "source_pdf":  "<path relative to config file>",
  "output_pdf":  "<path relative to config file>",

  // Visual style — all optional, defaults shown
  "fill_color":       [1, 1, 1],     // RGB 0–1 floats; default white
  "text_color":       [0, 0, 0],     // label text color; default black
  "label_font":       "helv",        // fitz built-in font name
  "label_font_size":  7,             // pt
  "border_width":     0.5,           // redaction-box border in pt

  "redactions": [
    // --- TYPE 1: seal_pages ---
    // Replace one or more consecutive PDF pages entirely with a centered
    // placeholder.  The page to start on is found by searching the whole
    // document for `find_text`; then `page_count` pages from that point
    // (inclusive) are replaced.
    {
      "type": "seal_pages",
      "description": "human-readable note (logged, not in output)",
      "find_text": "PAGE 20 OF 51",           // text that identifies the first page
      "page_count": 2,                         // how many consecutive pages to seal
      "replacement_text": "EXHIBIT A ...\nSEALED UNDER COURT ORDER DATED _________, 2026"
    },

    // --- TYPE 1b: seal_page_range ---
    // Replace an explicit, 1-based INCLUSIVE page range.  Prefer this over
    // seal_pages whenever the pages are already known -- especially for
    // scanned exhibits, where seal_pages' anchor search runs against OCR
    // output and is case-insensitive, so "EXHIBIT 2" can match a body-text
    // "Exhibit 2" many pages earlier and seal the wrong pages silently.
    {
      "type": "seal_page_range",
      "description": "...",
      "first_page": 22,
      "last_page": 34,
      "replacement_text": "EXHIBIT 2 ...\nSTRICKEN AND SEALED"
    },

    // --- TYPE 1c: redact_row ---
    // Redact the whole ruled table ROW containing `anchor_text`.  Use this for
    // any tabular data: redacting just the phrase you can name is how you
    // redact nothing.  A witness-list row carries a name in one cell and the
    // street address and telephone number in the next two, so covering the
    // name leaves the person trivially identifiable.  Row height comes from
    // the horizontal ruling lines, so cells that wrap to three lines are
    // covered to their full height.  "scope": "cell" stays inside the
    // vertical rules instead of spanning the table.
    {
      "type": "redact_row",
      "description": "...",
      "anchor_text": "Some Name",
      "scope": "row",
      "label": "[ITEM 21: SEALED]"
    },

    // --- TYPE 1d: redact_region ---
    // Explicit rectangle on an explicit 1-based page, in 0-1 page fractions
    // so it survives a re-render at another scale.  The escape hatch for
    // material no text search reaches: signatures, handwriting, stamps,
    // photographs, scan regions whose OCR came out as noise.
    {
      "type": "redact_region",
      "description": "...",
      "page": 7,
      "rect": [0.10, 0.42, 0.95, 0.51],
      "label": "[REDACTED]"
    },

    // --- TYPE 2: redact_block ---
    // Redact a contiguous block of text spanning from `start_text`
    // through `end_text` (both inclusive) on the same PDF page.
    // The covered rectangle runs from the top of the first hit to the
    // bottom of the last hit, spanning the full column width.
    {
      "type": "redact_block",
      "description": "...",
      "start_text": "Example redaction start text",
      "end_text": "Oakland, California.",
      "label": "[¶ 11 (THIRD-PARTY MEDICAL HISTORY) REDACTED]"
    },

    // --- TYPE 3: redact_clause ---
    // Redact one or more exact phrases, each independently located
    // anywhere in the document.  Each phrase becomes its own
    // redaction annotation.
    {
      "type": "redact_clause",
      "description": "...",
      "search_text": "threats of suicide and acts of self-harm,",
      "label": "[CLAUSE REDACTED]"
    },

    // --- TYPE 4: redact_sentences ---
    // Like redact_block but uses a single anchor phrase and covers
    // from there to the end of that paragraph unit (until a blank line
    // or the next paragraph anchor is found).  Useful for single-sentence
    // redactions embedded in paragraphs.
    {
      "type": "redact_sentences",
      "description": "...",
      "search_text": "He was eventually 5150'd",
      "label": "[SENTENCE REDACTED]"
    }
  ]
}

CACHING
───────
The script exits 0 with no output if the output file exists and is newer
than both source_pdf and the config file, unless --force is passed.
Pass --check-stale to exit 1 (without building) if the output is stale.

FAILURE MODE
────────────
Every redaction entry must match: if any operation finds nothing (typo'd
search text, unknown type, or an error while applying), the script prints
the offending entry to stderr, writes NO output, and exits nonzero. A
"successful" build therefore means every listed redaction was applied.

USAGE
─────
  python3 redact_pdf.py <config.json> [--force] [--check-stale]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import fitz  # type: ignore[import]
except ImportError:
    print("ERROR: PyMuPDF is required.  Install with: pip install pymupdf",
          file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Staleness helpers
# ---------------------------------------------------------------------------

def _mtime(p: Path) -> float:
    try:
        return os.path.getmtime(p)
    except FileNotFoundError:
        return -1.0


def is_stale(config_path: Path, source_pdf: Path, output_pdf: Path) -> tuple[bool, str]:
    """Return (stale, reason).  stale=True means a rebuild is required."""
    if not output_pdf.exists():
        return True, f"missing output {output_pdf}"
    out_mtime = _mtime(output_pdf)
    for dep in (config_path, source_pdf):
        if _mtime(dep) > out_mtime:
            return True, f"{dep.name} is newer than {output_pdf.name}"
    return False, ""


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _color(cfg: dict[str, Any], key: str, default: list[float]) -> tuple[float, float, float]:
    v = cfg.get(key, default)
    return (float(v[0]), float(v[1]), float(v[2]))


def _add_redact(
    page: fitz.Page,
    rect: fitz.Rect,
    label: str,
    fill: tuple[float, float, float],
    text_color: tuple[float, float, float],
    font: str,
    font_size: float,
) -> None:
    """Add a single redaction annotation with a text label (no border — draw after apply)."""
    # Last line of defence for the base-14 encoding trap: whatever the caller
    # passed, only draw glyphs the label font has. See sanitize_label.
    label, _dropped = sanitize_label(label)
    page.add_redact_annot(
        rect,
        text=label,
        fontname=font,
        fontsize=font_size,
        fill=fill,
        text_color=text_color,
    )


def _draw_borders(page: fitz.Page, rects: list[fitz.Rect], border_width: float) -> None:
    """Draw a thin rectangle border around each redacted area after apply_redactions."""
    if border_width <= 0:
        return
    for r in rects:
        page.draw_rect(r, color=(0.0, 0.0, 0.0), width=border_width)


def _deduplicate_rects(
    rects: list[fitz.Rect], y_tol: float = 4.0, x_gap_tol: float = 4.0
) -> list[fitz.Rect]:
    """Merge rectangles that are on the same line and overlapping or nearly adjacent.

    This collapses the multiple hits that OCR-layered scanned PDFs produce
    for a single visible phrase (e.g. the text appears in both the image
    layer and the invisible OCR layer, causing search_for to return
    duplicate rects).
    """
    if not rects:
        return []
    # Sort by y0 then x0.
    ordered = sorted(rects, key=lambda r: (round(r.y0, 1), r.x0))
    groups: list[fitz.Rect] = []
    cur = fitz.Rect(ordered[0])
    for r in ordered[1:]:
        same_line = abs(r.y0 - cur.y0) < y_tol and abs(r.y1 - cur.y1) < y_tol
        adjacent = r.x0 <= cur.x1 + x_gap_tol
        if same_line and adjacent:
            cur = fitz.Rect(
                min(cur.x0, r.x0), min(cur.y0, r.y0),
                max(cur.x1, r.x1), max(cur.y1, r.y1),
            )
        else:
            groups.append(cur)
            cur = fitz.Rect(r)
    groups.append(cur)
    return groups


# ---------------------------------------------------------------------------
# Label safety
# ---------------------------------------------------------------------------

# The base-14 fonts fitz uses for redaction labels ("helv" and friends) encode
# Latin-1. Anything outside it draws as "?" -- so a label reading
# "[ITEM 5 — SEALED]" silently becomes "[ITEM 5 ? SEALED]" in the output, which
# looks like a defect in a document whose whole purpose is to be trusted.
# Typographic punctuation is the common way in, because prose style guides call
# for it and labels get copied out of prose.
_LABEL_FOLD = {
    "—": "--", "–": "-", "‒": "-", "‐": "-",
    "‘": "'", "’": "'", "‚": ",",
    "“": '"', "”": '"',
    "…": "...", " ": " ", " ": " ", " ": " ",
    "­": "", "•": "*", "·": "*", "′": "'", "″": '"',
    "§": "sec. ",
}


def sanitize_label(label: str) -> tuple[str, list[str]]:
    """Fold a label to characters the base-14 label fonts can actually draw.

    Returns (safe_label, unrepresentable_characters_dropped).
    """
    out: list[str] = []
    dropped: list[str] = []
    for ch in label:
        if ch in _LABEL_FOLD:
            out.append(_LABEL_FOLD[ch])
            continue
        try:
            ch.encode("latin-1")
        except UnicodeEncodeError:
            dropped.append(ch)
            continue
        out.append(ch)
    return "".join(out), dropped


# ---------------------------------------------------------------------------
# Table geometry
# ---------------------------------------------------------------------------

def _rules(page: fitz.Page, horizontal: bool) -> list[float]:
    """Positions of the page's ruling lines, from vector drawings.

    Judicial Council forms and exhibit lists are ruled tables, so the rules
    give exact cell boundaries -- far better than guessing from text extents.
    A "rule" is any drawn line or thin filled rect whose other dimension is
    long, which catches both stroked lines and hairline rectangles.
    """
    positions: list[float] = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r is None:
            continue
        w, h = r.width, r.height
        if horizontal and h <= 2.5 and w >= 40:
            positions.append((r.y0 + r.y1) / 2.0)
        elif not horizontal and w <= 2.5 and h >= 20:
            positions.append((r.x0 + r.x1) / 2.0)
    if not positions:
        # A scanned page has no vector drawings at all: its table rules are
        # pixels. Without this fallback _band finds nothing, silently degrades
        # to one line height, and a three-line table row gets a one-line box --
        # which is worse than useless, because it looks redacted.
        positions = _rules_from_image(page, horizontal)

    # Collapse near-duplicates (a stroked line often yields two edges).
    positions.sort()
    merged: list[float] = []
    for p in positions:
        if not merged or p - merged[-1] > 2.0:
            merged.append(p)
    return merged


def _rules_from_image(page: fitz.Page, horizontal: bool, dpi: int = 72,
                      dark: int = 215, gap: int = 4,
                      min_frac: float = 0.45) -> list[float]:
    """Find a scanned table's ruling lines by their longest near-contiguous run.

    Returns positions in PDF points.

    Three things had to be right here, and each was wrong on the first try:

    * The discriminator is run LENGTH, not dark-pixel count. A line of text has
      many short runs that can total more ink than the rule beneath it.
    * Scanned rules are DITHERED, so they are not continuous. At a strict ink
      threshold a real rule measured 83 pixels on a 612-pixel page while the
      one rule that happened to scan solid measured 427. Tolerating a few light
      pixels inside a run (`gap`) is what makes the rest visible.
    * The ink threshold has to be generous (215, not 128). Table rules are
      hairlines and scan to mid grey, not black.

    Too strict and rules go missing, which is the dangerous direction: a
    missing rule silently merges two table rows, so a redaction aimed at one
    row covers its neighbour as well. Too loose and lines of text register as
    rules, which splits a row. The defaults recover the exact row grid of a
    Judicial Council form scanned at 300 dpi.
    """
    try:
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    except Exception:
        return []
    w, h, s = pix.width, pix.height, pix.samples
    if w == 0 or h == 0:
        return []
    n = pix.n or 1
    scale = 72.0 / dpi
    span = w if horizontal else h
    need = int(span * min_frac)
    outer = h if horizontal else w

    def longest_run(fixed: int) -> int:
        best = run = miss = 0
        for i in range(span):
            idx = (fixed * w + i) if horizontal else (i * w + fixed)
            if s[idx * n] < dark:
                run += 1
                miss = 0
                if run > best:
                    best = run
            else:
                miss += 1
                if miss > gap:
                    run = 0
                else:
                    run += 1
        return best

    return [i * scale for i in range(outer) if longest_run(i) >= need]



def _band(anchor: float, rules: list[float], lo: float, hi: float,
          pad: float) -> tuple[float, float]:
    """The gap between the rules bracketing `anchor`, or a padded fallback."""
    before = [r for r in rules if r <= anchor + 0.5]
    after = [r for r in rules if r >= anchor - 0.5]
    a = max(before) if before else None
    b = min(after) if after else None
    if a is not None and b is not None and b - a > 4.0:
        return a, b
    return max(lo, anchor - pad), min(hi, anchor + pad)


def _op_redact_row(doc: fitz.Document, op: dict, cfg: dict) -> int:
    """Redact the whole table ROW that contains an anchor phrase.

    Redacting only the phrase you can name is the classic way to redact
    nothing. A witness-list row holds a clinician's name in one cell and their
    street address and telephone number in the next two; covering the name
    leaves the person trivially identifiable by the identifiers beside it. The
    unit of redaction for tabular data is the row, not the phrase.

    Vertical extent comes from the horizontal ruling lines bracketing the
    anchor, so a row whose cells wrap to three lines is covered to its full
    height. Horizontal extent is the whole ruled table by default; pass
    "scope": "cell" to stay inside the vertical rules instead.

      {"type": "redact_row", "anchor_text": "Some Name",
       "scope": "row" | "cell", "label": "[... REDACTED]"}
    """
    anchor = op["anchor_text"]
    scope = op.get("scope", "row")
    label, dropped = sanitize_label(op.get("label", "[REDACTED]"))
    if dropped:
        print(f"  NOTE [redact_row] label characters not drawable, folded: "
              f"{''.join(sorted(set(dropped)))}", file=sys.stderr)
    fill = _color(cfg, "fill_color", [1.0, 1.0, 1.0])
    text_color = _color(cfg, "text_color", [0.0, 0.0, 0.0])
    font = cfg.get("label_font", "helv")
    font_size = float(cfg.get("label_font_size", 7))
    border_width = float(cfg.get("border_width", 0.5))

    page_idx = _find_page_by_text(doc, anchor)
    if page_idx is None:
        print(f"  WARNING [redact_row] could not find anchor '{anchor[:60]}'",
              file=sys.stderr)
        return 0
    page = doc[page_idx]
    hits = _deduplicate_rects(page.search_for(anchor))
    if not hits:
        return 0

    hrules = _rules(page, horizontal=True)
    vrules = _rules(page, horizontal=False)
    rects: list[fitz.Rect] = []
    for hit in hits:
        y0, y1 = _band((hit.y0 + hit.y1) / 2.0, hrules,
                       0.0, page.rect.height, hit.height * 1.2)
        col_x0, col_x1 = _page_column_x_range(page)
        # Only trust the vertical rules if enough of them were found to bound a
        # plausible table. A scan often yields ONE, and min()==max() then
        # collapses the rect to zero width -- the op reports success and
        # redacts nothing, which is the worst failure this tool can have.
        table_ok = len(vrules) >= 2 and (max(vrules) - min(vrules)) > page.rect.width * 0.3
        if scope == "cell" and table_ok:
            x0, x1 = _band((hit.x0 + hit.x1) / 2.0, vrules,
                           col_x0, col_x1, hit.width)
        elif table_ok:
            x0, x1 = min(vrules), max(vrules)
        else:
            x0, x1 = col_x0, col_x1
        if x1 - x0 < 20:
            x0, x1 = col_x0, col_x1
        rect = fitz.Rect(x0 + 0.6, y0 + 0.6, x1 - 0.6, y1 - 0.6)
        if rect.is_empty or rect.width < 10 or rect.height < 4:
            print(f"  WARNING [redact_row] degenerate rect {tuple(round(v) for v in rect)} "
                  f"for anchor '{anchor[:40]}'; refusing to draw a no-op box",
                  file=sys.stderr)
            continue
        rects.append(rect)

    if not rects:
        return 0
    for r in rects:
        _add_redact(page, r, label, fill, text_color, font, font_size)
    page.apply_redactions(graphics=1)
    _draw_borders(page, rects, border_width)
    print(f"  redact_row ({len(rects)} {scope}(s) on p.{page_idx+1}): "
          f"'{anchor[:44]}'")
    return len(rects)


def _op_redact_region(doc: fitz.Document, op: dict, cfg: dict) -> int:
    """Redact an explicit rectangle on an explicit 1-based page.

    The escape hatch for material no text search can reach: a signature, a
    handwritten annotation, a stamp, a photograph, a region of a scan whose
    OCR came out as noise. Coordinates are fractions of the page (0-1) so they
    survive a source re-render at a different scale.

      {"type": "redact_region", "page": 7,
       "rect": [0.10, 0.42, 0.95, 0.51], "label": "[REDACTED]"}
    """
    page_no = int(op["page"])
    if page_no < 1 or page_no > len(doc):
        print(f"  WARNING [redact_region] page {page_no} out of range "
              f"(1-{len(doc)})", file=sys.stderr)
        return 0
    fx0, fy0, fx1, fy1 = (float(v) for v in op["rect"])
    if not (0.0 <= fx0 < fx1 <= 1.0 and 0.0 <= fy0 < fy1 <= 1.0):
        print(f"  WARNING [redact_region] rect {op['rect']} is not an ordered "
              f"pair of 0-1 fractions", file=sys.stderr)
        return 0
    label, dropped = sanitize_label(op.get("label", "[REDACTED]"))
    if dropped:
        print(f"  NOTE [redact_region] label characters not drawable, folded: "
              f"{''.join(sorted(set(dropped)))}", file=sys.stderr)
    page = doc[page_no - 1]
    W, H = page.rect.width, page.rect.height
    rect = fitz.Rect(fx0 * W, fy0 * H, fx1 * W, fy1 * H)
    _add_redact(page, rect, label,
                _color(cfg, "fill_color", [1.0, 1.0, 1.0]),
                _color(cfg, "text_color", [0.0, 0.0, 0.0]),
                cfg.get("label_font", "helv"),
                float(cfg.get("label_font_size", 7)))
    page.apply_redactions(graphics=1)
    _draw_borders(page, [rect], float(cfg.get("border_width", 0.5)))
    print(f"  redact_region: p.{page_no} {op['rect']}")
    return 1


# ---------------------------------------------------------------------------
# Page-location helpers
# ---------------------------------------------------------------------------

def _find_page_by_text(doc: fitz.Document, needle: str) -> int | None:
    """Return the 0-based index of the first page containing needle, or None."""
    for i in range(len(doc)):
        if doc[i].search_for(needle):
            return i
    return None


def _find_text_rect(page: fitz.Page, text: str) -> fitz.Rect | None:
    """Return the bounding rect of the first hit of text on page, or None."""
    hits = page.search_for(text)
    if not hits:
        return None
    return hits[0]


def _find_text_rect_last(page: fitz.Page, text: str) -> fitz.Rect | None:
    """Return the bounding rect of the last hit of text on page, or None."""
    hits = page.search_for(text)
    if not hits:
        return None
    return hits[-1]


def _page_column_x_range(page: fitz.Page) -> tuple[float, float]:
    """Approximate the left/right x-range of the main text column."""
    blocks = page.get_text("dict")["blocks"]
    xs = []
    for b in blocks:
        if b["type"] != 0:
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    xs.append(span["bbox"][0])
    if not xs:
        return (50, page.rect.width - 30)
    x0 = min(xs)
    return (x0, page.rect.width - 30)


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------

def _op_seal_page_range(doc: fitz.Document, op: dict, cfg: dict) -> int:
    """Replace an explicit, 1-based inclusive page range with a placeholder.

    seal_pages locates its first page by searching for anchor text, which is
    the wrong tool for a scanned exhibit: the text layer is OCR output, so the
    anchor may be garbled, and the search is case-insensitive, so an anchor
    like "EXHIBIT 2" matches a body-text "Exhibit 2" many pages earlier and
    seals the wrong pages silently. When the pages are already known -- an
    exhibit running pp. 22-34, say -- name them.

      {"type": "seal_page_range", "first_page": 22, "last_page": 34,
       "replacement_text": "..."}

    Returns the number of pages sealed, or 0 if the range is out of bounds.
    """
    first = int(op["first_page"])
    last = int(op.get("last_page", first))
    if first < 1 or last < first or last > len(doc):
        print(f"  WARNING [seal_page_range] range {first}-{last} is out of bounds "
              f"for a {len(doc)}-page document", file=sys.stderr)
        return 0

    replacement_text: str = op.get("replacement_text", "[SEALED UNDER COURT ORDER]")
    border_width = float(cfg.get("border_width", 0.5))
    for pg_idx in range(first - 1, last):
        _blank_page(doc[pg_idx], replacement_text, border_width)
    print(f"  seal_page_range: sealed PDF pages {first}–{last}")
    return last - first + 1


def _blank_page(page, replacement_text: str, border_width: float) -> None:
    """White out a whole page and centre replacement text on it."""
    margin = 36  # 0.5 inch margin so the page doesn't look blank
    rect = fitz.Rect(
        page.rect.x0 + margin, page.rect.y0 + margin,
        page.rect.x1 - margin, page.rect.y1 - margin,
    )
    page.add_redact_annot(rect, fill=(1.0, 1.0, 1.0))
    page.apply_redactions(graphics=1)
    if border_width > 0:
        page.draw_rect(rect, color=(0.0, 0.0, 0.0), width=border_width)
    page.insert_textbox(
        rect, replacement_text, fontname="helv", fontsize=10,
        color=(0.0, 0.0, 0.0), align=1,
    )


def _op_seal_pages(doc: fitz.Document, op: dict, cfg: dict) -> int:
    """Replace one or more entire pages with a placeholder.

    Returns the number of pages sealed (0 = the anchor text was not found).
    """
    needle = op["find_text"]
    start_page = _find_page_by_text(doc, needle)
    if start_page is None:
        print(f"  WARNING [seal_pages] could not find '{needle}' in document", file=sys.stderr)
        return 0

    page_count = int(op.get("page_count", 1))
    replacement_text: str = op.get("replacement_text", "[SEALED UNDER COURT ORDER]")
    border_width = float(cfg.get("border_width", 0.5))

    for i in range(page_count):
        pg_idx = start_page + i
        if pg_idx >= len(doc):
            break
        page = doc[pg_idx]
        # Inset the redaction rect slightly so we can draw a visible border around it.
        margin = 36  # 0.5 inch margin so the page doesn't look blank
        rect = fitz.Rect(
            page.rect.x0 + margin, page.rect.y0 + margin,
            page.rect.x1 - margin, page.rect.y1 - margin,
        )

        # Fill with white (not black — saves ink, matches user preference).
        page.add_redact_annot(rect, fill=(1.0, 1.0, 1.0))
        page.apply_redactions(graphics=1)

        # Draw border around the seal area.
        if border_width > 0:
            page.draw_rect(rect, color=(0.0, 0.0, 0.0), width=border_width)

        # Insert centered replacement text in black.
        page.insert_textbox(
            rect,
            replacement_text,
            fontname="helv",
            fontsize=10,
            color=(0.0, 0.0, 0.0),
            align=1,  # center
        )
    print(f"  seal_pages: sealed PDF pages {start_page+1}–{start_page+page_count} "
          f"('{needle[:40]}')")
    return page_count


def _op_redact_block(doc: fitz.Document, op: dict, cfg: dict) -> int:
    """Redact a contiguous block from start_text through end_text.

    Returns the number of blocks redacted (0 = start_text was not found).
    """
    start_needle = op["start_text"]
    end_needle = op["end_text"]
    label = op.get("label", "[REDACTED]")
    fill = _color(cfg, "fill_color", [1.0, 1.0, 1.0])
    text_color = _color(cfg, "text_color", [0.0, 0.0, 0.0])
    font = cfg.get("label_font", "helv")
    font_size = float(cfg.get("label_font_size", 7))
    border_width = float(cfg.get("border_width", 0.5))

    # Find the page containing start_text.
    start_page = None
    start_rect = None
    for i in range(len(doc)):
        r = _find_text_rect(doc[i], start_needle)
        if r is not None:
            start_page = i
            start_rect = r
            break

    if start_page is None:
        print(f"  WARNING [redact_block] could not find start '{start_needle[:60]}'",
              file=sys.stderr)
        return 0

    page = doc[start_page]
    end_rect = _find_text_rect_last(page, end_needle)
    if end_rect is None:
        # Try the next page.
        if start_page + 1 < len(doc):
            end_rect = _find_text_rect_last(doc[start_page + 1], end_needle)
            if end_rect is not None:
                # Block spans two pages — redact to page bottom on first,
                # redact from page top to end on second.
                x0, x1 = _page_column_x_range(page)
                rect1 = fitz.Rect(x0 - 2, start_rect.y0 - 2, x1 + 2, page.rect.height - 40)
                _add_redact(page, rect1, label, fill, text_color, font, font_size)
                page.apply_redactions(graphics=1)
                _draw_borders(page, [rect1], border_width)

                page2 = doc[start_page + 1]
                x0b, x1b = _page_column_x_range(page2)
                rect2 = fitz.Rect(x0b - 2, 40, x1b + 2, end_rect.y1 + 2)
                _add_redact(page2, rect2, "", fill, text_color, font, font_size)
                page2.apply_redactions(graphics=1)
                _draw_borders(page2, [rect2], border_width)
                print(f"  redact_block (cross-page): '{start_needle[:40]}'")
                return 1

    if end_rect is None:
        # Fall back: redact from start to end of page.
        print(f"  WARNING [redact_block] could not find end '{end_needle[:60]}'; "
              f"redacting to page bottom", file=sys.stderr)
        x0, x1 = _page_column_x_range(page)
        cover = fitz.Rect(x0 - 2, start_rect.y0 - 2, x1 + 2, page.rect.height - 40)
    else:
        x0, x1 = _page_column_x_range(page)
        cover = fitz.Rect(x0 - 2, start_rect.y0 - 2, x1 + 2, end_rect.y1 + 2)

    _add_redact(page, cover, label, fill, text_color, font, font_size)
    page.apply_redactions(graphics=1)
    _draw_borders(page, [cover], border_width)
    print(f"  redact_block: '{start_needle[:50]}'")
    return 1


def _op_redact_clause(doc: fitz.Document, op: dict, cfg: dict) -> int:
    """Redact an exact phrase wherever it appears in the document.
    Returns the number of redactions applied.

    Optional op keys:
      page_anchor  — text that uniquely identifies the target page; if set,
                     only that page is searched (prevents false hits on
                     repeated phrases).
      max_hits     — integer; limit total redactions to at most this many.
    """
    needle = op["search_text"]
    label = op.get("label", "[REDACTED]")
    fill = _color(cfg, "fill_color", [1.0, 1.0, 1.0])
    text_color = _color(cfg, "text_color", [0.0, 0.0, 0.0])
    font = cfg.get("label_font", "helv")
    font_size = float(cfg.get("label_font_size", 7))
    border_width = float(cfg.get("border_width", 0.5))
    page_anchor = op.get("page_anchor")
    max_hits = op.get("max_hits")

    # Determine which pages to search.  Use pre-resolved page index if
    # available (resolved before any redactions ran, so it's reliable even
    # if a prior redaction consumed the anchor text on this page).
    if page_anchor is not None:
        anchor_pg = op.get("_resolved_page")
        if anchor_pg is None:
            print(f"  WARNING [redact_clause] page_anchor '{page_anchor}' not found; "
                  f"searching all pages", file=sys.stderr)
            page_range = range(len(doc))
        else:
            page_range = range(anchor_pg, anchor_pg + 1)
    else:
        page_range = range(len(doc))

    found = 0
    for i in page_range:
        page = doc[i]
        raw_hits = page.search_for(needle)
        if not raw_hits:
            continue
        # Deduplicate overlapping rects from multi-layer OCR PDFs.
        hits = _deduplicate_rects(
            [fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1) for r in raw_hits]
        )
        if max_hits is not None:
            hits = hits[:max_hits]
        for rect in hits:
            _add_redact(page, rect, label, fill, text_color, font, font_size)
            found += 1
        page.apply_redactions(graphics=1)
        _draw_borders(page, hits, border_width)

    if found == 0:
        print(f"  WARNING [redact_clause] no matches for '{needle[:60]}'", file=sys.stderr)
    else:
        print(f"  redact_clause ({found} hit{'s' if found != 1 else ''}): '{needle[:50]}'")
    return found


def _op_redact_sentences(doc: fitz.Document, op: dict, cfg: dict) -> int:
    """Redact from search_text to the end of that line cluster.
    Returns the number of redactions applied.

    Optional op keys: page_anchor, max_hits (same semantics as redact_clause).
    """
    needle = op["search_text"]
    label = op.get("label", "[REDACTED]")
    fill = _color(cfg, "fill_color", [1.0, 1.0, 1.0])
    text_color = _color(cfg, "text_color", [0.0, 0.0, 0.0])
    font = cfg.get("label_font", "helv")
    font_size = float(cfg.get("label_font_size", 7))
    border_width = float(cfg.get("border_width", 0.5))
    page_anchor = op.get("page_anchor")
    max_hits = op.get("max_hits")

    if page_anchor is not None:
        anchor_pg = op.get("_resolved_page")
        page_range = range(anchor_pg, anchor_pg + 1) if anchor_pg is not None else range(len(doc))
    else:
        page_range = range(len(doc))

    found = 0
    for i in page_range:
        page = doc[i]
        raw_hits = page.search_for(needle, quads=False)
        if not raw_hits:
            continue

        # Deduplicate, then group by line cluster.
        deduped = _deduplicate_rects(
            [fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1) for r in raw_hits]
        )
        if max_hits is not None:
            deduped = deduped[:max_hits]

        covers = []
        for rect in deduped:
            covers.append(rect)
            _add_redact(page, rect, label, fill, text_color, font, font_size)
            found += 1
        page.apply_redactions(graphics=1)
        _draw_borders(page, covers, border_width)

    if found == 0:
        print(f"  WARNING [redact_sentences] no matches for '{needle[:60]}'",
              file=sys.stderr)
    else:
        print(f"  redact_sentences ({found} hit{'s' if found != 1 else ''}): "
              f"'{needle[:50]}'")
    return found


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

HANDLERS = {
    "seal_pages":       _op_seal_pages,
    "seal_page_range":  _op_seal_page_range,
    "redact_row":       _op_redact_row,
    "redact_region":    _op_redact_region,
    "redact_block":     _op_redact_block,
    "redact_clause":    _op_redact_clause,
    "redact_sentences": _op_redact_sentences,
}


def _resolve_anchors(doc: fitz.Document, redactions: list[dict]) -> None:
    """Resolve every `page_anchor` text to a `_resolved_page` index, BEFORE
    any redactions run.  This prevents earlier redactions from consuming
    the anchor text that later operations depend on.

    Mutates each op dict in place by adding ``_resolved_page`` (0-based int,
    or None if the anchor was not found).
    """
    cache: dict[str, int | None] = {}
    for op in redactions:
        anchor = op.get("page_anchor")
        if anchor is None:
            continue
        if anchor not in cache:
            cache[anchor] = _find_page_by_text(doc, anchor)
        op["_resolved_page"] = cache[anchor]


def run(config_path: Path, force: bool = False) -> int:
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    base = config_path.parent
    source_pdf = (base / cfg["source_pdf"]).resolve()
    output_pdf = (base / cfg["output_pdf"]).resolve()

    stale, reason = is_stale(config_path.resolve(), source_pdf, output_pdf)
    if not stale and not force:
        print(f"  {output_pdf.name} is up to date", flush=True)
        return 0

    print(f"  building {output_pdf.name}: {reason if reason else 'forced'}", flush=True)

    if not source_pdf.exists():
        print(f"ERROR: source PDF not found: {source_pdf}", file=sys.stderr)
        return 1

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(source_pdf))

    redactions = cfg.get("redactions", [])
    _resolve_anchors(doc, redactions)

    # A redaction entry that matches nothing (or errors out) means the
    # sensitive text it names is still in the document. That must fail
    # the build — no output is written — rather than yield a "successful"
    # partially-redacted PDF.
    failures: list[str] = []
    for i, op in enumerate(redactions):
        # Skip comment/section-marker entries (keys starting with "_")
        if all(k.startswith("_") for k in op):
            continue
        op_type = op.get("type", "")
        desc = op.get("description", f"operation {i+1}")
        handler = HANDLERS.get(op_type)
        if handler is None:
            print(f"  ERROR: unknown operation type '{op_type}' in '{desc}'",
                  file=sys.stderr)
            failures.append(f"[{op_type or '?'}] {desc}: unknown operation type")
            continue
        print(f"  [{op_type}] {desc[:70]}", flush=True)
        try:
            applied = handler(doc, op, cfg)
        except Exception as exc:
            print(f"  ERROR in '{desc}': {exc}", file=sys.stderr)
            failures.append(f"[{op_type}] {desc}: {exc}")
            continue
        if not applied:
            needle = op.get("search_text") or op.get("start_text") or op.get("find_text", "")
            failures.append(f"[{op_type}] {desc}: no matches for '{needle[:60]}'")

    if failures:
        doc.close()
        print(f"ERROR: {len(failures)} redaction operation(s) had no effect; "
              f"refusing to write {output_pdf.name}:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    doc.save(str(output_pdf), garbage=4, deflate=True, clean=True)
    doc.close()
    print(f"  Wrote {output_pdf}", flush=True)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Redact a PDF according to a JSON config file."
    )
    parser.add_argument("config", help="Path to the JSON redaction config file")
    parser.add_argument("--force", action="store_true",
                        help="Rebuild even if output is up to date")
    parser.add_argument("--check-stale", action="store_true",
                        help="Exit 1 if output is stale, without rebuilding")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    if args.check_stale:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        base = config_path.parent
        source_pdf = (base / cfg["source_pdf"]).resolve()
        output_pdf = (base / cfg["output_pdf"]).resolve()
        stale, reason = is_stale(config_path, source_pdf, output_pdf)
        if stale:
            print(f"STALE: {reason}", file=sys.stderr)
            sys.exit(1)
        print("up to date")
        sys.exit(0)

    sys.exit(run(config_path, force=args.force))


if __name__ == "__main__":
    main()
