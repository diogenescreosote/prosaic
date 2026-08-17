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
