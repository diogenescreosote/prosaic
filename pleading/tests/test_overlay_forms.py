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


def test_pos_service_note_renders_inside_its_rect_when_set(tmp_path):
    note = ("Service was made electronically. See attached Proof of "
            "Electronic Service (Judicial Council Form EFS-050), Cal. "
            "Rules of Court, rule 2.251.")
    out, _ = _fill(tmp_path, extra={"pos_service_note": note})
    desc = form_fill.load_descriptor("mc040")
    rect = desc["fields"]["pos_service_note"]["rect"]
    x0, x1 = min(rect[0], rect[2]), max(rect[0], rect[2])
    y0, y1 = min(rect[1], rect[3]), max(rect[1], rect[3])

    reader = PdfReader(str(out))
    runs = _runs(reader.pages[1])  # page 2
    hits = [(t, x, y) for (t, x, y, _s) in runs if "electronically" in t]
    assert hits, f"pos_service_note text not drawn on page 2: {runs}"
    assert any(x0 - 1 <= x <= x1 and y0 - 1 <= y <= y1 + 1
               for (_t, x, y) in hits), (
        f"pos_service_note drawn outside its rect {rect}: {hits}")


def test_pos_service_note_absent_by_default(tmp_path):
    out, _ = _fill(tmp_path)
    reader = PdfReader(str(out))
    text = reader.pages[1].extract_text()
    assert "electronically" not in text
    assert "EFS-050" not in text


def test_pos_service_note_renders_in_red(tmp_path):
    """The note is an added annotation, not the JC form's own printed
    text — it must render in a non-black fill color (red, per the
    registry) so it visibly reads as such."""
    out, _ = _fill(tmp_path, extra={"pos_service_note": "Service was made electronically."})
    reader = PdfReader(str(out))
    page2 = reader.pages[1]
    contents = page2.get_contents().get_data().decode("latin-1")
    assert "1 0 0 rg" in contents, (
        "expected a red (1 0 0 rg) fill-color operator on page 2 for "
        "pos_service_note; none found in the content stream")


def test_no_pushbutton_chrome_survives_the_fill(tmp_path):
    """JC blanks ship Print/Save/Clear pushbuttons; none may reach a
    filing — neither as live widgets nor baked into page content
    (MC-040's buttons carry real /AP streams that the bake would ink)."""
    out, _ = _fill(tmp_path)
    reader = PdfReader(str(out))
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            obj = annot.get_object()
            assert str(obj.get("/FT") or "") != "/Btn" or not (
                int(obj.get("/Ff") or 0) & (1 << 16)), "live pushbutton survived"
        text = page.extract_text()
        for phrase in ("Print this form", "Save this form", "Clear this form"):
            assert phrase not in text, f"baked button text survived: {phrase}"


def test_label_pushbuttons_survive_the_fill_as_page_content(tmp_path):
    """The chrome strip must not eat cross-reference labels. One Judicial
    Council form draws its blue "Attachment 9." / sibling-form labels as pushbutton
    widgets; strip-everything deleted them and left sentences pointing
    at blank gaps. A pushbutton is chrome only by Print/Save/Reset/
    Warning name or by tell-tale appearance text; anything else keeps
    its appearance through the bake."""
    from pypdf.generic import (
        DictionaryObject, NameObject, NumberObject, ArrayObject,
        TextStringObject, StreamObject,
    )
    from pypdf import PdfWriter

    src = form_fill.blank_path(form_fill.load_descriptor("mc040"))
    reader = PdfReader(str(src))
    writer = PdfWriter(clone_from=reader)
    page = writer.pages[0]

    def pushbutton(name, label):
        ap = StreamObject()
        ap[NameObject("/Type")] = NameObject("/XObject")
        ap[NameObject("/Subtype")] = NameObject("/Form")
        ap[NameObject("/BBox")] = ArrayObject(
            [NumberObject(0), NumberObject(0), NumberObject(80), NumberObject(12)])
        ap[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/Helv"): DictionaryObject({
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                })})})
        ap.set_data(f"BT /Helv 9 Tf 1 6 Td ({label}) Tj ET".encode())
        ap_ref = writer._add_object(ap)
        w = DictionaryObject()
        w[NameObject("/Type")] = NameObject("/Annot")
        w[NameObject("/Subtype")] = NameObject("/Widget")
        w[NameObject("/FT")] = NameObject("/Btn")
        w[NameObject("/Ff")] = NumberObject(1 << 16)
        w[NameObject("/T")] = TextStringObject(name)
        w[NameObject("/Rect")] = ArrayObject(
            [NumberObject(400), NumberObject(700),
             NumberObject(480), NumberObject(712)])
        w[NameObject("/AP")] = DictionaryObject({NameObject("/N"): ap_ref})
        w[NameObject("/P")] = page.indirect_reference
        wref = writer._add_object(w)
        page[NameObject("/Annots")].append(wref)

    pushbutton("att9x[0]", "Attachment 9.")
    pushbutton("Print[0]", "Print this form")

    form_fill._strip_pushbutton_widgets(writer)
    kept = [str(a.get_object().get("/T") or "")
            for a in page["/Annots"]
            if str(a.get_object().get("/FT") or "") == "/Btn"
            and int(a.get_object().get("/Ff") or 0) & (1 << 16)]
    assert "att9x[0]" in kept, "label pushbutton was stripped"
    assert "Print[0]" not in kept, "chrome pushbutton survived"


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


