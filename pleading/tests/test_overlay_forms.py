"""Tests for ``technology: overlay`` form filling (ADR-0033) and the
geometry preview.

MC-040 is the pilot descriptor. The properties that matter: the output
is fully flattened (no AcroForm, no widget annotations), every drawn
value lands inside its widget's rectangle, checkbox marks land inside
their boxes, ``size_group`` members render at one consistent size, and
the geometry preview draws a box for everything (including hand-rect
e-sign areas) without warnings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))

import form_fill  # noqa: E402

from pypdf import PdfReader  # noqa: E402

META = {
    "filer_phone": "(555) 555-0100",
    "filer_email": "jane.roe@example.com",
    "filer_role": "Respondent, In Pro Per",
    "court_county": "COUNTY OF EXAMPLE",
    "court_street_address": "100 Court Street",
    "court_city_zip": "Example City, CA 90000",
    "court_branch": "Civil Division",
    "petitioner": "JOHN SMITH",
    "respondent": "JANE ROE",
    "case_number": "24CV00000",
    "judge": "Hon. A. Judge",
    "hearing_dept": "20",
}

DATA = {
    "atty_party_block": "Jane Roe\nPO Box 999\nExample City, CA 90000",
    "self_represented": True,
    "role_respondent": True,
    "mc040_respondent_name": "Jane Roe",
    "mc040_effective_date": "August 21, 2026",
    "mc040_for_name": "Jane Roe",
    "mc040_new_street": "PO Box 999",
    "mc040_new_city": "Example City",
    "mc040_new_state_zip": "CA 90000",
    "print_name": "Jane Roe",
}


def _runs(page):
    """(text, x, y, size) for every text-showing run on a page."""
    out = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            out.append((text.strip(), tm[4], tm[5], font_size))

    page.extract_text(visitor_text=visit)
    return out


def _widget_rects(form_id):
    desc = form_fill.load_descriptor(form_id)
    blank = form_fill.blank_path(desc)
    rects = {}
    for page_idx, name, obj in form_fill.iter_widgets(PdfReader(str(blank))):
        rects[name] = (page_idx, [float(v) for v in obj["/Rect"]])
    return desc, rects


def _fill(tmp_path, extra=None):
    out = tmp_path / "mc040.pdf"
    data = dict(DATA)
    if extra:
        data.update(extra)
    res = form_fill.fill("mc040", out, meta=dict(META), data=data)
    return out, res


def test_overlay_output_is_flattened(tmp_path):
    out, res = _fill(tmp_path)
    reader = PdfReader(str(out))
    assert not (reader.get_fields() or {})
    root = reader.trailer["/Root"]
    assert "/AcroForm" not in root
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            assert annot.get_object().get("/Subtype") != "/Widget"


def test_values_land_inside_their_widget_rects(tmp_path):
    out, _ = _fill(tmp_path)
    desc, rects = _widget_rects("mc040")
    reader = PdfReader(str(out))

    checks = {
        "case_number": "24CV00000",
        "mc040_effective_date": "August 21, 2026",
        "mc040_new_street": "PO Box 999",
    }
    for field, value in checks.items():
        spec = desc["fields"][field]
        page_idx, rect = rects[spec["map"]]
        x0, x1 = min(rect[0], rect[2]), max(rect[0], rect[2])
        y0, y1 = min(rect[1], rect[3]), max(rect[1], rect[3])
        hits = [(t, x, y) for (t, x, y, _s) in _runs(reader.pages[page_idx])
                if value in t]
        assert hits, f"{field}: '{value}' not drawn on page {page_idx + 1}"
        assert any(x0 - 1 <= x <= x1 and y0 - 1 <= y <= y1 + 1
                   for (_t, x, y) in hits), (
            f"{field}: '{value}' drawn outside its rect {rect}: {hits}")


def test_checkbox_mark_lands_inside_its_box(tmp_path):
    out, _ = _fill(tmp_path)
    desc, rects = _widget_rects("mc040")
    spec = desc["checkboxes"]["role_respondent"]
    page_idx, rect = rects[spec["map"]]
    x0, x1 = min(rect[0], rect[2]), max(rect[0], rect[2])
    y0, y1 = min(rect[1], rect[3]), max(rect[1], rect[3])
    reader = PdfReader(str(out))
    xs = [(x, y) for (t, x, y, _s) in _runs(reader.pages[page_idx]) if t == "X"]
    assert any(x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1
               for (x, y) in xs), (
        f"no X mark inside role_respondent box {rect}; X's at {xs}")


def test_size_group_members_share_a_size(tmp_path):
    # A deliberately long street forces a shrink; the (short) city line
    # must come down to the same size rather than render larger.
    long_street = ("12345 Extremely Long Boulevard of Excessive Length, "
                   "Suite 999, Building C, Care of the Registered Agent for "
                   "Service of Process, Example City, California 90000-0000")
    out, _ = _fill(tmp_path, extra={"mc040_new_street": long_street})
    reader = PdfReader(str(out))
    runs = _runs(reader.pages[0])
    street = [s for (t, _x, _y, s) in runs if "Extremely Long" in t]
    city = [s for (t, _x, _y, s) in runs if t == "Example City"]
    assert street and city, f"missing runs: street={street} city={city}"
    assert street[0] < form_fill.DEFAULT_FONT_SIZE  # it actually shrank
    assert abs(street[0] - city[0]) < 0.01, (
        f"size_group violated: street={street[0]} city={city[0]}")


def test_geometry_preview_draws_clean(tmp_path):
    out = tmp_path / "preview.pdf"
    res = form_fill.geometry_preview("mc040", out)
    assert out.exists() and out.stat().st_size > 1000
    assert not res.warnings, res.warnings
    reader = PdfReader(str(out))
    text = "".join(p.extract_text() for p in reader.pages)
    # e-sign areas are labeled by TYPE and party, per the taxonomy
    assert "SIGNATURE · filer" in text
    assert "SIGNATURE · server" in text
    assert "DATE · filer" in text
    assert "GEOMETRY PREVIEW" in text


def test_esign_taxonomy_and_parties_are_validated(tmp_path):
    desc = form_fill.load_descriptor("mc040")
    for name, spec in (desc.get("fields") or {}).items():
        es = spec.get("esign")
        if not es:
            continue
        assert es["type"] in form_fill.ESIGN_TYPES, (name, es)
        assert es["party"] in desc["esign_parties"], (name, es)

def test_module_repo_forms_are_discovered(tmp_path, monkeypatch):
    """ADR-0034: a checkout under modules/<name>/ mirroring the repo
    layout contributes descriptors and blanks, at lower precedence than
    local/ and higher than the built-ins.

    Uses an overlay form as the template: since ADR-0037 a non-overlay
    descriptor outside the legacy list is refused at load, so an
    AcroForm form cannot serve as an incidental fixture."""
    import shutil

    mod = tmp_path / "modules" / "example-forms" / "pleading" / "forms"
    (mod / "registry").mkdir(parents=True)
    desc = form_fill.load_descriptor("mc040")
    src = form_fill._registry_path("mc040")
    text = src.read_text().replace("form: mc040", "form: zz998")
    (mod / "registry" / "zz998.yaml").write_text(text)
    shutil.copy(form_fill.blank_path(desc), mod / desc["blank"])

    monkeypatch.setattr(form_fill, "MODULES_DIR", tmp_path / "modules")
    assert "zz998" in form_fill.list_forms()
    loaded = form_fill.load_descriptor("zz998")
    assert form_fill.blank_path(loaded).exists()


# --- ADR-0037: AcroForm filling is prohibited ------------------------------


def test_a_new_non_overlay_descriptor_is_refused(tmp_path):
    """No new form may be authored the AcroForm way.

    The rule has to bite at load, not at review: an agent copying the
    shape of an older descriptor would otherwise reproduce a fill whose
    rendering is a property of the reader rather than of the file.
    """
    import yaml
    desc = yaml.safe_load(
        "form: zz999\nblank: zz999.pdf\ntechnology: acroform\nfields: {}\n"
    )
    with pytest.raises(ValueError, match="not permitted"):
        form_fill._require_overlay("zz999", desc, tmp_path / "zz999.yaml")


def test_a_listed_legacy_form_warns_but_still_loads(capsys, tmp_path):
    import yaml
    desc = yaml.safe_load(
        "form: mc050\nblank: mc050.pdf\ntechnology: acroform\nfields: {}\n"
    )
    form_fill._require_overlay("mc050", desc, tmp_path / "mc050.yaml")
    assert "ADR-0037" in capsys.readouterr().err


def test_overlay_passes_without_complaint(capsys, tmp_path):
    import yaml
    desc = yaml.safe_load(
        "form: zz999\nblank: zz999.pdf\ntechnology: overlay\nfields: {}\n"
    )
    form_fill._require_overlay("zz999", desc, tmp_path / "zz999.yaml")
    assert capsys.readouterr().err == ""


def test_the_legacy_list_only_shrinks():
    """A canary on the list itself.

    The list is debt, enumerated so it stays visible. This pins its
    current contents so that adding to it is a deliberate act someone has
    to justify, rather than the path of least resistance when a new form
    is awkward to overlay.
    """
    assert form_fill.LEGACY_ACROFORM_FORMS <= {
        "civ110", "efs020", "mc025", "mc030", "mc050",
        "subp001", "subp002", "subp010", "subp025",
        "fl323", "fl327", "fl330", "fl335",
    }
