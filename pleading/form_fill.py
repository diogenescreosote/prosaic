#!/usr/bin/env python3
"""Descriptor-driven Judicial Council (and generic PDF) form filler.

The problem this solves: JC forms are fillable PDFs in theory, but in
practice their AcroForm/XFA layers are unreliable — fields are
mislabeled, appearances don't regenerate in some viewers, auto-size
text renders out of view, multiline fields clip silently, and long
answers simply don't fit. Filling them "the normal PDF way" produces
documents that look fine in one viewer and broken on the clerk's
screen.

The fix is to treat each form as *data*: a YAML descriptor in
``forms/registry/<form_id>.yaml`` records, for every logical field,
where it lives (AcroForm name or overlay rectangle), how it can fail,
and what to do about it (shrink, wrap, spill to a Judicial Council
MC-025 attachment). This module is the engine that executes
descriptors. See docs/forms.md for the descriptor schema and the
authoring workflow, and each descriptor's ``agent_guide`` for
form-specific usage.

Fill methods
------------
- ``acroform``: set the field value; regenerate nothing (viewers do,
  via /NeedAppearances) but *measure* the text against the widget
  rectangle and apply the field's ``fit`` strategy first.
- ``overlay``: ignore the widget (or absence of one) and draw the text
  directly on the page at ``rect`` with reportlab, merged in. This is
  the escape hatch for fields whose widgets are broken or missing.

Fit strategies (``fit:``)
-------------------------
- ``none``  (default): warn if the text overflows the box.
- ``shrink``: reduce font size (down to ``min_font_size``) until the
  text fits the box width (and height, for multiline).
- ``wrap``: wrap to multiple lines within the box (multiline fields /
  overlay rects); combine as ``shrink_wrap``.
- ``overflow_attachment``: if the text cannot fit even after
  shrink/wrap, put "See Attachment <N>." in the field and return the
  full text as an MC-025 attachment to append — the legally standard
  JC practice for overflow (Cal. Rules of Court 2.100 series).
- ``strict``: raise instead of producing an overflowing filing.

CLI
---
    python form_fill.py fill <form_id> --data data.yaml -o out.pdf
    python form_fill.py info <form_id>
    python form_fill.py fields <blank.pdf>       # descriptor skeleton
    python form_fill.py list
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (
        ArrayObject,
        BooleanObject,
        DictionaryObject,
        NameObject,
        TextStringObject,
    )
except ImportError as exc:  # pragma: no cover
    raise SystemExit("form_fill requires 'pypdf' (pip install pypdf)") from exc

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

import jc_common

PLEADING_DIR = Path(__file__).resolve().parent
REGISTRY_DIR = PLEADING_DIR / "forms" / "registry"
BLANKS_DIR = PLEADING_DIR / "forms"

DEFAULT_FONT = "Helvetica"
DEFAULT_FONT_SIZE = 9.0
DEFAULT_MIN_FONT_SIZE = 6.0
LEADING_RATIO = 1.15


# ---------------------------------------------------------------------------
# Descriptor loading
# ---------------------------------------------------------------------------

def list_forms() -> list[str]:
    return sorted(p.stem for p in REGISTRY_DIR.glob("*.yaml"))


def load_descriptor(form_id: str) -> dict:
    path = REGISTRY_DIR / f"{form_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No descriptor for form '{form_id}' (expected {path}). "
            f"Known forms: {', '.join(list_forms()) or '(none)'}"
        )
    desc = yaml.safe_load(path.read_text())
    for key in ("form", "blank", "fields"):
        if key not in desc:
            raise ValueError(f"{path}: descriptor missing required key '{key}'")
    return desc


def blank_path(desc: dict) -> Path:
    return BLANKS_DIR / desc["blank"]


# ---------------------------------------------------------------------------
# PDF introspection
# ---------------------------------------------------------------------------

def _qualified_name(annot_obj) -> str:
    """Reconstruct a widget's fully qualified field name via /Parent chain."""
    parts = []
    node = annot_obj
    seen = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        t = node.get("/T")
        if t:
            parts.append(str(t))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return ".".join(reversed(parts))


