#!/usr/bin/env python3
"""Place yellow highlight annotations on phrases in a PDF, anchored to the
printed words rather than to the text layer.

Why this exists: highlighting with `page.search_for` on the text layer
puts the box where the text layer says the words are. On an image-only
scan there is no text layer at all, and on a scan that ocrmypdf has
deskewed the OCR layer is often shifted from the picture, so the box
lands beside the words a reader sees. This tool can instead render the
page, OCR the picture with tesseract, and draw the box on the pixels
that carry the phrase.

Modes:
  text   the text layer only (fast; exact on born-digital PDFs)
  image  render each page and OCR it; never consults the text layer
  auto   text layer first; a page with no text layer, or a phrase the
         text layer does not find, falls back to the image (default)

The original is never modified: output always goes to a new path, and
the tool refuses an output path that is the input. With --pages the
output is an excerpt holding only the selected pages.

The report on stdout names, per output page, how many rectangles were
placed and by which mode, then lists every phrase that matched on no
selected page. Any such miss exits 2, so a build script can notice.

Usage:
    python3 highlight_pdf.py <in.pdf> <out.pdf> --phrase "..." [--phrase ...]
                             [--pages 1,4-6] [--dpi 200] [--mode auto|text|image]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz  # type: ignore[no-redef]

MODES = ("auto", "text", "image")
MAX_NOISE = 2          # stray tokens tolerated between two matched words
PREFIX_MIN = 4         # tokens at least this long may match by prefix
PAD_PT = 1.0           # vertical padding on each highlight rectangle


# ---------------------------------------------------------------------------
# Page selection (the pleading spec's `pages` syntax: 1-indexed, ranges,
# commas, open-ended `3-` and `-5`)
# ---------------------------------------------------------------------------

def parse_pages(spec: Optional[str], total: int) -> List[int]:
    """Return 0-based page indices in the order given; all pages if no spec.

    Every referenced page must exist: an out-of-range or reversed range
    is an error, never silently clamped, because a truncated excerpt is
    a defect.
    """
    if spec is None or not spec.strip():
        return list(range(total))

    def number(tok: str, what: str) -> int:
        tok = tok.strip()
        if not tok.isdigit():
            raise ValueError(f"invalid --pages {spec!r}: {tok!r} is not a page number")
        n = int(tok)
        if not 1 <= n <= total:
            raise ValueError(
                f"invalid --pages {spec!r}: page {n} does not exist "
                f"(PDF has {total} page{'s' if total != 1 else ''})"
            )
        return n

    out: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"invalid --pages {spec!r}: empty entry")
        if "-" in part:
            a, b = part.split("-", 1)
            s = number(a, "start") if a.strip() else 1
            e = number(b, "end") if b.strip() else total
            if s > e:
                raise ValueError(f"invalid --pages {spec!r}: range {part!r} is reversed")
            out.extend(range(s - 1, e))
        else:
            out.append(number(part, "page") - 1)
    return out


# ---------------------------------------------------------------------------
# Image mode: tesseract word boxes and token-sequence matching
# ---------------------------------------------------------------------------

LineKey = Tuple[str, str, str]   # (block, paragraph, line) from the TSV


@dataclass
class Word:
    """One OCR token. `boxes` holds one (line, rect) per printed fragment,
    so a word hyphenated across two lines carries two boxes."""
    t: str
    boxes: List[Tuple[LineKey, "fitz.Rect"]] = field(default_factory=list)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tokens_of(phrase: str) -> List[str]:
    return [t for t in (norm(p) for p in phrase.split()) if t]


def is_noise(t: str) -> bool:
    """A token that may be interleaved with the real words: pleading line
    numbers and the odd stray glyph. Single letters are noise except the
    words "i" and "a"."""
    return not t or (t.isdigit() and len(t) <= 2) or (len(t) == 1 and t not in ("i", "a"))


def tokens_match(w: str, t: str) -> bool:
    """Exact, or a prefix either way for tokens long enough that a prefix
    is informative (a hyphenated fragment, an OCR slip at the tail)."""
    if w == t:
        return True
    return len(t) >= PREFIX_MIN and len(w) >= PREFIX_MIN and (w.startswith(t) or t.startswith(w))


def parse_tsv(tsv: str, to_page: "fitz.Matrix") -> List[Word]:
    """Words from `tesseract ... tsv`, with pixel boxes mapped through
    `to_page` into PDF points. A word ending in a hyphen whose successor
    sits on another line is joined with that successor into one token."""
    raw: List[Tuple[str, LineKey, "fitz.Rect"]] = []
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) != 12 or f[0] != "5":
            continue
        text = f[11].strip()
        if not text:
            continue
        try:
            x, y, w, h = int(f[6]), int(f[7]), int(f[8]), int(f[9])
        except ValueError:
            continue
        rect = fitz.Rect(x, y, x + w, y + h) * to_page
        rect.normalize()
        raw.append((text, (f[2], f[3], f[4]), rect))

    words: List[Word] = []
    i = 0
    while i < len(raw):
        text, line, rect = raw[i]
        t = norm(text)
        if not t:
            i += 1
            continue
        if (text.endswith("-") and i + 1 < len(raw) and raw[i + 1][1] != line
                and norm(raw[i + 1][0])):
            nt, nline, nrect = raw[i + 1]
            words.append(Word(t + norm(nt), [(line, rect), (nline, nrect)]))
            i += 2
            continue
        words.append(Word(t, [(line, rect)]))
        i += 1
    return words


def find_phrase(words: Sequence[Word], phrase: str) -> List[List[Word]]:
    """Every occurrence of `phrase` as a token sequence in `words`, each
    as the list of words it spans. Up to MAX_NOISE noise tokens may sit
    between two consecutive matched words; none before the first."""
    toks = tokens_of(phrase)
    if not toks:
        return []
    n = len(toks)
    hits: List[List[Word]] = []
    for i in range(len(words)):
        if not tokens_match(words[i].t, toks[0]):
            continue
        j, k, skips = i, 0, 0
        used: List[Word] = []
        while k < n and j < len(words):
            if tokens_match(words[j].t, toks[k]):
                used.append(words[j]); j += 1; k += 1; skips = 0
            elif used and skips < MAX_NOISE and is_noise(words[j].t):
                j += 1; skips += 1
            else:
                break
        if k == n:
            hits.append(used)
    return hits


def line_rects(hit: Sequence[Word]) -> List["fitz.Rect"]:
    """One rectangle per printed line of a match, padded vertically."""
    lines: Dict[LineKey, "fitz.Rect"] = {}
    for w in hit:
        for line, rect in w.boxes:
            if line in lines:
                lines[line].include_rect(rect)
            else:
                lines[line] = fitz.Rect(rect)
    out = []
    for r in lines.values():
        r.y0 -= PAD_PT
        r.y1 += PAD_PT
        out.append(r)
    return out


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_words(page: "fitz.Page", dpi: int) -> List[Word]:
    """Render the page at `dpi`, OCR it, return its words in page points."""
    zoom = dpi / 72.0
    mat = page.rotation_matrix * fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    fd, png = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        pix.save(png)
        proc = subprocess.run(
            ["tesseract", png, "stdout", "--psm", "6", "tsv"],
            capture_output=True, text=True,
        )
    finally:
        os.unlink(png)
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed on page {page.number + 1}: {proc.stderr.strip()}")
    return parse_tsv(proc.stdout, ~mat)


# ---------------------------------------------------------------------------
# Text mode
# ---------------------------------------------------------------------------

def text_rects(page: "fitz.Page", phrase: str) -> List["fitz.Rect"]:
    """One rectangle per line of each occurrence in the text layer."""
    rects: List["fitz.Rect"] = []
    for quad in page.search_for(phrase, quads=True):
        r = quad.rect
        r.y0 -= PAD_PT
        r.y1 += PAD_PT
        rects.append(r)
    return rects


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

@dataclass
class PageReport:
    out_page: int          # 1-based in the output
    src_page: int          # 1-based in the input
    count: int
    modes: List[str]


def highlight(
    src: str,
    dst: str,
    phrases: Sequence[str],
    pages: Optional[str] = None,
    dpi: int = 200,
    mode: str = "auto",
    log=print,
) -> Tuple[List[PageReport], List[str]]:
    """Write `dst`: the selected pages of `src` with the phrases
    highlighted. Returns per-page reports and the phrases that matched on
    no selected page."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    if not phrases:
        raise ValueError("at least one --phrase is required")
    if os.path.exists(dst) and os.path.samefile(src, dst):
        raise ValueError("output path is the input; the original is never modified")
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("output path is the input; the original is never modified")

    have_tesseract = tesseract_available()
    if mode == "image" and not have_tesseract:
        raise RuntimeError(
            "tesseract is not installed (needed for --mode image); "
            "install it (brew install tesseract / apt install tesseract-ocr-eng) "
            "or use --mode text"
        )
    warned_no_tesseract = False

    with fitz.open(src) as sdoc:
        indices = parse_pages(pages, sdoc.page_count)
        out = fitz.open()
        for idx in indices:
            out.insert_pdf(sdoc, from_page=idx, to_page=idx)

    reports: List[PageReport] = []
    found = {p: False for p in phrases}
    try:
        for n, page in enumerate(out):
            count = 0
            modes_used: List[str] = []
            pending = list(phrases)

            has_text = mode != "image" and bool(page.get_text("words"))
            if has_text:
                still: List[str] = []
                for ph in pending:
                    rects = text_rects(page, ph)
                    if rects:
                        for r in rects:
                            page.add_highlight_annot(r)
                        count += len(rects)
                        found[ph] = True
                    else:
                        still.append(ph)
                if count:
                    modes_used.append("text")
                pending = still if mode == "auto" else []

            if pending and mode in ("auto", "image"):
                if not have_tesseract:
                    if not warned_no_tesseract:
                        log("warning: tesseract not installed; image fallback unavailable",
                            file=sys.stderr)
                        warned_no_tesseract = True
                else:
                    words = ocr_words(page, dpi)
                    placed = 0
                    for ph in pending:
                        for hit in find_phrase(words, ph):
                            for r in line_rects(hit):
                                page.add_highlight_annot(r)
                                placed += 1
                            found[ph] = True
                    if placed:
                        modes_used.append("image")
                    count += placed

            reports.append(PageReport(n + 1, indices[n] + 1, count, modes_used))

        out.save(dst, garbage=3, deflate=True)
    finally:
        out.close()

    misses = [p for p in phrases if not found[p]]
    return reports, misses


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Highlight phrases in a PDF, anchored to the printed words.",
        epilog="Exit status: 0 all phrases placed; 2 some phrase matched nowhere; 1 error.",
    )
    ap.add_argument("src", help="input PDF (never modified)")
    ap.add_argument("dst", help="output PDF (the selected pages, highlighted)")
    ap.add_argument("--phrase", action="append", required=True,
                    help="phrase to highlight; repeat for several")
    ap.add_argument("--pages", help="pages to keep, 1-indexed: 1,4-6 (default: all)")
    ap.add_argument("--dpi", type=int, default=200, help="render resolution for OCR (default 200)")
    ap.add_argument("--mode", choices=MODES, default="auto",
                    help="auto (default): text layer, then image where it fails; "
                         "text: text layer only; image: OCR the picture only")
    args = ap.parse_args(argv)

    try:
        reports, misses = highlight(
            args.src, args.dst, args.phrase, pages=args.pages, dpi=args.dpi, mode=args.mode
        )
    except (ValueError, RuntimeError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    total = 0
    for r in reports:
        how = ", ".join(r.modes) if r.modes else "none"
        print(f"page {r.out_page} (source page {r.src_page}): "
              f"{r.count} highlight{'s' if r.count != 1 else ''} ({how})")
        total += r.count
    print(f"wrote {args.dst}: {len(reports)} page{'s' if len(reports) != 1 else ''}, "
          f"{total} highlight{'s' if total != 1 else ''}")
    if misses:
        print(f"NOT FOUND on any selected page ({len(misses)}):")
        for m in misses:
            print(f"  {m!r}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
