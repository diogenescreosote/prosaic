"""Tests for the descriptor-driven JC form filler.

Run from the repo root or pleading/:  python -m pytest pleading/tests -q

The most important test here is ``test_descriptor_matches_blank``: it
fails when the Judicial Council revises a form and the shipped blank's
field names/checkbox states no longer match the descriptor — the
failure mode that otherwise produces silently empty filings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import form_fill  # noqa: E402
import jc_common  # noqa: E402
import probe  # noqa: E402

from pypdf import PdfReader  # noqa: E402

FORMS = form_fill.list_forms()

FIXTURE_META = {
    "filer_name": "Jane Roe",
    "filer_address_lines": ["123 Main Street", "Springfield, CA 90000"],
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
    "paper_title": "DECLARATION OF JANE ROE",
}


# ---------------------------------------------------------------------------
# jc_common unit tests
# ---------------------------------------------------------------------------

def test_split_name_and_bar_number():
    assert jc_common.split_name_and_bar_number("Sally Sattler, Esq. SBN 123456") == (
        "Sally Sattler, Esq.", "123456")
    assert jc_common.split_name_and_bar_number("Jane Roe") == ("Jane Roe", "")
    assert jc_common.split_name_and_bar_number("Jane Roe", "999999") == ("Jane Roe", "999999")


def test_strip_county_prefix():
    assert jc_common.strip_county_prefix("COUNTY OF EXAMPLE") == "EXAMPLE"
    assert jc_common.strip_county_prefix("Example") == "Example"


def test_court_name_full():
    """Forms with a bare "NAME OF COURT:" label (SUBP-002) want the
    whole designation, composed from court_name + court_county with the
    county's own prefix tolerated either way."""
    assert jc_common.court_name_full(
        {"court_county": "COUNTY OF EXAMPLE"}
    ) == "SUPERIOR COURT OF CALIFORNIA, COUNTY OF EXAMPLE"
    assert jc_common.court_name_full(
        {"court_name": "SUPERIOR COURT OF THE STATE OF CALIFORNIA",
         "court_county": "EXAMPLE"}
    ) == "SUPERIOR COURT OF THE STATE OF CALIFORNIA, COUNTY OF EXAMPLE"
    assert jc_common.court_name_full({}) == "SUPERIOR COURT OF CALIFORNIA"


def test_declarant_from_title():
    assert jc_common.declarant_name(
        {"paper_title": "DECLARATION OF JANE ROE IN SUPPORT OF MOTION"}) == "JANE ROE"
    assert jc_common.declarant_name({"paper_title": "MEMORANDUM"}) is None
    assert jc_common.declarant_name({"declarant_name": "X"}) == "X"


def test_filer_role_binding_is_verbatim():
    """Unlike attorney_for, the filer_role binding keeps the whole role —
    forms with a bare '(TITLE)' line under a signature (SUBP-010) print
    no 'Attorney for' label of their own."""
    meta = {"filer_role": "Attorney for Plaintiff JOHN SMITH"}
    assert jc_common.AUTO_BINDINGS["filer_role"](meta) == (
        "Attorney for Plaintiff JOHN SMITH")
    assert jc_common.AUTO_BINDINGS["attorney_for"](meta) == "Plaintiff JOHN SMITH"
    assert jc_common.AUTO_BINDINGS["filer_role"]({}) == ""


def test_attorney_block_folds_unit_designator_and_keeps_city():
    """A PMB/Suite/Apt line joins the street line, postal style, so a
    four-line box never loses the city line; and nothing is dropped
    silently when the block does fit."""
    lines = jc_common.attorney_block_lines({
        "filer_name": "Jane Roe",
        "filer_address_lines": ["100 Main St", "PMB 42", "Springfield, CA 90000"],
    })
    assert lines == ["Jane Roe", "100 Main St, PMB 42", "Springfield, CA 90000", ""]
    lines = jc_common.attorney_block_lines({
        "filer_name": "Jane Roe",
        "filer_address_lines": ["Roe & Doe LLP", "100 Main St", "Suite 300", "Springfield, CA 90000"],
    })
    assert lines == ["Jane Roe", "Roe & Doe LLP", "100 Main St, Suite 300", "Springfield, CA 90000"]


def test_attorney_block_warns_instead_of_silently_truncating(capsys):
    lines = jc_common.attorney_block_lines({
        "filer_name": "Jane Roe",
        "filer_address_lines": ["Roe & Doe LLP", "Tower Two", "100 Main St", "Springfield, CA 90000"],
    })
    assert len(lines) == 4
    err = capsys.readouterr().err
    assert "WARNING" in err and "Springfield, CA 90000" in err


