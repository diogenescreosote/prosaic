"""Tests for the descriptor-driven JC form filler.

Run from the repo root or pleading/:  python -m pytest pleading/tests -q

The most important test here is ``test_descriptor_matches_blank``: it
fails when the Judicial Council revises a form and the shipped blank's
field names/checkbox states no longer match the descriptor — the
failure mode that otherwise produces silently empty filings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))

import form_fill  # noqa: E402
import jc_common  # noqa: E402

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
        widgets[name] = obj
        widgets.setdefault(name.split(".")[-1], obj)

    missing = []
    for name, spec in (desc.get("fields") or {}).items():
        if spec.get("method") == "overlay":
            assert spec.get("rect"), f"{form_id}.{name}: overlay without rect"
            continue
        if spec.get("map") and spec["map"] not in widgets:
            missing.append(f"field {name} -> {spec['map']}")
    for name, spec in (desc.get("checkboxes") or {}).items():
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
    reader = PdfReader(str(out))
    has_case_number = any(spec.get("auto") == "case_number"
                          for spec in (desc.get("fields") or {}).values())
    if desc.get("technology") == "overlay":
        # Overlay outputs are flattened: no form machinery at all, and
        # the values live in the page CONTENT, not in field /V's.
        assert not (reader.get_fields() or {}), (
            f"{form_id}: overlay output must carry no AcroForm fields")
        if has_case_number:
            text = "".join(p.extract_text() for p in reader.pages)
            assert "24CV00000" in text, (
                f"{form_id}: case number not drawn into page content")
    else:
        # The case number must actually land in some field's /V.
        fields = reader.get_fields() or {}
        values = " | ".join(str(f.get("/V") or "") for f in fields.values())
        if has_case_number:
            assert "24CV00000" in values, f"{form_id}: case number not present in field values"


@pytest.mark.parametrize("form_id", FORMS)
def test_blank_default_fields_are_never_set_as_empty_string(form_id, tmp_path, monkeypatch):
    """A field left at its default "" must never reach pypdf as an
    explicit empty-string value via ``update_page_form_field_values``.

    Caught by hand, filling a real CIV-110: pypdf's generated appearance
    stream for an explicitly-set empty text value computes a vertical
    text position that lands a few ULPs off zero (e.g.
    "7.105427357601002e-15") and writes it in Python's scientific
    notation, which is not a valid PDF real number token -- the
    resulting `Td` operator is unparseable garbage to a strict reader
    (poppler included), even though the field is invisible either way.
    Reproducing the exact float-precision coincidence needs specific
    field geometry that fictional fixture data doesn't reliably hit, so
    this asserts the actual invariant the fix establishes -- an empty
    string is never handed to pypdf as a value to set -- rather than
    chasing the byte pattern it happens to produce.
    """
    from pypdf import PdfWriter

    calls = []
    original = PdfWriter.update_page_form_field_values

    def recording(self, page, values, *args, **kwargs):
        calls.append(dict(values))
        return original(self, page, values, *args, **kwargs)

    monkeypatch.setattr(PdfWriter, "update_page_form_field_values", recording)

    out = tmp_path / f"{form_id}.pdf"
    form_fill.fill(form_id, out, meta=dict(FIXTURE_META))

    empties = [name for call in calls for name, v in call.items() if v == ""]
    assert not empties, f"{form_id}: empty-string value(s) set explicitly: {empties}"


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
    fields = reader.get_fields() or {}
    values = " ".join(str(f.get("/V") or "") for f in fields.values())
    assert "See Attachment 1." in values


def test_unknown_data_key_is_reported(tmp_path):
    res = form_fill.fill("mc030", tmp_path / "x.pdf", meta=dict(FIXTURE_META),
                         data={"nonexistent_field": "boom"})
    assert any("unknown field" in w for w in res.warnings)


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

    reader = PdfReader(str(out))
    fields = reader.get_fields() or {}
    desc = form_fill.load_descriptor("civ110")

    def value_of(logical_name, section="checkboxes"):
        mapped = desc[section][logical_name]["map"]
        return str((fields.get(mapped) or {}).get("/V") or "")

    assert value_of("dismissal_with_prejudice") == "/1"
    assert value_of("pleading_type_cross_complaint_1") == "/Yes"
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

    reader = PdfReader(str(out))
    fields = reader.get_fields() or {}
    desc = form_fill.load_descriptor("civ110")

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
    leaks = []
    for name in checkbox_names:
        mapped = desc["checkboxes"][name]["map"]
        v = (fields.get(mapped) or {}).get("/V")
        if v:
            leaks.append(f"{name} -> {mapped} = {v!r}")
    assert not leaks, f"machine checked a box without human instruction: {leaks}"

    text_names = ["cross_complaint_1_date", "cross_complaint_1_name",
                  "cross_complaint_2_date", "cross_complaint_2_name",
                  "pleading_type_other_specify"]
    leaks = []
    for name in text_names:
        mapped = desc["fields"][name]["map"]
        v = str((fields.get(mapped) or {}).get("/V") or "")
        if v.strip():
            leaks.append(f"{name} -> {mapped} = {v!r}")
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
    reader = PdfReader(str(out))
    fields = reader.get_fields() or {}
    desc = form_fill.load_descriptor("civ110")

    def value_of(name):
        mapped = desc["checkboxes"][name]["map"]
        return str((fields.get(mapped) or {}).get("/V") or "")

    assert value_of("fee_waiver_did_not") == "/2"
    assert value_of("fee_waiver_did") == "", "sibling fee-waiver box unexpectedly checked"


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
    reader = PdfReader(str(out))
    fields = reader.get_fields() or {}
    desc = form_fill.load_descriptor("civ110")

    def value_of(name):
        mapped = desc["checkboxes"][name]["map"]
        return str((fields.get(mapped) or {}).get("/V") or "")

    # The two checkboxes actually asked for, on each side, must land.
    assert value_of("item2_signer_is_party") == "/2"
    assert value_of("item2_role_defendant_respondent") == "/Yes"
    assert value_of("item3_signer_is_attorney") == "/1"
    assert value_of("item3_role_cross_complainant") == "/Yes"

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

    reader = PdfReader(str(out))
    fields = reader.get_fields() or {}

    def value_of(map_name):
        f = fields.get(map_name)
        return str((f or {}).get("/V") or "")

    desc = form_fill.load_descriptor("mc050")
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
        mapped = desc["fields"][name]["map"]
        v = value_of(mapped)
        if v.strip():
            leaks.append(f"{name} -> {mapped} = {v!r}")
    assert not leaks, f"machine filled human/event-owned fields: {leaks}"

    blank_checkboxes = ["item5_consent_applies", "item6_consent_applies"]
    for name in blank_checkboxes:
        mapped = desc["checkboxes"][name]["map"]
        f = fields.get(mapped) or {}
        assert not f.get("/V"), f"{name} -> {mapped} was checked by a rich fill"

    # And confirm the rich data DID land where it belongs, so this test
    # cannot pass by accident (e.g. a broken fill that fills nothing).
    assert value_of("FillText29") == "JOHN SMITH"          # substituting_party_name
    assert value_of("FillText27") == "Sam Sattler, Esq."   # new_rep_name
    assert value_of("FillText51") == "Jane Roe"            # pos_recipient_1_name


@pytest.mark.skipif("subp010" not in FORMS or "mc025" not in FORMS,
                    reason="subp010/mc025 descriptor not present")
class TestSubp010RecordsAttachment:
    """SUBP-010 item 3 is a ONE-LINE widget: any real records demand
    must become 'See Attachment 3.' + an MC-025, with the form's own
    'Continued on Attachment 3.' box reflecting what happened."""

    ATTACH_CB = "List3[0].item3[0].limited1[0]"

    def _widget_values(self, path):
        vals = []
        for _p, name, obj in form_fill.iter_widgets(PdfReader(str(path))):
            v = obj.get("/V")
            if v is None and obj.get("/Parent") is not None:
                v = obj["/Parent"].get_object().get("/V")
            vals.append((name, "" if v is None else str(v)))
        return vals

    def _attachment_box(self, path):
        return [v for n, v in self._widget_values(path) if n.endswith(self.ATTACH_CB)]

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
        joined = " ".join(v for _n, v in self._widget_values(out)).replace("\n", " ")
        assert "See Attachment 3." in joined
        assert "SENTINEL7742" in joined, "records demand truncated"
        assert self._attachment_box(out) == ["/1"]

    def test_short_demand_fits_and_unchecks_the_box(self, tmp_path):
        out = tmp_path / "subp010_inline.pdf"
        res = form_fill.fill("subp010", out, meta=dict(FIXTURE_META),
                             data={"records_description": "Personnel file."})
        assert not res.overflows
        assert self._attachment_box(out) == [""], (
            "a demand that fits inline must clear 'Continued on Attachment 3.'")

    def test_cover_sheet_flow_keeps_the_box_checked(self, tmp_path):
        """No item-3 text at all: the demand is the attached pages, so the
        default stands and the box stays checked."""
        out = tmp_path / "subp010_cover.pdf"
        form_fill.fill("subp010", out, meta=dict(FIXTURE_META))
        assert self._attachment_box(out) == ["/1"]

