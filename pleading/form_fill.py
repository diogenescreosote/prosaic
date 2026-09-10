#!/usr/bin/env python3
"""Descriptor-driven Judicial Council (and generic PDF) form filler.

The problem this solves: JC forms are fillable PDFs in theory, but in
practice how a filled field renders is a property of the viewer, not
of the file — appearance streams go stale, auto-size text vanishes,
multiline boxes clip, an inherited value on a group node makes
untouched siblings render garbage, and a page-level merge into a
packet drops the form dictionary altogether. What a clerk sees is
then a guess about the clerk's PDF reader.

The fix is to treat each form as *data* and never as a form: a YAML
descriptor in ``forms/registry/<form_id>.yaml`` records, for every
logical field, where it lives on the page, how it can fail, and what
to do about it (shrink, wrap, spill to a Judicial Council MC-025
attachment). This module is the engine that executes descriptors. See
docs/forms.md for the descriptor schema and the authoring workflow,
and each descriptor's ``agent_guide`` for form-specific usage.

The one technology (``technology: overlay``)
--------------------------------------------
Every field and checkbox is drawn directly on the page as ordinary
content — a ``map:`` names a widget on the blank only to borrow its
rectangle (and its multiline flag); a field with no widget carries a
hand-authored ``rect:`` — and the output is then FLATTENED: widget
appearances are baked into page content, every widget annotation and
the AcroForm dictionary are removed, viewer chrome (Print/Save/Clear
buttons, privacy banners) is stripped first so it is never baked in.
What is written is plain ink that renders identically everywhere and
survives packet assembly (ADR-0033, ADR-0037, ADR-0046). No field
value is ever written into the PDF's form layer, and a descriptor
declaring any other technology is refused at load.

``size_group:`` on fields keeps related boxes visually consistent:
every member renders at the smallest size any member needed to fit.

Fit strategies (``fit:``)
-------------------------
- ``none``  (default): warn if the text overflows the box.
- ``shrink``: reduce font size (down to ``min_font_size``) until the
  text fits the box width (and height, for multiline).
- ``wrap``: wrap to multiple lines within the box; combine as
  ``shrink_wrap``. A field whose widget is multiline wraps under
  ``shrink`` too.
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
import re
import os
import sys
import tempfile
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, NameObject
except ImportError as exc:  # pragma: no cover
    raise SystemExit("form_fill requires 'pypdf' (pip install pypdf)") from exc

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

import jc_common

PLEADING_DIR = Path(__file__).resolve().parent
REPO_ROOT = PLEADING_DIR.parent
# Local modules (ADR-0032): a gitignored local/ tree mirrors the repo
# layout and overlays it. Module repos (ADR-0034): commit-pinned
# checkouts (usually git submodules) under modules/<name>/, each
# mirroring the repo layout, scanned in alphabetical order. Discovery
# precedence, first hit wins: local/ → modules/<name>/ → built-in — so
# a deployment can patch a stock or module form without editing either
# repo.
# PROSAIC_LAYERS_ROOT points the overlay scan at another checkout's
# local/ and modules/ --- how a candidate engine is checked against a
# deployment's descriptors before it is merged (`sc form check`).
LAYERS_ROOT = Path(os.environ.get("PROSAIC_LAYERS_ROOT") or REPO_ROOT).resolve()
LOCAL_PLEADING_DIR = LAYERS_ROOT / "local" / "pleading"
MODULES_DIR = LAYERS_ROOT / "modules"


def _overlay_dirs(*sub: str) -> list[Path]:
    dirs = [LOCAL_PLEADING_DIR.joinpath(*sub)]
    if MODULES_DIR.is_dir():
        dirs += [m / "pleading" / Path(*sub)
                 for m in sorted(MODULES_DIR.iterdir()) if m.is_dir()]
    dirs.append(PLEADING_DIR.joinpath(*sub))
    return [d for d in dirs if d.is_dir()]


def registry_dirs() -> list[Path]:
    return _overlay_dirs("forms", "registry")


def blanks_dirs() -> list[Path]:
    return _overlay_dirs("forms")


# Back-compat names (snapshot at import; internal code calls the
# functions so tests and long-lived processes see modules appear).
REGISTRY_DIRS = registry_dirs()
BLANKS_DIRS = blanks_dirs()
REGISTRY_DIR = PLEADING_DIR / "forms" / "registry"
BLANKS_DIR = PLEADING_DIR / "forms"

DEFAULT_FONT = "Helvetica"
DEFAULT_FONT_SIZE = 9.0
DEFAULT_MIN_FONT_SIZE = 6.0
LEADING_RATIO = 1.15

# E-sign field taxonomy: the least common multiple of DocuSeal,
# DocuSign, and Dropbox Sign field types — every type here maps onto a
# native type on each platform (platforms lacking name/email render
# them as text). A descriptor tags a field with
# ``esign: {type: date, party: filer}``; parties are declared in
# descriptor-level ``esign_parties:`` (abstract role names — petitioner,
# attorney_for_petitioner, server — in signing order). See ADR-0033.
ESIGN_TYPES = {"signature", "initials", "date", "name",
               "email", "phone", "text", "checkbox"}

# Geometry-preview palette. Parties get colors by their position in
# ``esign_parties`` (party 1 red, 2 blue, 3 green, 4 orange).
PARTY_COLORS = [(0.80, 0.12, 0.12), (0.10, 0.30, 0.80),
                (0.10, 0.55, 0.20), (0.75, 0.45, 0.00)]
FIELD_BOX_COLOR = (0.25, 0.45, 0.85)
CHECKBOX_COLOR = (0.45, 0.30, 0.70)


# ---------------------------------------------------------------------------
# Descriptor loading
# ---------------------------------------------------------------------------

def list_forms() -> list[str]:
    return sorted({p.stem for d in registry_dirs() for p in d.glob("*.yaml")})


def _registry_path(form_id: str):
    for d in registry_dirs():
        candidate = d / f"{form_id}.yaml"
        if candidate.exists():
            return candidate
    return None


def load_descriptor(form_id: str) -> dict:
    path = _registry_path(form_id)
    if path is None:
        path = REGISTRY_DIR / f"{form_id}.yaml"
        raise FileNotFoundError(
            f"No descriptor for form '{form_id}' (expected {path}"
            f" or a local/ overlay). "
            f"Known forms: {', '.join(list_forms()) or '(none)'}"
        )
    desc = yaml.safe_load(path.read_text())
    for key in ("form", "blank", "fields"):
        if key not in desc:
            raise ValueError(f"{path}: descriptor missing required key '{key}'")
    _require_overlay(form_id, desc, path)
    return desc


def _require_overlay(form_id: str, desc: dict, path: Path) -> None:
    """Overlay is the only fill technology there is (ADR-0037, ADR-0046).

    How a form-layer fill renders is a property of the viewer, not of
    the file, so what a court receives is not knowable from here.
    Overlay draws every value as page content and flattens, which is
    why it also survives the page-level merges used to assemble a
    packet. A descriptor must say so explicitly: an absent key is
    refused too, so that no descriptor's behaviour rests on a default.
    """
    tech = str(desc.get("technology") or "").strip().lower()
    if tech == "overlay":
        return
    stated = f"technology: {tech}" if tech else "no technology key"
    raise ValueError(
        f"{path}: {stated} is not permitted for {form_id}. Judicial Council "
        "forms are filled by drawing text onto the page and flattening "
        "(technology: overlay, ADR-0037/ADR-0046); form-layer values are "
        "never written, because how they render is a property of the "
        "viewer rather than of the file. Write `technology: overlay` and "
        "check the geometry with `sc form preview`."
    )


def blank_path(desc: dict) -> Path:
    for d in blanks_dirs():
        candidate = d / desc["blank"]
        if candidate.exists():
            return candidate
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
        "technology: overlay",
        "chrome_fields: []   # non-button chrome widgets to strip before the bake",
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


ALIGNMENTS = ("left", "center", "right")
VALIGNMENTS = ("top", "middle", "bottom")
TEXT_INSET = 2.0  # horizontal breathing room from a box edge, in points


def text_origins(lines: list[str], rect: list[float], size: float, font: str,
                 align: Optional[str] = None, valign: Optional[str] = None,
                 ) -> list[tuple[float, float]]:
    """Baseline origin (x, y) for each line of text drawn into ``rect``.

    A single line is centered in its box, horizontally and vertically,
    unless the descriptor says otherwise: a value on a signature or
    caption line reads as belonging to the line when it sits mid-way
    along it and on it, not flush left and floating above. A block of
    several lines (an address block, a wrapped answer) anchors at the
    top left, the way a typed block reads. ``align`` (left, center,
    right) and ``valign`` (top, middle, bottom) pin exceptions per
    field — a wide box that follows an inline label wants left.
    """
    x0, x1 = min(rect[0], rect[2]), max(rect[0], rect[2])
    y0, y1 = min(rect[1], rect[3]), max(rect[1], rect[3])
    multi = len(lines) > 1
    align = (align or ("left" if multi else "center")).lower()
    valign = (valign or ("top" if multi else "middle")).lower()
    if align not in ALIGNMENTS:
        raise ValueError(f"align must be one of {ALIGNMENTS}, not {align!r}")
    if valign not in VALIGNMENTS:
        raise ValueError(f"valign must be one of {VALIGNMENTS}, not {valign!r}")

    # Baselines step down by one leading per line; ``first`` is the
    # first line's baseline. Cap height is taken as 0.72 em, so a line
    # is visually centered when its baseline sits 0.36 em below the
    # midline — the same convention a viewer uses for a widget's text.
    spread = (len(lines) - 1) * size * LEADING_RATIO
    if valign == "top":
        first = y1 - size
    elif valign == "bottom":
        first = y0 + TEXT_INSET + spread
    else:
        first = (y0 + y1) / 2.0 - size * 0.36 + spread / 2.0

    origins = []
    for j, line in enumerate(lines):
        w = stringWidth(line, font, size)
        if align == "left":
            x = x0 + TEXT_INSET
        elif align == "right":
            x = x1 - TEXT_INSET - w
        else:
            x = (x0 + x1) / 2.0 - w / 2.0
        origins.append((x, first - j * size * LEADING_RATIO))
    return origins


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
            # We draw the lines ourselves (first baseline one size below
            # the top, then LEADING_RATIO per line), so the extent is
            # exactly what the renderer will use; no viewer is involved.
            fits_h = size * (1 + (len(lines) - 1) * LEADING_RATIO) <= height
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

    # The `forms:` block is read by name lookup above, never consumed, so a
    # key that matches nothing in the descriptor was silently ignored --- it
    # filled no field and checked no box, and the build said nothing. Two
    # such typos rode into a signed filing before a human noticed a blank
    # box on the rendered page. A misspelled key is indistinguishable from
    # an unset one in the output, so it has to be caught here.
    known = set(desc.get("fields") or {}) | set(desc.get("checkboxes") or {})
    for leftover in form_block:
        if leftover not in known:
            problems.append(
                f"unknown key '{leftover}' in forms.{desc['form']} block "
                f"(not in {desc['form']} descriptor) --- it was IGNORED"
            )
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


PUSHBUTTON_FLAG = 1 << 16  # PDF 32000-1 12.7.4.2.1: /Ff bit 17
MULTILINE_FLAG = 1 << 12   # PDF 32000-1 12.7.4.3: /Ff bit 13


# Chrome pushbuttons by name: the Judicial Council names its
# viewer-convenience buttons Print/Save/Reset (and the Warning privacy
# banner) across the corpus (MC-040, SUBP-010, ...). Everything
# else with the pushbutton flag is page FURNITURE dressed as a button:
# one request-for-order form draws its blue "Attachment 9." and sibling-form
# cross-reference labels as pushbutton widgets, and stripping those
# leaves sentences pointing at blank gaps ("as attached on form ____").
_CHROME_BUTTON_NAME = re.compile(
    r"^(print|save|reset|clear|submit|warning)\d*(\[\d+\])?$", re.I)
# Appearance fallback for oddly named chrome: the button's own /AP
# draws the tell-tale text.
_CHROME_BUTTON_AP = re.compile(
    rb"(Print|Save|Clear|Reset)\s*this\s*form|protection\s*and\s*privacy",
    re.I)


def _is_chrome_pushbutton(obj) -> bool:
    name = str(_inherited(obj, "/T") or "")
    if _CHROME_BUTTON_NAME.match(name):
        return True
    try:
        ap = obj["/AP"]["/N"]
        data = ap.get_object().get_data()
        if _CHROME_BUTTON_AP.search(data):
            return True
    except Exception:
        pass
    return False


def _strip_pushbutton_widgets(writer: PdfWriter) -> None:
    """Remove CHROME pushbutton widgets (Print/Save/Clear/Warning) from
    all pages; keep every other pushbutton so the bake inks it into the
    page.

    Judicial Council blanks ship with viewer-convenience buttons whose
    /AP streams the overlay bake would otherwise ink permanently into a
    filing ("Print this form" / "Save this form" / "Clear this form"
    and the privacy banner) --- those are stripped, identified by the
    corpus-wide Print/Save/Reset/Warning naming with an appearance-text
    fallback. But NOT every pushbutton is chrome: one request-for-order form implements
    its blue "Attachment 9." and sibling-form cross-reference labels
    as pushbutton widgets, and an earlier strip-everything rule deleted
    them, leaving sentences that point at blank gaps. Label buttons are
    kept so the bake converts their appearance into ordinary page
    content (the interactivity dies in the bake either way).
    ``chrome_fields`` remains for non-button chrome.
    """
    doomed_names: set[str] = set()
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        kept = ArrayObject()
        for annot in page["/Annots"]:
            obj = annot.get_object()
            ft = _inherited(obj, "/FT")
            ff = _inherited(obj, "/Ff")
            if (str(ft) == "/Btn" and int(ff or 0) & PUSHBUTTON_FLAG
                    and _is_chrome_pushbutton(obj)):
                name = str(obj.get("/T") or "")
                if name:
                    doomed_names.add(name)
                continue
            kept.append(annot)
        page[NameObject("/Annots")] = kept
    if doomed_names:
        catalog = writer._root_object  # type: ignore[attr-defined]
        if "/AcroForm" in catalog:
            af = catalog["/AcroForm"].get_object()
            if "/Fields" in af:
                kept_fields = ArrayObject()
                for f in af["/Fields"]:
                    obj = f.get_object()
                    if str(obj.get("/T") or "") in doomed_names:
                        continue
                    kept_fields.append(f)
                af[NameObject("/Fields")] = kept_fields


def _bake_widgets(writer: PdfWriter) -> PdfWriter:
    """BAKE widget appearance streams into page content, then return a
    writer over the result. Must run before any widget is dropped.

    Judicial Council blanks carry ReadOnly widgets that draw *static
    label text* — an item's "Attachment 7." marker, and the blue form
    numbers printed inside a sentence that cross-references another
    form. Those are annotations, not page content, so deleting widgets
    deletes the labels. One request-for-order page alone has 62 widgets
    of which 4 are ReadOnly
    labels; an early version of overlay support dropped them and produced
    a form reading "Attachment ___" with an empty blue gap where the form
    number belongs. Baking first turns every appearance into ordinary
    content, so the labels survive and nothing interactive is left.
    """
    import io
    import fitz  # pymupdf, already a hard dependency
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    doc = fitz.open(stream=buf.read(), filetype="pdf")
    doc.bake()          # widgets + annotations -> page content
    baked = io.BytesIO(doc.tobytes())
    doc.close()
    baked.seek(0)
    return PdfWriter(clone_from=PdfReader(baked))


def _strip_all_form_machinery(writer: PdfWriter) -> None:
    """Belt and braces after :func:`_bake_widgets`: drop any widget
    annotation and the AcroForm dictionary that survived the bake.
    Nothing interactive remains, so every viewer renders the same page
    content — the whole point of ``technology: overlay``."""
    for page in writer.pages:
        if "/Annots" in page:
            kept = ArrayObject()
            for annot in page["/Annots"]:
                if annot.get_object().get("/Subtype") == "/Widget":
                    continue
                kept.append(annot)
            page[NameObject("/Annots")] = kept
    catalog = writer._root_object  # type: ignore[attr-defined]
    if "/AcroForm" in catalog:
        del catalog[NameObject("/AcroForm")]


def fill(form_id: str, output_path: Path, meta: Optional[dict] = None,
         data: Optional[dict] = None, strict: bool = False) -> FillResult:
    """Fill a form per its descriptor. See module docstring."""
    desc = load_descriptor(form_id)
    blank = blank_path(desc)
    if not blank.exists():
        raise FileNotFoundError(f"Blank form missing: {blank}")

    # Box-level front-matter defaults reach direct fills too; a meta
    # that came through md_pleading already carries them (idempotent).
    meta = {**jc_common.front_matter_defaults(), **(meta or {})}
    texts, checks, explicit_checks, problems = resolve_values(desc, meta, data)
    result = FillResult(output_path=output_path, warnings=problems)
    if problems and strict:
        raise ValueError(f"{form_id}: " + "; ".join(problems))

    reader = PdfReader(str(blank))
    writer = PdfWriter(clone_from=reader)

    # Index the blank's widgets by qualified name (and bare leaf name as
    # a fallback), keeping only what a fill borrows from them: the
    # rectangle and the multiline flag. The widgets themselves are never
    # written to; they are baked and removed below.
    widget_geom: dict[str, tuple[int, list[float], bool]] = {}
    for page_idx, name, obj in iter_widgets(reader):
        rect = [float(v) for v in (obj.get("/Rect") or [0, 0, 0, 0])]
        multiline = bool(int(_inherited(obj, "/Ff", 0) or 0) & MULTILINE_FLAG)
        widget_geom.setdefault(name, (page_idx, rect, multiline))
        widget_geom.setdefault(name.split(".")[-1], (page_idx, rect, multiline))

    overlay_ops: dict[int, list[dict]] = {}
    pending_overlay: list[dict] = []

    fields = desc.get("fields") or {}
    for name, spec in fields.items():
        value = texts.get(name, "")
        if not value:
            continue
        rect = spec.get("rect")
        page_no = int(spec.get("page", 1)) - 1
        if not rect and spec.get("map"):
            hit = widget_geom.get(spec["map"])
            if hit is not None:
                page_no, rect, multiline = hit
                if "multiline" not in spec:
                    # A multiline widget is a box meant to hold lines;
                    # fit_text wraps into it rather than shrinking a
                    # long value to the minimum size on one line.
                    spec = {**spec, "multiline": multiline}
        if not rect:
            result.warnings.append(
                f"{name}: overlay field needs a rect, or a map naming a "
                f"widget in {blank.name} — form revision drift?")
            continue
        # Fitting is the point — a field with no explicit fit strategy
        # shrinks rather than warns.
        if not spec.get("fit"):
            spec = {**spec, "fit": "shrink"}
        pending_overlay.append({
            "name": name, "value": value, "rect": rect,
            "page": page_no, "spec": spec,
        })

    # Fit the pending overlay text, then enforce size-group consistency:
    # every member of a ``size_group`` renders at the smallest size any
    # member needed, so a block of related boxes doesn't end up at three
    # different sizes (the consistency/fit compromise of ADR-0033).
    for op in pending_overlay:
        fitted = fit_text(op["value"], op["rect"], op["spec"])
        if not fitted.fits:
            op["value"], fitted = _handle_overflow(
                op["name"], op["spec"], op["value"], op["rect"], result)
        op["fit"] = fitted
    group_min: dict[str, float] = {}
    for op in pending_overlay:
        g = op["spec"].get("size_group")
        if g:
            group_min[g] = min(group_min.get(g, 1e9), op["fit"].font_size)
    for op in pending_overlay:
        g = op["spec"].get("size_group")
        if g and op["fit"].font_size > group_min[g]:
            locked = {**op["spec"], "font_size": group_min[g],
                      "min_font_size": group_min[g]}
            op["fit"] = fit_text(op["value"], op["rect"], locked)
    for op in pending_overlay:
        overlay_ops.setdefault(op["page"], []).append(
            {"rect": op["rect"], "fit": op["fit"], "spec": op["spec"]})

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
        # Like text fields, a checkbox may carry a hand-authored
        # ``rect:`` — required when two widgets share one qualified name
        # (e.g. a radio pair), since a name lookup can only ever reach
        # the first.
        rect = spec.get("rect")
        page_idx = int(spec.get("page", 1)) - 1
        if not rect and spec.get("map"):
            hit = widget_geom.get(spec["map"])
            if hit is not None:
                page_idx, rect, _multiline = hit
        if not rect:
            result.warnings.append(
                f"checkbox {name}: needs a rect, or a map naming a "
                f"widget in {blank.name} — form revision drift?")
            continue
        overlay_ops.setdefault(page_idx, []).append({"rect": rect, "mark": True})

    # Chrome widgets must go BEFORE the bake: LiveCycle-era buttons
    # carry no /AP stream and bake to nothing, but AEM-era blanks
    # (2020+) give Print/Save/Clear buttons and privacy banners real
    # appearance streams, which the bake would ink permanently into
    # the filing.
    _strip_named_widgets(writer, set(desc.get("chrome_fields") or []))
    _strip_pushbutton_widgets(writer)
    writer = _bake_widgets(writer)
    _strip_all_form_machinery(writer)

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
                rect = op["rect"]
                if op.get("mark"):
                    # Checkbox: a bold X visually centered in the box.
                    w = abs(rect[2] - rect[0])
                    h = abs(rect[3] - rect[1])
                    size = max(6.0, min(w, h) * 0.85)
                    c.setFont("Helvetica-Bold", size)
                    cx = (rect[0] + rect[2]) / 2.0
                    cy = (rect[1] + rect[3]) / 2.0
                    c.drawCentredString(cx, cy - size * 0.36, "X")
                    continue
                fitted, spec = op["fit"], op["spec"]
                font = str(spec.get("font") or DEFAULT_FONT)
                c.setFont(font, fitted.font_size)
                color = spec.get("color")
                c.setFillColorRGB(*color) if color else c.setFillColorRGB(0, 0, 0)
                for line, (x, y) in zip(
                        fitted.lines,
                        text_origins(fitted.lines, rect, fitted.font_size, font,
                                     spec.get("align"), spec.get("valign"))):
                    c.drawString(x, y, line)
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
# E-sign field geometry (for the build's <pdf>.fields.json sidecar)
# ---------------------------------------------------------------------------

def esign_fields(form_id: str, meta: Optional[dict] = None) -> list[dict]:
    """Every ``esign:`` field on a form, as sidecar records the build can
    merge into ``<pdf>.fields.json`` and ``sc docuseal`` can place.

    Same rect resolution as a fill (explicit ``rect`` or ``map`` naming a
    widget), converted to the sidecar's top-left-origin points. The role
    is ``Signer <n>`` numbered by the field's party position in
    ``esign_parties`` -- the same "Signer N" vocabulary the pleading
    signblocks emit and the roster (``--to`` order) is read in, so a
    form's signature fields attach to the right submitter with no
    per-form wiring. A field whose party is not declared falls to
    ``Signer 1``. Page-relative coordinates: the caller offsets pages
    when the form is prepended as a cover sheet.
    """
    from reportlab.lib.pagesizes import letter as _letter
    page_h = _letter[1]
    desc = load_descriptor(form_id)
    blank = blank_path(desc)
    if not blank.exists():
        raise FileNotFoundError(f"Blank form missing: {blank}")
    reader = PdfReader(str(blank))
    widget_rects: dict[str, tuple[int, list[float]]] = {}
    for page_idx, name, obj in iter_widgets(reader):
        rect = [float(v) for v in (obj.get("/Rect") or [0, 0, 0, 0])]
        widget_rects.setdefault(name, (page_idx, rect))
        widget_rects.setdefault(name.split(".")[-1], (page_idx, rect))

    parties = [str(p) for p in (desc.get("esign_parties") or [])]
    out: list[dict] = []
    for name, spec in (desc.get("fields") or {}).items():
        es = spec.get("esign") or {}
        if not es:
            continue
        rect = spec.get("rect")
        page_no = int(spec.get("page", 1)) - 1
        if not rect and spec.get("map"):
            hit = widget_rects.get(spec["map"])
            if hit is not None:
                page_no, rect = hit
        if not rect:
            continue
        x0, y0, x1, y1 = rect
        x, w = min(x0, x1), abs(x1 - x0)
        top, h = max(y0, y1), abs(y1 - y0)
        party = str(es.get("party") or "")
        role_n = parties.index(party) + 1 if party in parties else 1
        out.append({
            "name": f"{name}",
            "role": f"Signer {role_n}",
            "type": str(es.get("type") or "text"),
            "page": page_no + 1,
            "x": round(x, 2),
            "y_top": round(page_h - top, 2),
            "w": round(w, 2),
            "h": round(h, 2),
        })
    return out


# ---------------------------------------------------------------------------
# Geometry preview
# ---------------------------------------------------------------------------

def geometry_preview(form_id: str, output_path: Path) -> FillResult:
    """Render the blank with a translucent box over every place the
    descriptor can put ink — the visual sanity check that a form
    adapter's geometry is right, made BEFORE trusting a fill.

    Text fields draw in blue, checkboxes in purple, each labeled with
    its logical name. Fields carrying an ``esign:`` tag draw in their
    party's color (position in ``esign_parties`` → PARTY_COLORS) with
    the e-sign TYPE as the label, so name/date/signature areas reserved
    for each signer are distinguishable at a glance. A legend at the
    foot of page 1 keys the colors. The output is a review artifact,
    never a filing.
    """
    desc = load_descriptor(form_id)
    blank = blank_path(desc)
    if not blank.exists():
        raise FileNotFoundError(f"Blank form missing: {blank}")
    reader = PdfReader(str(blank))
    writer = PdfWriter(clone_from=reader)
    result = FillResult(output_path=output_path)

    widget_rects: dict[str, tuple[int, list[float]]] = {}
    for page_idx, name, obj in iter_widgets(reader):
        rect = [float(v) for v in (obj.get("/Rect") or [0, 0, 0, 0])]
        widget_rects.setdefault(name, (page_idx, rect))
        widget_rects.setdefault(name.split(".")[-1], (page_idx, rect))

    parties = [str(p) for p in (desc.get("esign_parties") or [])]

    boxes: dict[int, list[dict]] = {}

    def add(name: str, spec: dict, is_checkbox: bool) -> None:
        rect = spec.get("rect")
        page_no = int(spec.get("page", 1)) - 1
        if not rect and spec.get("map"):
            hit = widget_rects.get(spec["map"])
            if hit is not None:
                page_no, rect = hit
        if not rect:
            result.warnings.append(f"{name}: no rect and no matching widget; not drawn")
            return
        es = spec.get("esign") or {}
        color = CHECKBOX_COLOR if is_checkbox else FIELD_BOX_COLOR
        # A descriptor key like `yes:` or `no:` parses as a YAML bool;
        # fill() coerces it, so the preview must too.
        label = str(name)
        if es:
            etype = str(es.get("type") or "text")
            if etype not in ESIGN_TYPES:
                result.warnings.append(
                    f"{name}: esign type '{etype}' outside taxonomy "
                    f"{sorted(ESIGN_TYPES)}")
            party = str(es.get("party") or "")
            if party and party not in parties:
                result.warnings.append(
                    f"{name}: esign party '{party}' not declared in "
                    f"esign_parties {parties}")
            if party in parties:
                color = PARTY_COLORS[parties.index(party) % len(PARTY_COLORS)]
            else:
                color = (0.4, 0.4, 0.4)
            label = etype.upper() + (f" · {party}" if party else "")
        boxes.setdefault(page_no, []).append(
            {"rect": rect, "color": color, "label": label, "esign": bool(es)})

    for name, spec in (desc.get("fields") or {}).items():
        add(name, spec, False)
    for name, spec in (desc.get("checkboxes") or {}).items():
        add(name, spec, True)

    import io
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=letter)
    for i in range(len(reader.pages)):
        for b in boxes.get(i, []):
            r, col = b["rect"], b["color"]
            x, y = min(r[0], r[2]), min(r[1], r[3])
            w, h = abs(r[2] - r[0]), abs(r[3] - r[1])
            c.saveState()
            c.setFillColorRGB(*col)
            c.setStrokeColorRGB(*col)
            c.setFillAlpha(0.18)
            c.setStrokeAlpha(0.9)
            c.setLineWidth(1.2 if b["esign"] else 0.5)
            c.rect(x, y, w, h, fill=1, stroke=1)
            c.setFillAlpha(1.0)
            c.setFont("Helvetica", 4.5)
            c.drawString(x + 1, y + h + 0.8, b["label"][:70])
            c.restoreState()
        if i == 0:
            c.saveState()
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(36, 18, f"GEOMETRY PREVIEW — {desc['form']} — "
                                 "review artifact, not a filing")
            c.setFont("Helvetica", 7)
            x0 = 36
            entries = [("text field", FIELD_BOX_COLOR),
                       ("checkbox", CHECKBOX_COLOR)]
            entries += [(f"e-sign: {p}", PARTY_COLORS[j % len(PARTY_COLORS)])
                        for j, p in enumerate(parties)]
            for lbl, col in entries:
                c.setFillColorRGB(*col)
                c.rect(x0, 8, 8, 6, fill=1, stroke=0)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(x0 + 10, 8, lbl)
                x0 += 12 + stringWidth(lbl, "Helvetica", 7) + 10
            c.restoreState()
        c.showPage()
    c.save()
    buf.seek(0)
    over = PdfReader(buf)
    for i, page in enumerate(writer.pages):
        if i < len(over.pages):
            page.merge_page(over.pages[i])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as fh:
        writer.write(fh)
    return result


# ---------------------------------------------------------------------------
# Cover-sheet cache + prepend (generic versions of the per-form helpers)
# ---------------------------------------------------------------------------

def find_case_dir(input_md: Path) -> Path:
    for ancestor in input_md.parents:
        if ancestor.name == "src":
            return ancestor.parent
    return input_md.parent.parent


def _src_relative_dir(input_md: Path) -> Optional[Path]:
    """``input_md``'s directory, relative to its ancestor named ``src``.

    Returns ``Path(".")`` for a source sitting directly in ``src/``,
    and ``None`` when ``input_md`` has no ``src`` ancestor at all (a
    source outside the case's ``src/`` tree, e.g. a scratch file).
    """
    for ancestor in input_md.parents:
        if ancestor.name == "src":
            return input_md.parent.relative_to(ancestor)
    return None


def cover_sheet_cache_path(form_id: str, input_md: Path) -> Path:
    """Where ``ensure_cached`` reads/writes the filled cover sheet for
    ``input_md``.

    Keyed by the source's path relative to ``src/``, mirrored under
    ``assets/decl_cover_sheets/``, so two sources with the same bare
    filename in different subfolders of ``src/`` (e.g.
    ``src/packet_a/proposed_order.md`` and
    ``src/packet_b/proposed_order.md``) get distinct cache files
    instead of silently overwriting one another. A source directly in
    ``src/`` caches at the top of ``decl_cover_sheets/``; a source with
    no ``src`` ancestor falls back to the bare stem, as before.
    """
    case_dir = find_case_dir(input_md)
    base = case_dir / "assets" / "decl_cover_sheets"
    rel_dir = _src_relative_dir(input_md)
    cache_dir = base if rel_dir is None or rel_dir == Path(".") else base / rel_dir
    return cache_dir / f"{input_md.stem}.{form_id}.pdf"


def ensure_cached(form_id: str, meta: dict, input_md: Path) -> Path:
    """Return a cached filled form for a pleading source, refreshing if stale."""
    desc = load_descriptor(form_id)
    cache = cover_sheet_cache_path(form_id, input_md)
    blank = blank_path(desc)
    descriptor_file = _registry_path(form_id) or (REGISTRY_DIR / f"{form_id}.yaml")
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

# ---------------------------------------------------------------------------
# Descriptor check: does every registered form still fill under this engine?
# ---------------------------------------------------------------------------

@dataclass
class CheckRow:
    form_id: str
    layer: str
    technology: str
    pages: int = 0
    warnings_empty: int = 0
    warnings_full: int = 0
    error: str = ""
    notes: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def _layer_of(path: Optional[Path]) -> str:
    if path is None:
        return "?"
    try:
        rel = path.resolve().relative_to(LAYERS_ROOT)
    except ValueError:
        return "built-in"
    parts = rel.parts
    if parts[:1] == ("local",):
        return "local"
    if parts[:1] == ("modules",) and len(parts) > 1:
        return f"modules/{parts[1]}"
    return "built-in"


def _sample_data(desc: dict) -> dict:
    """One value per logical field and every checkbox set: the fill that
    exercises every rect a descriptor names."""
    data: dict = {}
    for name, spec in (desc.get("fields") or {}).items():
        data[name] = str(spec.get("example") or spec.get("default") or f"{name} sample")
    for name in (desc.get("checkboxes") or {}):
        data[name] = True
    return data


def check_forms(form_ids: Optional[list[str]] = None,
                keep_dir: Optional[Path] = None) -> list[CheckRow]:
    """Fill every registered descriptor twice (auto bindings only, then
    every field populated), render its geometry preview, and report one
    row per form. An exception is a failure; descriptor warnings are
    counted, not fatal. This is the merge gate that keeps a deployment's
    module descriptors working across engine changes.
    """
    ids = form_ids or list_forms()
    out_dir = keep_dir or Path(tempfile.mkdtemp(prefix="form-check-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[CheckRow] = []
    for fid in ids:
        path = _registry_path(fid)
        row = CheckRow(form_id=fid, layer=_layer_of(path), technology="?")
        try:
            desc = load_descriptor(fid)
            row.technology = str(desc.get("technology") or "?")
            odd = [k for sect in ("fields", "checkboxes")
                   for k in (desc.get(sect) or {}) if not isinstance(k, str)]
            if odd:
                row.notes = (f"{len(odd)} non-string key(s) {odd} --- quote them in "
                             "the descriptor (YAML reads yes/no/on/off as booleans)")
            empty = fill(fid, out_dir / f"{fid}.empty.pdf", meta={}, data={})
            row.warnings_empty = len(empty.warnings)
            full = fill(fid, out_dir / f"{fid}.full.pdf", meta={}, data=_sample_data(desc))
            row.warnings_full = len(full.warnings)
            geometry_preview(fid, out_dir / f"{fid}.preview.pdf")
            row.pages = len(PdfReader(str(full.output_path)).pages)
        except Exception as exc:  # every failure is a row, never an abort
            row.error = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    return rows


def format_check(rows: list[CheckRow]) -> str:
    head = f"{'form':<10} {'layer':<28} {'tech':<9} {'pages':>5} {'warn':>9}  status"
    lines = [head, "-" * len(head)]
    for r in rows:
        warn = f"{r.warnings_empty}/{r.warnings_full}"
        status = "ok" if r.ok else f"FAIL {r.error}"
        if r.ok and r.notes:
            status += f" ({r.notes})"
        lines.append(f"{r.form_id:<10} {r.layer:<28} {r.technology:<9} "
                     f"{r.pages:>5} {warn:>9}  {status}")
    bad = [r for r in rows if not r.ok]
    lines.append(f"{len(rows)} forms, {len(rows) - len(bad)} ok, {len(bad)} failed"
                 f" (warn = empty-fill/full-fill descriptor warnings; layers from {LAYERS_ROOT})")
    return "\n".join(lines)


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

    sp = sub.add_parser(
        "preview",
        help="render the blank with colored boxes over every fillable/"
             "e-sign area — visual geometry check for a descriptor")
    sp.add_argument("form_id")
    sp.add_argument("-o", "--output", required=True)

    sub.add_parser("list", help="list registered forms")

    sp = sub.add_parser(
        "check",
        help="fill every registered form (autos only, then every field), "
             "render its geometry preview, and report; exit 1 on any failure. "
             "PROSAIC_LAYERS_ROOT=<checkout> checks that checkout's local/ "
             "and modules/ descriptors under this engine")
    sp.add_argument("form_ids", nargs="*", help="default: every registered form")
    sp.add_argument("--keep", metavar="DIR", help="keep the rendered PDFs here")
    sp.add_argument("--strict", action="store_true",
                    help="also fail on descriptor warnings")

    args = p.parse_args()
    if args.cmd == "check":
        rows = check_forms(args.form_ids or None, Path(args.keep) if args.keep else None)
        print(format_check(rows))
        failed = [r for r in rows if not r.ok]
        if args.strict:
            failed += [r for r in rows if r.ok and (r.warnings_empty or r.warnings_full)]
        return 1 if failed else 0
    if args.cmd == "list":
        for f in list_forms():
            d = load_descriptor(f)
            print(f"{f:<10} {d.get('title', '')}  [{d.get('domain', '')} rev {d.get('revision', '?')}]")
        return 0
    if args.cmd == "fields":
        print(skeleton_yaml(Path(args.pdf)))
        return 0
    if args.cmd == "preview":
        res = geometry_preview(args.form_id, Path(args.output))
        for w in res.warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(f"wrote {res.output_path}")
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
