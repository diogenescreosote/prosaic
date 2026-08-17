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

    # The case number must actually land in some field's /V.
    reader = PdfReader(str(out))
    fields = reader.get_fields() or {}
    values = " | ".join(str(f.get("/V") or "") for f in fields.values())
    if any(spec.get("auto") == "case_number"
           for spec in (form_fill.load_descriptor(form_id).get("fields") or {}).values()):
        assert "24CV00000" in values, f"{form_id}: case number not present in field values"


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