def test_attorney_for_self_represented():
    assert jc_common.attorney_for({"filer_role": "Respondent, In Pro Per"}) == (
        "Respondent, In Pro Per")
    assert jc_common.attorney_for(
        {"filer_role": "Attorney for Petitioner JOHN SMITH"}) == "Petitioner JOHN SMITH"


# ---------------------------------------------------------------------------
# fit_text unit tests
# ---------------------------------------------------------------------------

def test_fit_shrinks_until_it_fits():
    rect = [0, 0, 120, 14]  # narrow single-line box
    long = "This is a fairly long string that will not fit at nine points"
    r = form_fill.fit_text(long, rect, {"fit": "shrink"})
    assert r.font_size < form_fill.DEFAULT_FONT_SIZE
    r_strict = form_fill.fit_text(long, rect, {"fit": "none"})
    assert not r_strict.fits


def test_fit_wrap_produces_lines():
    rect = [0, 0, 200, 200]
    text = " ".join(["word"] * 60)
    r = form_fill.fit_text(text, rect, {"fit": "wrap"})
    assert len(r.lines) > 1 and r.fits


# ---------------------------------------------------------------------------
# Descriptor ↔ blank consistency (revision-drift alarm)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form_id", FORMS)
def test_descriptor_matches_blank(form_id):
    desc = form_fill.load_descriptor(form_id)
    blank = form_fill.blank_path(desc)
    assert blank.exists(), f"blank missing: {blank}"

    widgets = {}
    for _page, name, obj in form_fill.iter_widgets(PdfReader(str(blank))):
        # setdefault, matching fill(): when two widgets share a
        # qualified name (radio pairs), the FIRST one is the one a
        # map: reaches, so it is the one the on_value must match.
        widgets.setdefault(name, obj)
        widgets.setdefault(name.split(".")[-1], obj)

    missing = []
    for name, spec in (desc.get("fields") or {}).items():
        if spec.get("method") == "overlay":
            assert spec.get("rect"), f"{form_id}.{name}: overlay without rect"
            continue
        if spec.get("map") and spec["map"] not in widgets:
            missing.append(f"field {name} -> {spec['map']}")
    for name, spec in (desc.get("checkboxes") or {}).items():
        if not spec.get("map"):
            # Hand-authored geometry (e.g. a radio pair whose widgets
            # share one qualified name): a rect is the whole contract.
            assert spec.get("rect"), f"{form_id}.{name}: checkbox without map or rect"
            continue
        obj = widgets.get(spec.get("map", ""))
        if obj is None:
            missing.append(f"checkbox {name} -> {spec.get('map')}")
            continue
        on = spec.get("on_value")
        if on:
            ap = obj.get("/AP")
            if ap and "/N" in ap.get_object():
                states = [str(k) for k in ap.get_object()["/N"].keys()]
                assert on in states, (
                    f"{form_id}.{name}: on_value {on} not in widget states {states}")
    assert not missing, (
        f"{form_id}: descriptor references fields absent from {blank.name} "
        f"(form revision drift?): {missing}")


# ---------------------------------------------------------------------------
# Smoke fills
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form_id", FORMS)
def test_smoke_fill(form_id, tmp_path):
    out = tmp_path / f"{form_id}.pdf"
    res = form_fill.fill(form_id, out, meta=dict(FIXTURE_META))
    assert out.exists() and out.stat().st_size > 1000
    drift = [w for w in res.warnings if "not found" in w or "drift" in w]
    assert not drift, f"{form_id}: {drift}"

    desc = form_fill.load_descriptor(form_id)
    has_case_number = any(spec.get("auto") == "case_number"
                          for spec in (desc.get("fields") or {}).values())
    # A fill is flattened: no form machinery at all, and the values
    # live in the page CONTENT (ADR-0046).
    assert probe.has_no_form_layer(out), f"{form_id}: output must carry no form layer"
    if has_case_number:
        assert "24CV00000" in probe.all_text(out), (
            f"{form_id}: case number not drawn into page content")


@pytest.mark.skipif("mc025" not in FORMS, reason="mc025 descriptor not present")
def test_overflow_spills_to_mc025(tmp_path):
    out = tmp_path / "mc030_overflow.pdf"
    huge = ("This declaration body is deliberately far too long for the box. " * 80)
    res = form_fill.fill("mc030", out, meta=dict(FIXTURE_META), data={"body": huge})
    assert res.overflows, "expected an overflow record"
    reader = PdfReader(str(out))
    base_pages = len(PdfReader(str(form_fill.blank_path(
        form_fill.load_descriptor("mc030")))).pages)
    assert len(reader.pages) > base_pages, "MC-025 attachment page(s) not appended"
    assert "See Attachment 1." in probe.page_text(out, 1).replace("\n", " ")


def test_unknown_data_key_is_reported(tmp_path):
    res = form_fill.fill("mc030", tmp_path / "x.pdf", meta=dict(FIXTURE_META),
                         data={"nonexistent_field": "boom"})
    assert any("unknown field" in w for w in res.warnings)


