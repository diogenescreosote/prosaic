"""Inspect a filled form the way a reader does: by what is on the page.

A filled Judicial Council form is flattened ink (ADR-0046) — it carries
no field values to read back — so tests ask what text was drawn inside
the rectangle a logical field or checkbox occupies. Rectangles come
from the descriptor (``rect:``) or from the blank's widget of the same
``map:`` name, exactly as the fill resolved them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fitz  # pymupdf

PLEADING = Path(__file__).resolve().parent.parent
if str(PLEADING) not in sys.path:
    sys.path.insert(0, str(PLEADING))

import form_fill  # noqa: E402
from pypdf import PdfReader  # noqa: E402

CHECK_MARK = "X"


def page_text(pdf: Path, page_no: int) -> str:
    """pdftotext of one 1-based page."""
    return subprocess.run(
        ["pdftotext", "-f", str(page_no), "-l", str(page_no), str(pdf), "-"],
        capture_output=True, text=True).stdout


def all_text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", str(pdf), "-"],
                          capture_output=True, text=True).stdout


def has_no_form_layer(pdf: Path) -> bool:
    """True when nothing interactive survived: no widget on any page and
    no form dictionary in the catalog."""
    reader = PdfReader(str(pdf))
    if "/AcroForm" in reader.trailer["/Root"]:
        return False
    return not any(True for _ in form_fill.iter_widgets(reader))


def blank_rects(form_id: str) -> dict[str, tuple[int, list[float]]]:
    """(page index, rect) of every widget on the form's blank, keyed by
    qualified name and by bare leaf name."""
    desc = form_fill.load_descriptor(form_id)
    out: dict[str, tuple[int, list[float]]] = {}
    for page_idx, name, obj in form_fill.iter_widgets(
            PdfReader(str(form_fill.blank_path(desc)))):
        rect = [float(v) for v in (obj.get("/Rect") or [0, 0, 0, 0])]
        out.setdefault(name, (page_idx, rect))
        out.setdefault(name.split(".")[-1], (page_idx, rect))
    return out


def rect_of(form_id: str, logical: str, section: str = "fields") -> tuple[int, list[float]]:
    """Where the fill draws ``logical``: its own ``rect:``, else its
    mapped widget's rectangle on the blank."""
    desc = form_fill.load_descriptor(form_id)
    spec = desc[section][logical]
    if spec.get("rect"):
        return int(spec.get("page", 1)) - 1, list(spec["rect"])
    hit = blank_rects(form_id).get(spec.get("map", ""))
    if hit is None:
        raise KeyError(f"{form_id}.{logical}: no rect and no widget named {spec.get('map')!r}")
    return hit


def text_in_rect(pdf: Path, page_idx: int, rect: list[float], inset: float = 1.0) -> str:
    """Text whose glyphs lie inside ``rect`` (PDF user space, origin
    bottom-left) on the given page of the flattened output."""
    doc = fitz.open(str(pdf))
    try:
        page = doc[page_idx]
        x0, x1 = min(rect[0], rect[2]) + inset, max(rect[0], rect[2]) - inset
        y0, y1 = min(rect[1], rect[3]) + inset, max(rect[1], rect[3]) - inset
        h = page.rect.height
        clip = fitz.Rect(x0, h - y1, x1, h - y0)
        words = [w[4] for w in page.get_text("words")
                 if fitz.Rect(w[:4]).intersects(clip)
                 and (fitz.Rect(w[:4]) & clip).get_area() > 0.5 * fitz.Rect(w[:4]).get_area()]
        return " ".join(words)
    finally:
        doc.close()


def draw_rect(form_id: str, logical: str) -> tuple[int, list[float]]:
    """Where the fill actually draws ``logical``: its widget rect widened
    to the layout the blank's geometry gives it — the cell's free area
    for a box, the rule's span for a line (ADR-0046)."""
    desc = form_fill.load_descriptor(form_id)
    page_idx, rect = rect_of(form_id, logical, "fields")
    lay = form_fill.resolve_layout(rect, desc["fields"][logical],
                                   form_fill.page_geometry(form_fill.blank_path(desc), page_idx))
    x0, y0, x1, y1 = min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])
    if lay is not None and lay.kind == "box" and lay.area:
        ax0, ay0, ax1, ay1 = lay.area
        x0, y0, x1, y1 = min(x0, ax0), min(y0, ay0), max(x1, ax1), max(y1, ay1)
    elif lay is not None and lay.kind == "line" and lay.rule:
        rx0, ry, rx1 = lay.rule
        x0, y0, x1 = min(x0, rx0), min(y0, ry), max(x1, rx1)
    return page_idx, [x0, y0, x1, y1]


def field_text(pdf: Path, form_id: str, logical: str) -> str:
    page_idx, rect = draw_rect(form_id, logical)
    return text_in_rect(pdf, page_idx, rect)


def checkbox_marked(pdf: Path, form_id: str, logical: str) -> bool:
    page_idx, rect = rect_of(form_id, logical, "checkboxes")
    return CHECK_MARK in text_in_rect(pdf, page_idx, rect, inset=0.0).split()


def widget_text(pdf: Path, form_id: str, name_suffix: str) -> list[str]:
    """Text drawn inside every blank widget whose qualified name ends
    with ``name_suffix`` — for asserting that a region a human owns
    (a signature line, a date) received nothing."""
    out = []
    seen: set[tuple[int, tuple[float, ...]]] = set()
    for name, (page_idx, rect) in blank_rects(form_id).items():
        if not name.endswith(name_suffix):
            continue
        key = (page_idx, tuple(rect))
        if key in seen:
            continue
        seen.add(key)
        out.append(text_in_rect(pdf, page_idx, rect))
    return out