# --- ADR-0037 / ADR-0046: overlay is the only technology --------------------


@pytest.mark.parametrize("technology", ["acroform", "xfa", "Overlay ", "pdf"])
def test_any_other_technology_is_refused(technology, tmp_path):
    """The rule bites at load, not at review: an agent copying the shape
    of a descriptor from another era would otherwise reproduce a fill
    whose rendering is a property of the reader rather than the file."""
    import yaml
    desc = yaml.safe_load(
        f"form: zz999\nblank: zz999.pdf\ntechnology: {technology}\nfields: {{}}\n"
    )
    if technology.strip().lower() == "overlay":
        form_fill._require_overlay("zz999", desc, tmp_path / "zz999.yaml")
        return
    with pytest.raises(ValueError, match="ADR-0046"):
        form_fill._require_overlay("zz999", desc, tmp_path / "zz999.yaml")


def test_a_descriptor_without_a_technology_key_is_refused(tmp_path):
    """No default: a descriptor states how it fills, or it does not load."""
    import yaml
    desc = yaml.safe_load("form: zz999\nblank: zz999.pdf\nfields: {}\n")
    with pytest.raises(ValueError, match="no technology key"):
        form_fill._require_overlay("zz999", desc, tmp_path / "zz999.yaml")


def test_every_registered_descriptor_declares_overlay():
    """There is no legacy list any more (ADR-0046); the registry itself
    is the proof."""
    for form_id in form_fill.list_forms():
        assert form_fill.load_descriptor(form_id).get("technology") == "overlay", form_id


def test_no_form_layer_code_survives():
    """The form-layer path was deleted, not disabled: nothing in the
    engine writes a field value, strips XFA, or sets NeedAppearances."""
    import inspect
    src = inspect.getsource(form_fill)
    for token in ("LEGACY_ACROFORM_FORMS", "update_page_form_field_values",
                  "NeedAppearances", "_strip_xfa", "_apply_font_size"):
        assert token not in src, token


# --- ADR-0046: text is centered in its box -----------------------------------


def _origin(lines, rect, size=9.0, **kw):
    return form_fill.text_origins(lines, rect, size, form_fill.DEFAULT_FONT, **kw)


def test_single_line_centers_in_its_box_by_default():
    from reportlab.pdfbase.pdfmetrics import stringWidth
    rect = [100.0, 500.0, 300.0, 520.0]
    [(x, y)] = _origin(["24CV000123"], rect)
    w = stringWidth("24CV000123", form_fill.DEFAULT_FONT, 9.0)
    assert x == pytest.approx(200.0 - w / 2.0)
    assert y == pytest.approx(510.0 - 9.0 * 0.36)


def test_a_block_anchors_top_left_by_default():
    rect = [100.0, 500.0, 300.0, 560.0]
    origins = _origin(["Jane Roe", "100 Main St, PMB 42", "Springfield, CA 90000"], rect)
    xs = [x for x, _y in origins]
    ys = [y for _x, y in origins]
    assert xs == [pytest.approx(100.0 + form_fill.TEXT_INSET)] * 3
    assert ys[0] == pytest.approx(560.0 - 9.0)
    assert ys[1] - ys[2] == pytest.approx(9.0 * form_fill.LEADING_RATIO)
    assert ys[2] > 500.0, "the last line stays inside the box"


def test_align_and_valign_overrides():
    from reportlab.pdfbase.pdfmetrics import stringWidth
    rect = [100.0, 500.0, 300.0, 520.0]
    w = stringWidth("x", form_fill.DEFAULT_FONT, 9.0)
    [(xl, yt)] = _origin(["x"], rect, align="left", valign="top")
    [(xr, yb)] = _origin(["x"], rect, align="right", valign="bottom")
    assert xl == pytest.approx(100.0 + form_fill.TEXT_INSET)
    assert xr == pytest.approx(300.0 - form_fill.TEXT_INSET - w)
    assert yt == pytest.approx(520.0 - 9.0)
    assert yb == pytest.approx(500.0 + form_fill.TEXT_INSET)
    with pytest.raises(ValueError, match="align"):
        _origin(["x"], rect, align="middle")


def test_centered_text_never_leaves_its_box():
    """Every origin lies inside the rect, and a fitted line's extent does
    too — the property the rule exists for."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    rect = [37.5, 56.5, 394.9, 101.8]   # a real attorney-block box
    fit = form_fill.fit_text("Andrew Roe\n100 Main St, PMB 42\nSpringfield, CA 90000",
                             rect, {"fit": "shrink_wrap", "multiline": True})
    assert fit.fits
    for line, (x, y) in zip(fit.lines, _origin(fit.lines, rect, fit.font_size)):
        assert rect[0] <= x and x + stringWidth(line, form_fill.DEFAULT_FONT, fit.font_size) <= rect[2]
        assert rect[1] <= y <= rect[3] - fit.font_size * 0.72