class TestCoverSheetCachePath:
    """Two sources with the same bare filename in different src/
    subfolders must not collide on the same cover-sheet cache file
    (they used to, keyed only by ``<source_stem>.<form_id>.pdf``)."""

    def _make_source(self, case_dir, *parts):
        src = case_dir / "src"
        for p in parts[:-1]:
            src = src / p
        src.mkdir(parents=True, exist_ok=True)
        md = src / parts[-1]
        md.write_text("dummy source\n")
        return md

    def test_same_stem_different_subfolders_cache_distinctly(self, tmp_path):
        case_dir = tmp_path / "smith_v_roe"
        a = self._make_source(case_dir, "packet_a", "proposed_order.md")
        b = self._make_source(case_dir, "packet_b", "proposed_order.md")

        cache_a = form_fill.cover_sheet_cache_path("mc030", a)
        cache_b = form_fill.cover_sheet_cache_path("mc030", b)

        assert cache_a != cache_b
        assert cache_a.name == cache_b.name == "proposed_order.mc030.pdf"
        assert cache_a.parent.name == "packet_a"
        assert cache_b.parent.name == "packet_b"

        assets = case_dir / "assets" / "decl_cover_sheets"
        assert cache_a == assets / "packet_a" / "proposed_order.mc030.pdf"
        assert cache_b == assets / "packet_b" / "proposed_order.mc030.pdf"

    def test_source_directly_in_src_has_no_extra_subfolder(self, tmp_path):
        case_dir = tmp_path / "smith_v_roe"
        top = self._make_source(case_dir, "complaint.md")
        cache = form_fill.cover_sheet_cache_path("mc030", top)
        assert cache == case_dir / "assets" / "decl_cover_sheets" / "complaint.mc030.pdf"

    def test_source_outside_src_falls_back_to_bare_stem(self, tmp_path):
        scratch_dir = tmp_path / "scratch"
        scratch_dir.mkdir()
        outside = scratch_dir / "notes.md"
        outside.write_text("dummy\n")
        cache = form_fill.cover_sheet_cache_path("mc030", outside)
        # No `src/` ancestor: falls back to case_dir = parent.parent (as
        # find_case_dir always did), with no mirrored subfolder.
        assert cache.name == "notes.mc030.pdf"
        assert cache.parent.name == "decl_cover_sheets"

    def test_ensure_cached_writes_distinct_files_for_same_stem(self, tmp_path):
        case_dir = tmp_path / "smith_v_roe"
        a = self._make_source(case_dir, "packet_a", "proposed_order.md")
        b = self._make_source(case_dir, "packet_b", "proposed_order.md")

        out_a = form_fill.ensure_cached("mc030", dict(FIXTURE_META), a)
        out_b = form_fill.ensure_cached("mc030", dict(FIXTURE_META), b)

        assert out_a != out_b
        assert out_a.exists() and out_b.exists()

    def test_ensure_cached_refills_when_the_engine_is_newer(self, tmp_path):
        import os

        case_dir = tmp_path / "smith_v_roe"
        src = self._make_source(case_dir, "packet_a", "proposed_order.md")
        cache = form_fill.ensure_cached("mc030", dict(FIXTURE_META), src)
        engine = Path(form_fill.__file__).stat().st_mtime
        os.utime(src, (engine - 100, engine - 100))
        os.utime(cache, (engine - 50, engine - 50))
        form_fill.ensure_cached("mc030", dict(FIXTURE_META), src)
        assert cache.stat().st_mtime > engine - 50

    def test_ensure_cached_refills_when_matter_yaml_is_newer(self, tmp_path):
        """A matter-wide front-matter default (form_fill_font, a filer
        address) changes what the fill draws without touching the
        source, so a newer matter.yaml makes the cache stale."""
        import os
        import time

        case_dir = tmp_path / "smith_v_roe"
        src = self._make_source(case_dir, "packet_a", "proposed_order.md")
        cache = form_fill.ensure_cached("mc030", dict(FIXTURE_META), src)
        now = time.time()
        os.utime(src, (now - 100, now - 100))
        os.utime(cache, (now - 50, now - 50))
        form_fill.ensure_cached("mc030", dict(FIXTURE_META), src)
        assert cache.stat().st_mtime == pytest.approx(now - 50), "fresh cache refilled"
        (case_dir / "matter.yaml").write_text("front_matter_defaults: {}\n")
        form_fill.ensure_cached("mc030", dict(FIXTURE_META), src)
        assert cache.stat().st_mtime > now - 50


# ---------------------------------------------------------------------------
# Fill font: form_fill_font / descriptor font: / --font
# ---------------------------------------------------------------------------