def _inherited(obj, key, default=None):
    """Look up an (inheritable) key on a widget, walking /Parent chain."""
    node = obj
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if key in node:
            return node[key]
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return default


def iter_widgets(reader: PdfReader):
    """Yield (page_index, qualified_name, annot_object) for every widget."""
    for page_idx, page in enumerate(reader.pages):
        for ref in page.get("/Annots") or []:
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Widget":
                yield page_idx, _qualified_name(obj), obj


def dump_fields(pdf_path: Path) -> list[dict]:
    """Introspect a blank form: one row per widget, for descriptor authoring."""
    reader = PdfReader(str(pdf_path))
    rows = []
    for page_idx, name, obj in iter_widgets(reader):
        rect = [round(float(v), 1) for v in (obj.get("/Rect") or [0, 0, 0, 0])]
        ftype = str(_inherited(obj, "/FT", "") or "")
        states: list[str] = []
        ap = obj.get("/AP")
        if ap and "/N" in ap.get_object():
            n = ap.get_object()["/N"]
            if hasattr(n, "keys"):
                states = [str(k) for k in n.keys()]
        flags = int(_inherited(obj, "/Ff", 0) or 0)
        rows.append({
            "name": name,
            "page": page_idx + 1,
            "type": ftype,
            "rect": rect,
            "tooltip": str(obj.get("/TU") or ""),
            "states": states,
            "multiline": bool(flags & (1 << 12)),
        })
    return rows


def skeleton_yaml(pdf_path: Path) -> str:
    """Emit a starter descriptor for a blank form (author then verifies)."""
    rows = dump_fields(pdf_path)
    lines = [
        f"form: {pdf_path.stem}",
        f'title: ""',
        "domain: ca/",
        'revision: ""',
        'source_url: ""',
        f"blank: {pdf_path.name}",
        "technology: acroform   # or xfa",
        "chrome_fields: []",
        "fields:",
    ]
    for r in rows:
        if r["type"] == "/Btn":
            continue
        safe = r["name"].split(".")[-1] or "field"
        lines += [
            f"  {safe}:",
            f'    map: "{r["name"]}"',
            f"    page: {r['page']}",
            f'    doc: "{r["tooltip"]}"' if r["tooltip"] else '    doc: ""',
        ]
        if r["multiline"]:
            lines.append("    fit: shrink_wrap")
    lines.append("checkboxes:")
    for r in rows:
        if r["type"] != "/Btn":
            continue
        on = [s for s in r["states"] if s != "/Off"]
        safe = r["name"].split(".")[-1] or "cb"
        lines += [
            f"  {safe}:",
            f'    map: "{r["name"]}"',
            f'    on_value: "{on[0] if on else "/1"}"',
            f'    doc: "{r["tooltip"]}"' if r["tooltip"] else '    doc: ""',
        ]
    lines.append('agent_guide: ""')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text fitting
# ---------------------------------------------------------------------------