def _drawn_fonts(pdf: Path, needle: str) -> set[str]:
    """Fonts of every text span containing ``needle`` on any page."""
    import fitz

    fonts: set[str] = set()
    with fitz.open(str(pdf)) as doc:
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if needle in span["text"]:
                            fonts.add(span["font"])
    return fonts


def test_resolve_fill_font_aliases_and_refusal():
    assert form_fill.resolve_fill_font(None) == form_fill.DEFAULT_FONT == "Helvetica"
    assert form_fill.resolve_fill_font("") == "Helvetica"
    assert form_fill.resolve_fill_font("courier") == "Courier"
    assert form_fill.resolve_fill_font("COURIER") == "Courier"
    assert form_fill.resolve_fill_font("Courier") == "Courier"
    assert form_fill.resolve_fill_font("times") == "Times-Roman"
    with pytest.raises(ValueError, match="fill font"):
        form_fill.resolve_fill_font("Comic Sans")


def test_default_fill_font_is_unchanged(tmp_path):
    out = tmp_path / "mc030.pdf"
    form_fill.fill("mc030", out, meta=dict(FIXTURE_META))
    assert _drawn_fonts(out, "24CV00000") == {"Helvetica"}


def test_form_fill_font_meta_draws_every_field_in_courier(tmp_path):
    out = tmp_path / "mc030.pdf"
    form_fill.fill("mc030", out, meta={**FIXTURE_META, "form_fill_font": "courier"},
                   data={"body": "Short body text."})
    assert _drawn_fonts(out, "24CV00000") == {"Courier"}
    assert _drawn_fonts(out, "Short body text.") == {"Courier"}


def test_explicit_font_beats_meta_and_field_font_beats_both(tmp_path, monkeypatch):
    out = tmp_path / "mc030.pdf"
    form_fill.fill("mc030", out, meta={**FIXTURE_META, "form_fill_font": "courier"},
                   font="times")
    assert _drawn_fonts(out, "24CV00000") == {"Times-Roman"}

    real = form_fill.load_descriptor

    def pinned(form_id):
        desc = real(form_id)
        if form_id == "mc030":
            fields = dict(desc["fields"])
            fields["case_number"] = {**fields["case_number"], "font": "Helvetica-Bold"}
            desc = {**desc, "fields": fields, "font": "times"}
        return desc

    monkeypatch.setattr(form_fill, "load_descriptor", pinned)
    out2 = tmp_path / "mc030_pinned.pdf"
    form_fill.fill("mc030", out2, meta={**FIXTURE_META, "form_fill_font": "courier"})
    assert _drawn_fonts(out2, "24CV00000") == {"Helvetica-Bold"}
    # The descriptor's top-level font: yields to the meta's choice ...
    assert _drawn_fonts(out2, "Jane Roe") == {"Courier"}
    # ... and decides when nothing else does.
    out3 = tmp_path / "mc030_desc.pdf"
    form_fill.fill("mc030", out3, meta=dict(FIXTURE_META))
    assert _drawn_fonts(out3, "Jane Roe") == {"Times-Roman"}


def test_fit_measures_with_the_chosen_font():
    """Courier is wider than Helvetica: a value that fits at full size
    in the default face must shrink in Courier, because fitting measures
    the font that will be drawn."""
    rect = [0, 0, 120, 12]
    text = "Mavis Example, nonparty"
    spec = {"fit": "shrink", "font_size": 9}
    helv = form_fill.fit_text(text, rect, spec)
    cour = form_fill.fit_text(text, rect, {**spec, "font": "Courier"})
    assert helv.fits and helv.font_size == 9
    assert cour.fits and cour.font_size < 9


@pytest.mark.skipif("mc025" not in FORMS, reason="mc025 descriptor not present")
def test_overflow_attachment_follows_the_fill_font(tmp_path):
    out = tmp_path / "mc030_overflow.pdf"
    huge = "Overflowing declaration text for the attachment. " * 80
    res = form_fill.fill("mc030", out, meta={**FIXTURE_META, "form_fill_font": "courier"},
                         data={"body": huge})
    assert res.overflows
    assert _drawn_fonts(out, "See Attachment 1.") == {"Courier"}
    assert _drawn_fonts(out, "Overflowing declaration") == {"Courier"}


@pytest.mark.skipif("civ110" not in FORMS, reason="civ110 descriptor not present")
def test_civ110_dismissal_and_pleading_type_checkboxes_render_checked(tmp_path):
    """Item 1.a/1.b are fillable when a human names the choice
    explicitly (specs/pleading/forms/civ110.md, promise 2). Check one
    dismissal-type box and one pleading-type box (plus its paired
    cross-complaint date/name fields) and confirm each lands on its
    OWN mapped widget, not a neighboring option in the same group."""
    out = tmp_path / "civ110_checked.pdf"
    form_fill.fill("civ110", out, meta=dict(FIXTURE_META), data={
        "dismissal_with_prejudice": True,
        "pleading_type_cross_complaint_1": True,
        "cross_complaint_1_date": "1/1/2026",
        "cross_complaint_1_name": "JOHN SMITH",
    })

    def value_of(logical_name, section="checkboxes"):
        if section == "fields":
            return probe.field_text(out, "civ110", logical_name)
        return probe.CHECK_MARK if probe.checkbox_marked(out, "civ110", logical_name) else ""

    assert value_of("dismissal_with_prejudice") == probe.CHECK_MARK
    assert value_of("pleading_type_cross_complaint_1") == probe.CHECK_MARK
    assert value_of("cross_complaint_1_date", "fields") == "1/1/2026"
    assert value_of("cross_complaint_1_name", "fields") == "JOHN SMITH"

    # Negative control: the sibling options in each group must stay
    # unchecked, proving the fill landed on its own widget rather than
    # the whole exclGroup/checkbox family.
    for sibling in ("dismissal_without_prejudice",
                    "dismissal_without_prejudice_664_6",
                    "pleading_type_complaint", "pleading_type_petition",
                    "pleading_type_cross_complaint_2",
                    "pleading_type_entire_action", "pleading_type_other"):
        assert value_of(sibling) == "", f"{sibling} unexpectedly checked"
    assert value_of("cross_complaint_2_date", "fields") == ""
    assert value_of("cross_complaint_2_name", "fields") == ""


@pytest.mark.skipif("civ110" not in FORMS, reason="civ110 descriptor not present")
def test_civ110_dismissal_checkboxes_default_unchecked_on_a_rich_fill(tmp_path):
    """Mirrors the mandatory-blanks-survive-a-rich-fill pattern used for
    civ110's items 2/3 and mc050's items 4-6: filling every caption
    field, with NO item 1.a/1.b instruction, must leave every new
    checkbox and its paired text field unchecked/blank by default."""
    out = tmp_path / "civ110_no_checkboxes.pdf"
    form_fill.fill("civ110", out, meta=dict(FIXTURE_META))

    checkbox_names = [
        "dismissal_with_prejudice", "dismissal_without_prejudice",
        "dismissal_without_prejudice_664_6", "pleading_type_complaint",
        "pleading_type_petition", "pleading_type_cross_complaint_1",
        "pleading_type_cross_complaint_2", "pleading_type_entire_action",
        "pleading_type_other",
        "fee_waiver_did", "fee_waiver_did_not",
        "item2_signer_is_attorney", "item2_signer_is_party",
        "item2_role_plaintiff_petitioner", "item2_role_defendant_respondent",
        "item2_role_cross_complainant",
        "item3_signer_is_attorney", "item3_signer_is_party",
        "item3_role_plaintiff_petitioner", "item3_role_defendant_respondent",
        "item3_role_cross_complainant",
    ]
    leaks = [name for name in checkbox_names if probe.checkbox_marked(out, "civ110", name)]
    assert not leaks, f"machine checked a box without human instruction: {leaks}"

    text_names = ["cross_complaint_1_date", "cross_complaint_1_name",
                  "cross_complaint_2_date", "cross_complaint_2_name",
                  "pleading_type_other_specify"]
    leaks = []
    for name in text_names:
        v = probe.field_text(out, "civ110", name)
        if v.strip():
            leaks.append(f"{name} = {v!r}")
    assert not leaks, f"machine filled a fill-in without human instruction: {leaks}"


@pytest.mark.skipif("civ110" not in FORMS, reason="civ110 descriptor not present")
def test_civ110_fee_waiver_checkboxes_render_checked(tmp_path):
    """Item 2's fee-waiver fact ('The court did / did not waive court
    fees and costs...') is fillable on explicit instruction, same as
    item 1.a/1.b (specs/pleading/forms/civ110.md, promise 2a) — but
    only ever on a human's explicit say-so, never inferred."""
    out = tmp_path / "civ110_fee_waiver.pdf"
    form_fill.fill("civ110", out, meta=dict(FIXTURE_META), data={
        "fee_waiver_did_not": True,
    })
    assert probe.checkbox_marked(out, "civ110", "fee_waiver_did_not")
    assert not probe.checkbox_marked(out, "civ110", "fee_waiver_did"), (
        "sibling fee-waiver box unexpectedly checked")