def _wrap_to_width(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if stringWidth(f"{cur} {w}", font, size) <= width:
                cur = f"{cur} {w}"
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


@dataclass
class FitResult:
    text: str
    font_size: float
    lines: list[str]
    fits: bool


def fit_text(text: str, rect: list[float], spec: dict) -> FitResult:
    """Apply the field's fit strategy; report whether the text fits."""
    pad = 4.0
    width = abs(rect[2] - rect[0]) - pad
    height = abs(rect[3] - rect[1]) - 2.0
    strategy = str(spec.get("fit") or "none")
    size = float(spec.get("font_size") or DEFAULT_FONT_SIZE)
    # overflow_attachment fields do NOT shrink below full size by
    # default: microscopic-but-technically-fitting text is worse for a
    # court filing than a clean "See Attachment N." + MC-025. Authors
    # can opt into shrinking with an explicit min_font_size.
    default_min = (DEFAULT_FONT_SIZE if strategy == "overflow_attachment"
                   else DEFAULT_MIN_FONT_SIZE)
    min_size = float(spec.get("min_font_size") or default_min)
    font = str(spec.get("font") or DEFAULT_FONT)
    can_shrink = "shrink" in strategy or strategy == "overflow_attachment"
    can_wrap = ("wrap" in strategy or strategy == "overflow_attachment"
                or spec.get("multiline"))

    while True:
        lines = _wrap_to_width(text, font, size, width) if can_wrap else text.split("\n")
        widest = max((stringWidth(l, font, size) for l in lines), default=0.0)
        if len(lines) > 1:
            fits_h = len(lines) * size * LEADING_RATIO <= height
        else:
            # Single line: viewers vertically center the text in the
            # widget, and JC forms routinely give one-line fields a rect
            # exactly one font-size tall (some forms' are 9 pt). Requiring
            # leading + padding there falsely flags every caption fill;
            # the text fits whenever the font fits the raw rect height.
            fits_h = size <= abs(rect[3] - rect[1])
        fits = widest <= width and fits_h
        if fits or not can_shrink or size <= min_size:
            return FitResult(text=text, font_size=size, lines=lines, fits=fits)
        size -= 0.5


# ---------------------------------------------------------------------------
# The fill engine
# ---------------------------------------------------------------------------

@dataclass
class FillResult:
    output_path: Path
    warnings: list[str] = dc_field(default_factory=list)
    overflows: list[dict] = dc_field(default_factory=list)  # {label, text, field}


def resolve_values(desc: dict, meta: Optional[dict] = None,
                   data: Optional[dict] = None) -> tuple[dict, dict, list[str]]:
    """Compute logical-field → value from auto bindings, meta, and data.

    Precedence (low → high): field ``default`` → ``auto`` binding over
    ``meta`` → per-form block in meta (``forms: {<form_id>: {...}}``)
    → explicit ``data`` dict.
    """
    meta = meta or {}
    data = dict(data or {})
    form_block = ((meta.get("forms") or {}).get(desc["form"]) or {})
    problems: list[str] = []

    texts: dict[str, str] = {}
    for name, spec in (desc.get("fields") or {}).items():
        val = spec.get("default", "")
        auto = spec.get("auto")
        if auto:
            fn = jc_common.AUTO_BINDINGS.get(auto)
            if fn is None:
                problems.append(f"field {name}: unknown auto binding '{auto}'")
            else:
                val = fn(meta) or val
        if name in form_block:
            val = form_block[name]
        if name in data:
            val = data.pop(name)
        val = "" if val is None else str(val)
        if spec.get("required") and not val.strip():
            problems.append(f"required field '{name}' is empty")
        texts[name] = val

    checks: dict[str, bool] = {}
    explicit_checks: set[str] = set()
    for name, spec in (desc.get("checkboxes") or {}).items():
        val = spec.get("default", False)
        if name in form_block:
            val = form_block[name]
            explicit_checks.add(name)
        if name in data:
            val = data.pop(name)
            explicit_checks.add(name)
        checks[name] = bool(val)

    for leftover in data:
        problems.append(f"unknown field '{leftover}' (not in {desc['form']} descriptor)")
    return texts, checks, explicit_checks, problems


def _strip_named_widgets(writer: PdfWriter, names: set[str]) -> None:
    """Remove chrome widgets (buttons, privacy banners) from all pages."""
    if not names:
        return
    for page in writer.pages:
        if "/Annots" in page:
            kept = ArrayObject()
            for annot in page["/Annots"]:
                obj = annot.get_object()
                if _qualified_name(obj).split(".")[-1] in names or str(obj.get("/T") or "") in names:
                    continue
                kept.append(annot)
            page[NameObject("/Annots")] = kept
    catalog = writer._root_object  # type: ignore[attr-defined]
    if "/AcroForm" in catalog:
        af = catalog["/AcroForm"].get_object()
        if "/Fields" in af:
            kept_fields = ArrayObject()
            for f in af["/Fields"]:
                obj = f.get_object()
                if str(obj.get("/T") or "") in names:
                    continue
                kept_fields.append(f)
            af[NameObject("/Fields")] = kept_fields


def _strip_xfa(writer: PdfWriter) -> None:
    """Drop the XFA layer so viewers honor the AcroForm values we set.

    LiveCycle-era JC forms carry both an XFA template and AcroForm
    widgets; XFA-aware viewers prefer the XFA layer and would show the
    *unfilled* template. Removing /XFA makes every viewer read the
    AcroForm, which is the layer we fill.
    """
    catalog = writer._root_object  # type: ignore[attr-defined]
    if "/AcroForm" in catalog:
        af = catalog["/AcroForm"].get_object()
        if "/XFA" in af:
            del af[NameObject("/XFA")]


def _set_need_appearances(writer: PdfWriter) -> None:
    catalog = writer._root_object  # type: ignore[attr-defined]
    if "/AcroForm" in catalog:
        af = catalog["/AcroForm"].get_object()
        af[NameObject("/NeedAppearances")] = BooleanObject(True)


def _apply_font_size(annot_obj, size: float, font: str = "Helv") -> None:
    """Pin a widget's default appearance to a concrete font size.

    JC fields are often set to auto-size (``0 Tf``), which some viewers
    render microscopically or out of view; an explicit size is the
    reliable path once we've measured that the text fits.
    """
    annot_obj[NameObject("/DA")] = TextStringObject(f"/{font} {size:g} Tf 0 g")


def fill(form_id: str, output_path: Path, meta: Optional[dict] = None,
         data: Optional[dict] = None, strict: bool = False) -> FillResult:
    """Fill a form per its descriptor. See module docstring."""
    desc = load_descriptor(form_id)
    blank = blank_path(desc)
    if not blank.exists():
        raise FileNotFoundError(f"Blank form missing: {blank}")

    texts, checks, explicit_checks, problems = resolve_values(desc, meta, data)
    result = FillResult(output_path=output_path, warnings=problems)
    if problems and strict:
        raise ValueError(f"{form_id}: " + "; ".join(problems))

    reader = PdfReader(str(blank))
    writer = PdfWriter(clone_from=reader)

    # Index widgets by qualified name (and bare name as fallback).
    widgets: dict[str, tuple[int, Any]] = {}
    for page_idx, name, obj in iter_widgets(PdfReader(str(blank))):
        widgets.setdefault(name, (page_idx, name))
        widgets.setdefault(name.split(".")[-1], (page_idx, name))

    # Live widget objects in the writer, for /DA edits.
    writer_widgets: dict[str, Any] = {}
    for page in writer.pages:
        for ref in page.get("/Annots") or []:
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Widget":
                writer_widgets[_qualified_name(obj)] = obj

    acro_values_by_page: dict[int, dict[str, str]] = {}
    overlay_ops: dict[int, list[dict]] = {}

    fields = desc.get("fields") or {}
    for name, spec in fields.items():
        value = texts.get(name, "")
        method = spec.get("method", "acroform")

        if method == "overlay":
            if not value:
                continue
            rect = spec.get("rect")
            page_no = int(spec.get("page", 1)) - 1
            if not rect:
                result.warnings.append(f"{name}: overlay field missing rect; skipped")
                continue
            fitted = fit_text(value, rect, spec)
            if not fitted.fits:
                value, fitted = _handle_overflow(name, spec, value, rect, result)
            overlay_ops.setdefault(page_no, []).append({
                "rect": rect, "fit": fitted, "spec": spec,
            })
            continue

        # acroform
        mapped = spec.get("map")
        if not mapped:
            result.warnings.append(f"{name}: no map and method=acroform; skipped")
            continue
        hit = widgets.get(mapped)
        if hit is None:
            result.warnings.append(
                f"{name}: field '{mapped}' not found in {blank.name} — form revision drift?"
            )
            continue
        page_idx, qualified = hit
        wobj = writer_widgets.get(qualified)
        rect = [float(v) for v in (wobj.get("/Rect") if wobj is not None else [0, 0, 200, 12])]
        if value:
            fitted = fit_text(value, rect, spec)
            if not fitted.fits:
                value, fitted = _handle_overflow(name, spec, value, rect, result)
            if wobj is not None:
                _apply_font_size(wobj, fitted.font_size)
        acro_values_by_page.setdefault(page_idx, {})[qualified] = value

    # Overflow-linked checkboxes: a field spec may declare
    # ``overflow_checkbox`` (checked iff the value spilled to an
    # attachment) and/or ``inline_checkbox`` (checked iff the value fit
    # on the form). Applied only when the field has a value and the
    # checkbox wasn't explicitly set by the caller.
    overflowed = {ov["field"] for ov in result.overflows}
    for fname, fspec in fields.items():
        if not texts.get(fname, ""):
            continue
        ocb = fspec.get("overflow_checkbox")
        icb = fspec.get("inline_checkbox")
        if ocb and ocb not in explicit_checks:
            checks[ocb] = fname in overflowed
        if icb and icb not in explicit_checks:
            checks[icb] = fname not in overflowed

    for name, spec in (desc.get("checkboxes") or {}).items():
        if not checks.get(name):
            continue
        mapped = spec.get("map")
        hit = widgets.get(mapped or "")
        if hit is None:
            result.warnings.append(f"checkbox {name}: '{mapped}' not found — revision drift?")
            continue
        page_idx, qualified = hit
        on = spec.get("on_value") or "/1"
        wobj = writer_widgets.get(qualified)
        if wobj is not None:
            wobj[NameObject("/V")] = NameObject(on)
            wobj[NameObject("/AS")] = NameObject(on)
            node = wobj
            parent = node.get("/Parent")
            if parent is not None:
                parent.get_object()[NameObject("/V")] = NameObject(on)

    for page_idx, values in acro_values_by_page.items():
        writer.update_page_form_field_values(writer.pages[page_idx], values)

    if desc.get("technology") == "xfa":
        _strip_xfa(writer)
    _strip_named_widgets(writer, set(desc.get("chrome_fields") or []))
    _set_need_appearances(writer)

    # Merge overlays. ``whiteouts:`` (descriptor-level) paints white
    # rectangles first — the tool for static page junk that survives
    # widget removal, like the gray under-rectangles of stripped
    # privacy banners.
    whiteouts: dict[int, list] = {}
    for w in desc.get("whiteouts") or []:
        whiteouts.setdefault(int(w.get("page", 1)) - 1, []).append(w["rect"])
    if overlay_ops or whiteouts:
        import io
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        max_page = max([*overlay_ops, *whiteouts])
        for i in range(max_page + 1):
            for rect in whiteouts.get(i, []):
                c.setFillColorRGB(1, 1, 1)
                c.rect(min(rect[0], rect[2]), min(rect[1], rect[3]),
                       abs(rect[2] - rect[0]), abs(rect[3] - rect[1]),
                       fill=1, stroke=0)
            c.setFillColorRGB(0, 0, 0)
            for op in overlay_ops.get(i, []):
                rect, fitted, spec = op["rect"], op["fit"], op["spec"]
                font = str(spec.get("font") or DEFAULT_FONT)
                c.setFont(font, fitted.font_size)
                x = min(rect[0], rect[2]) + 2
                y_top = max(rect[1], rect[3]) - fitted.font_size
                for j, line in enumerate(fitted.lines):
                    c.drawString(x, y_top - j * fitted.font_size * LEADING_RATIO, line)
            c.showPage()
        c.save()
        buf.seek(0)
        overlay_reader = PdfReader(buf)
        for i, page in enumerate(writer.pages):
            if (i in overlay_ops or i in whiteouts) and i < len(overlay_reader.pages):
                page.merge_page(overlay_reader.pages[i])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as fh:
        writer.write(fh)

    # Materialize overflow attachments (MC-025), appended in order.
    if result.overflows:
        _append_mc025_attachments(output_path, meta or {}, result)
    return result


def _handle_overflow(name: str, spec: dict, value: str, rect: list[float],
                     result: FillResult) -> tuple[str, FitResult]:
    """Apply the overflow policy for text that cannot fit its box."""
    strategy = str(spec.get("fit") or "none")
    if strategy == "overflow_attachment":
        label = spec.get("attachment_label") or f"Attachment ({name})"
        result.overflows.append({"label": label, "text": value, "field": name})
        short = f"See {label}."
        return short, fit_text(short, rect, {**spec, "fit": "shrink"})
    if strategy == "strict":
        raise ValueError(f"field '{name}': text does not fit and fit=strict")
    result.warnings.append(
        f"field '{name}': text overflows its box "
        f"(fit={strategy or 'none'}) — verify rendering before filing"
    )
    return value, fit_text(value, rect, spec)


def _mc025_body_capacity(desc: dict) -> tuple[list[float], dict]:
    """Return (body widget rect, body field spec) from the MC-025 blank."""
    spec = (desc.get("fields") or {})["body"]
    target = spec.get("map", "")
    for _page, name, obj in iter_widgets(PdfReader(str(blank_path(desc)))):
        if name == target or name.split(".")[-1] == target:
            return [float(v) for v in obj["/Rect"]], spec
    raise ValueError("mc025 descriptor's body field not found in blank")


def _chunk_for_mc025(text: str, rect: list[float], spec: dict) -> list[str]:
    """Split overflow text into page-sized chunks that each FIT the
    MC-025 body box (measured, not guessed) — the form's own "Add pages
    as required" mechanism. Never lets text be silently clipped."""
    # Chunk at the size the field will actually RENDER (not the shrink
    # floor): pre-broken lines measured at a smaller size than the
    # render size re-wrap in the viewer into orphan fragments.
    size = float(spec.get("font_size") or DEFAULT_FONT_SIZE)
    font = str(spec.get("font") or DEFAULT_FONT)
    pad = 4.0
    width = abs(rect[2] - rect[0]) - pad
    height = abs(rect[3] - rect[1]) - 2.0
    per_page = max(1, int(height // (size * LEADING_RATIO)))
    lines = _wrap_to_width(text, font, size, width)
    return ["\n".join(lines[i:i + per_page]) for i in range(0, len(lines), per_page)]


def _append_mc025_attachments(main_pdf: Path, meta: dict, result: FillResult) -> None:
    """Append filled MC-025 page(s) per overflow to the output PDF.

    Text longer than one attachment page spans several MC-025s with
    "page N of M" filled — never silent truncation (spec:
    specs/pleading/forms/mc025.md)."""
    import tempfile
    readers = [PdfReader(str(main_pdf))]
    with tempfile.TemporaryDirectory() as td:
        for i, ov in enumerate(result.overflows):
            try:
                desc025 = load_descriptor("mc025")
                rect, body_spec = _mc025_body_capacity(desc025)
            except (FileNotFoundError, ValueError) as exc:
                result.warnings.append(
                    f"overflow '{ov['label']}': mc025 unavailable ({exc}); "
                    "attachment NOT generated"
                )
                continue
            chunks = _chunk_for_mc025(ov["text"], rect, body_spec)
            number = ov["label"].replace("Attachment", "").strip(" ()")
            for pageno, chunk in enumerate(chunks, 1):
                att = Path(td) / f"att{i}_{pageno}.pdf"
                data = {"attachment_number": number, "body": chunk}
                if len(chunks) > 1:
                    data["page_number"] = str(pageno)
                    data["page_total"] = str(len(chunks))
                fill("mc025", att, meta=meta, data=data)
                readers.append(PdfReader(str(att)))
        writer = PdfWriter()
        writer.clone_document_from_reader(readers[0])
        for r in readers[1:]:
            for page in r.pages:
                writer.add_page(page)
        with open(main_pdf, "wb") as fh:
            writer.write(fh)


# ---------------------------------------------------------------------------
# Cover-sheet cache + prepend (generic versions of the per-form helpers)
# ---------------------------------------------------------------------------

def find_case_dir(input_md: Path) -> Path:
    for ancestor in input_md.parents:
        if ancestor.name == "src":
            return ancestor.parent
    return input_md.parent.parent


def ensure_cached(form_id: str, meta: dict, input_md: Path) -> Path:
    """Return a cached filled form for a pleading source, refreshing if stale."""
    desc = load_descriptor(form_id)
    case_dir = find_case_dir(input_md)
    cache = case_dir / "assets" / "decl_cover_sheets" / f"{input_md.stem}.{form_id}.pdf"
    blank = blank_path(desc)
    descriptor_file = REGISTRY_DIR / f"{form_id}.yaml"
    fresh = (
        cache.exists()
        and cache.stat().st_mtime >= input_md.stat().st_mtime
        and cache.stat().st_mtime >= blank.stat().st_mtime
        and cache.stat().st_mtime >= descriptor_file.stat().st_mtime
    )
    if not fresh:
        res = fill(form_id, cache, meta=meta)
        for w in res.warnings:
            print(f"  [form {form_id}] {w}", file=sys.stderr)
    return cache


def prepend(main_pdf: Path, cover_pdf: Path) -> None:
    """Prepend ``cover_pdf`` to ``main_pdf`` in place (fields stay live)."""
    cover_reader = PdfReader(str(cover_pdf))
    main_reader = PdfReader(str(main_pdf))
    writer = PdfWriter()
    writer.clone_document_from_reader(cover_reader)
    for page in main_reader.pages:
        writer.add_page(page)
    with open(main_pdf, "wb") as fh:
        writer.write(fh)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("fill", help="fill a form from a YAML data file")
    sp.add_argument("form_id")
    sp.add_argument("--data", help="YAML file of logical field values")
    sp.add_argument("--meta", help="YAML file of pleading front matter (caption autos)")
    sp.add_argument("-o", "--output", required=True)

    sp = sub.add_parser("info", help="show a form's agent guide + field schema")
    sp.add_argument("form_id")

    sp = sub.add_parser("fields", help="introspect a blank PDF; emit descriptor skeleton")
    sp.add_argument("pdf")

    sub.add_parser("list", help="list registered forms")

    args = p.parse_args()
    if args.cmd == "list":
        for f in list_forms():
            d = load_descriptor(f)
            print(f"{f:<10} {d.get('title', '')}  [{d.get('domain', '')} rev {d.get('revision', '?')}]")
        return 0
    if args.cmd == "fields":
        print(skeleton_yaml(Path(args.pdf)))
        return 0
    if args.cmd == "info":
        d = load_descriptor(args.form_id)
        print(f"# {d['form']} — {d.get('title', '')}")
        print(f"# domain: {d.get('domain')}  revision: {d.get('revision')}  blank: {d['blank']}")
        print()
        print(d.get("agent_guide", "").strip())
        print("\n## fields")
        for name, spec in (d.get("fields") or {}).items():
            bits = [spec.get("doc", "")]
            if spec.get("auto"):
                bits.append(f"auto={spec['auto']}")
            if spec.get("fit"):
                bits.append(f"fit={spec['fit']}")
            if spec.get("required"):
                bits.append("REQUIRED")
            print(f"  {name}: {'; '.join(b for b in bits if b)}")
        if d.get("checkboxes"):
            print("\n## checkboxes")
            for name, spec in d["checkboxes"].items():
                print(f"  {name}: {spec.get('doc', '')}")
        return 0
    if args.cmd == "fill":
        data = yaml.safe_load(Path(args.data).read_text()) if args.data else {}
        meta = yaml.safe_load(Path(args.meta).read_text()) if args.meta else {}
        res = fill(args.form_id, Path(args.output), meta=meta, data=data)
        for w in res.warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(f"wrote {res.output_path}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