@pytest.mark.skipif("civ110" not in FORMS, reason="civ110 descriptor not present")
def test_civ110_item2_role_and_identification_checkboxes_do_not_leak_to_item3(tmp_path):
    """Regression pin for the reported bug this descriptor work was
    built to catch: a human, previewing a real fill, found that
    checking item 2's Plaintiff/Petitioner role box also appeared to
    check item 3's identical-looking box. Verified empirically (see
    civ110.yaml's agent_guide, 'Verified: item2 vs. item3
    independence') that the two signature blocks' identification and
    role checkboxes are genuinely independent AcroForm fields despite
    the role group reusing an identical leaf field name
    ('RB2Choice2[0/1/2]') across both blocks. This test fills ONE
    block's checkboxes (using values chosen to be distinguishable from
    the other block's, in case a future edit garbles which map goes
    with which logical name) and asserts the untouched block's fields
    remain completely unset, in both directions."""
    out = tmp_path / "civ110_no_leak.pdf"
    form_fill.fill("civ110", out, meta=dict(FIXTURE_META), data={
        "item2_signer_is_party": True,
        "item2_role_defendant_respondent": True,
        "item3_signer_is_attorney": True,
        "item3_role_cross_complainant": True,
    })

    def value_of(name):
        return probe.checkbox_marked(out, "civ110", name)

    # The two checkboxes actually asked for, on each side, must land.
    assert value_of("item2_signer_is_party")
    assert value_of("item2_role_defendant_respondent")
    assert value_of("item3_signer_is_attorney")
    assert value_of("item3_role_cross_complainant")

    # Every OTHER checkbox in both blocks -- including each block's own
    # sibling options and, critically, the other block's copy of the
    # SAME logical checkbox -- must still read empty. This is the
    # cross-contamination check: item2_role_defendant_respondent must
    # not have also set item3_role_defendant_respondent, and
    # item3_signer_is_attorney must not have also set
    # item2_signer_is_attorney.
    must_stay_unset = [
        "item2_signer_is_attorney", "item2_role_plaintiff_petitioner",
        "item2_role_cross_complainant",
        "item3_signer_is_party", "item3_role_plaintiff_petitioner",
        "item3_role_defendant_respondent",
    ]
    leaks = [name for name in must_stay_unset if value_of(name)]
    assert not leaks, f"cross-block or sibling bleed detected: {leaks}"


@pytest.mark.skipif("mc050" not in FORMS, reason="mc050 descriptor not present")
def test_mc050_consent_and_service_fields_stay_blank(tmp_path):
    """A rich fill of every substantive MC-050 field (who's substituting,
    the former/new representative's details, the party's role, and even
    a known proof-of-service recipient) must never leak into the three
    consent signature blocks (items 4-6) or the proof-of-service page's
    date/declarant fields — those record a person's own consent, or an
    event (the mailing) that has not happened yet (specs/pleading/forms/mc050.md,
    promises 2-4)."""
    out = tmp_path / "mc050.pdf"
    rich_data = {
        "substituting_party_name": "JOHN SMITH",
        "former_rep_party_self": True,
        "new_rep_attorney": True,
        "new_rep_name": "Sam Sattler, Esq.",
        "new_rep_bar_number": "123456",
        "new_rep_address": "500 Market Street, Suite 100, Springfield, CA 90000",
        "new_rep_phone": "(555) 555-0199",
        "party_role_plaintiff": True,
        "other_role_specify": "Cross-defendant",
        "pos_recipient_1_name": "Jane Roe",
        "pos_recipient_1_address": "123 Main Street, Springfield, CA 90000",
    }
    form_fill.fill("mc050", out, meta=dict(FIXTURE_META), data=dict(rich_data))

    def value_of(name):
        return probe.field_text(out, "mc050", name)

    blank_fields = [
        "item4_date", "item4_print_name",
        "item5_date", "item5_print_name",
        "item6_date", "item6_print_name",
        "pos_mailing_date", "pos_mailing_place",
        "pos_declaration_date", "pos_declarant_name",
        "pos_declarant_address",
    ]
    leaks = []
    for name in blank_fields:
        v = value_of(name)
        if v.strip():
            leaks.append(f"{name} = {v!r}")
    assert not leaks, f"machine filled human/event-owned fields: {leaks}"

    blank_checkboxes = ["item5_consent_applies", "item6_consent_applies"]
    for name in blank_checkboxes:
        assert not probe.checkbox_marked(out, "mc050", name), (
            f"{name} was checked by a rich fill")

    # And confirm the rich data DID land where it belongs, so this test
    # cannot pass by accident (e.g. a broken fill that fills nothing).
    assert value_of("substituting_party_name") == "JOHN SMITH"
    assert value_of("new_rep_name") == "Sam Sattler, Esq."
    assert value_of("pos_recipient_1_name") == "Jane Roe"


@pytest.mark.skipif("subp010" not in FORMS or "mc025" not in FORMS,
                    reason="subp010/mc025 descriptor not present")
class TestSubp010RecordsAttachment:
    """SUBP-010 item 3 is a ONE-LINE widget: any real records demand
    must become 'See Attachment 3.' + an MC-025, with the form's own
    'Continued on Attachment 3.' box reflecting what happened."""

    ATTACH_CB = "continued_on_attachment_3"

    def _attachment_box(self, path):
        return probe.checkbox_marked(path, "subp010", self.ATTACH_CB)

    def test_long_demand_overflows_and_checks_the_box(self, tmp_path):
        out = tmp_path / "subp010_overflow.pdf"
        demand = ("All monthly account statements, deposit slips, withdrawal "
                  "records, wire transfer records, and signature cards SENTINEL7742 "
                  "for any account held in the name of JANE ROE for the period "
                  "January 1, 2024 through December 31, 2025.")
        res = form_fill.fill("subp010", out, meta=dict(FIXTURE_META),
                             data={"records_description": demand})
        assert res.overflows and res.overflows[0]["label"] == "Attachment 3"
        base = len(PdfReader(str(form_fill.blank_path(
            form_fill.load_descriptor("subp010")))).pages)
        assert len(PdfReader(str(out)).pages) > base, "MC-025 not appended"
        joined = probe.all_text(out).replace("\n", " ")
        assert "See Attachment 3." in joined
        assert "SENTINEL7742" in joined, "records demand truncated"
        assert self._attachment_box(out)

    def test_short_demand_fits_and_unchecks_the_box(self, tmp_path):
        out = tmp_path / "subp010_inline.pdf"
        res = form_fill.fill("subp010", out, meta=dict(FIXTURE_META),
                             data={"records_description": "Personnel file."})
        assert not res.overflows
        assert not self._attachment_box(out), (
            "a demand that fits inline must clear 'Continued on Attachment 3.'")

    def test_cover_sheet_flow_keeps_the_box_checked(self, tmp_path):
        """No item-3 text at all: the demand is the attached pages, so the
        default stands and the box stays checked."""
        out = tmp_path / "subp010_cover.pdf"
        form_fill.fill("subp010", out, meta=dict(FIXTURE_META))
        assert self._attachment_box(out)



def test_esign_fields_export_geometry_for_the_sidecar():
    """form_fill.esign_fields returns every esign field as a sidecar
    record (top-left points, role 'Signer N' by party position), so the
    build can place a form's signature/date lines in DocuSeal."""
    import form_fill
    fields = form_fill.esign_fields("mc040")
    assert fields, "mc040 declares esign fields"
    for f in fields:
        assert set(f) >= {"name", "role", "type", "page", "x", "y_top", "w", "h"}
        assert f["role"].startswith("Signer ")
        assert f["type"] in form_fill.ESIGN_TYPES
        assert f["page"] >= 1 and f["h"] > 0 and f["w"] > 0
    # party position -> role number: mc040's first party is Signer 1
    assert any(f["role"] == "Signer 1" for f in fields)


# ---------------------------------------------------------------------------
# RA-010 / RA-020: remote appearance (specs/pleading/forms/ra010.md, ra020.md)
# ---------------------------------------------------------------------------

RA010_GRID = {
    # The declaration-of-notice blocks recycle leaf names (rows 3/5/7/8
    # share T162-T165; rows 4/6 share CheckBox24/Field2/T166-T169), so
    # each block gets its own sentinel and must land in its own box.
    f"notice{n}_{part}": f"N{n}{part.upper()}"
    for n in range(1, 9)
    for part in ("name", "date", "method", "address")
}


@pytest.mark.skipif("ra010" not in FORMS, reason="ra010 descriptor not present")
def test_ra010_files_two_pages_and_keeps_the_instructions_on_request(tmp_path):
    """Page 3 is the form's own instructions ("need not be filed"):
    `filed_pages` drops it from every fill, an explicit page spec still
    reaches it, and the e-sign sidecar follows the pages written."""
    out = tmp_path / "ra010.pdf"
    form_fill.fill("ra010", out, meta=dict(FIXTURE_META))
    assert len(PdfReader(str(out)).pages) == 2
    assert "Instructions for Giving Notice" not in probe.all_text(out)
    sidecar = json.loads(out.with_name(out.name + ".fields.json").read_text())
    assert {f["page"] for f in sidecar["fields"]} == {2}
    assert sorted(f["type"] for f in sidecar["fields"]) == [
        "date", "date", "signature", "signature"]

    full = tmp_path / "ra010_full.pdf"
    form_fill.fill("ra010", full, meta=dict(FIXTURE_META), pages="1-3")
    assert len(PdfReader(str(full)).pages) == 3
    assert "Instructions for Giving Notice" in probe.all_text(full)


@pytest.mark.skipif("ra010" not in FORMS, reason="ra010 descriptor not present")
def test_ra010_grid_blocks_land_in_their_own_boxes_and_signing_stays_blank(tmp_path):
    out = tmp_path / "ra010_rich.pdf"
    data = {
        **RA010_GRID,
        "notice8_other": True,
        "notice5_other": True,
        "scope_proceeding": True,
        "appearing_other": True,
        "appearing_other_name_role": "Mavis Example, nonparty witness",
        "proceeding_type": "Evidentiary hearing",
    }
    form_fill.fill("ra010", out, meta=dict(FIXTURE_META), data=data)
    assert probe.has_no_form_layer(out)
    for name, value in RA010_GRID.items():
        assert probe.field_text(out, "ra010", name) == value, name
    assert probe.checkbox_marked(out, "ra010", "notice8_other")
    assert probe.checkbox_marked(out, "ra010", "notice5_other")
    assert not probe.checkbox_marked(out, "ra010", "notice7_other")
    # 2a and 2b share the leaf name Ch1; only 2b was asked for.
    assert probe.checkbox_marked(out, "ra010", "scope_proceeding")
    assert not probe.checkbox_marked(out, "ra010", "scope_throughout_case")
    text = probe.all_text(out)
    assert "24CV00000" in probe.page_text(out, 2), "page-2 caption"
    assert "Mavis Example, nonparty witness" in text
    for blank in ("sig_date", "decl_sig_date"):
        assert not probe.field_text(out, "ra010", blank).strip(), blank
    assert probe.field_text(out, "ra010", "print_name") == "Jane Roe"


@pytest.mark.skipif("ra020" not in FORMS, reason="ra020 descriptor not present")
def test_ra020_judicial_signature_block_is_never_filled(tmp_path):
    out = tmp_path / "ra020.pdf"
    data = {
        "proceeding_type": "Evidentiary hearing",
        "remote_permitted": True,
        "remote_names": "Mavis Example\nSam Sample",
        "remote_roles": "Nonparty witness\nNonparty witness",
        "tech_video_only": True,
    }
    form_fill.fill("ra020", out, meta=dict(FIXTURE_META), data=data)
    assert probe.has_no_form_layer(out)
    assert len(PdfReader(str(out)).pages) == 1
    assert not probe.field_text(out, "ra020", "judge_date").strip()
    assert not probe.field_text(out, "ra020", "judge_name").strip()
    assert not out.with_name(out.name + ".fields.json").exists(), (
        "RA-020 declares no e-sign party: the judicial signature is the court's")
    assert probe.checkbox_marked(out, "ra020", "remote_permitted")
    assert not probe.checkbox_marked(out, "ra020", "in_person_required")
    assert "Sam Sample" in probe.field_text(out, "ra020", "remote_names")


@pytest.mark.skipif("ra020" not in FORMS, reason="ra020 descriptor not present")
@pytest.mark.parametrize("font", [None, "courier"])
def test_ra020_columns_center_under_their_headings_and_stay_level(tmp_path, font):
    """Items 2 and 3a print "Name" and "Role in Case" headings over each
    column; every filled line centers under its heading, and each name
    sits on its role's baseline (specs/pleading/forms/ra020.md, promise 2)."""
    import fitz

    out = tmp_path / "ra020.pdf"
    names = ["Mary Major", "Mavis Example", "A Much Longer Witness Name"]
    roles = ["Party", "Nonparty witness", "Expert"]
    data = {
        "in_person_names": names[0],
        "in_person_roles": roles[0],
        "remote_names": "\n".join(names[1:]),
        "remote_roles": "\n".join(roles[1:]),
    }
    form_fill.fill("ra020", out, meta=dict(FIXTURE_META), data=data, font=font)
    with fitz.open(str(out)) as doc:
        lines = [
            (" ".join(s["text"] for s in ln["spans"]).strip(), fitz.Rect(ln["bbox"]))
            for b in doc[0].get_text("dict")["blocks"] for ln in b.get("lines", [])
        ]
    blank_words = fitz.open(str(form_fill.blank_path(form_fill.load_descriptor("ra020"))))[0]
    words = blank_words.get_text("words")

    def heading_centers(word):
        return sorted(((w[0] + w[2]) / 2, w[1]) for w in words if w[4] == word)

    name_x = heading_centers("Name")[0][0]
    role_l = [w for w in words if w[4] == "Role"][0]
    case_r = [w for w in words if w[4] == "Case"][0]
    role_x = (role_l[0] + case_r[2]) / 2

    def found(text):
        hits = [r for t, r in lines if t == text]
        assert len(hits) == 1, f"{text!r} drawn {len(hits)} times"
        return hits[0]

    for name, role in zip(names, roles):
        n_rect, r_rect = found(name), found(role)
        assert abs((n_rect.x0 + n_rect.x1) / 2 - name_x) < 1.5, name
        assert abs((r_rect.x0 + r_rect.x1) / 2 - role_x) < 1.5, role
        assert abs(n_rect.y1 - r_rect.y1) < 0.5, f"{name} not level with {role}"
