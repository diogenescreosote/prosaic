"""AI visual QA across the whole form registry (specs/pleading/forms/).

The subpoena flow has dedicated judgments in test_form_filling.py; this
module covers every registered form with a rendered-page judgment, plus
a calibration check proving the judge fails obviously bad output — a
judge that can't fail is decoration, not testing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import form_fill
from tests.harness import scenario
from tests.harness.ai import assert_judgment, judge, skip_if_unavailable

META = {
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

# form -> (realistic data, form-specific rubric emphasis)
CASES = {
    "mc030": ({}, "the body should read 'See attached Declaration of JANE ROE.'; "
                  "date, signature, and all role checkboxes empty"),
    "mc025": ({"attachment_number": "9",
               "body": "Continued facts in support of the motion."},
              "short title 'JOHN SMITH v. JANE ROE', case number, attachment "
              "number 9; body legible at top of the area"),
    "civ110": ({}, "caption filled; every dismissal-type/party checkbox, date, "
                   "and both signature blocks empty (dismissal decisions are human)"),
    "efs020": ({}, "party and document-title lines filled; page-2 proof of "
                   "service entirely blank; date/signature empty"),
    "subp010": ({"deponent": "Custodian of Records, Example Bank, N.A., "
                             "500 Market Street, Example City, CA 90000, "
                             "(555) 555-0199",
                 "deposition_officer": "Example Records Service, Inc.",
                 "production_date": "September 15, 2026",
                 "production_time": "10:00 a.m.",
                 "production_location": "200 Commerce Way, Suite 300, "
                                        "Example City, CA 90000",
                 "method_mail_to_officer": True,
                 "records_description":
                     "All monthly account statements, deposit slips, and "
                     "signature cards for any account held in the name of "
                     "JANE ROE, including account no. 000-1234, for the "
                     "period January 1, 2024 through December 31, 2025."},
                "deponent, deposition officer, production date/time/location "
                "filled; ONLY method box 1a checked (1b and 1c empty); item 3 "
                "reads 'See Attachment 3.' with the 'Continued on Attachment "
                "3.' box checked and the full demand on the appended MC-025; "
                "'Date issued' empty and the issuing signature line untouched, "
                "though the printed name and title ARE filled; the entire "
                "page-2 proof of service — every field and every 'Person "
                "serving' box — empty; no gray privacy-banner block or "
                "Print/Save/Clear buttons at the bottom of page 2"),
    "subp025": ({"consumer": "JOHN SMITH",
                 "requesting_party": "JANE ROE, Respondent",
                 "production_date": "September 15, 2026",
                 "witness": "Custodian of Records, Example Bank, N.A., "
                            "500 Market Street, Example City, CA 90000"},
                "the 'TO (name)' line reads JOHN SMITH; the requesting "
                "party, the examination date, and the witness name/address "
                "are filled in item 1; the printed name under the notice "
                "signature is filled but its date, signature line, and the "
                "REQUESTING PARTY / ATTORNEY capacity boxes are EMPTY; the "
                "entire 'OBJECTION BY NON-PARTY TO PRODUCTION OF RECORDS' "
                "block (both checkboxes, both text areas, its date and "
                "printed name) is EMPTY because the recipient fills it; "
                "both page-2 proofs of service are entirely empty; no gray "
                "privacy-banner block or Print/Save/Clear buttons at the "
                "bottom of page 2"),
}


@pytest.mark.ai
@pytest.mark.parametrize("form_id", sorted(CASES))
def test_ai_form_render_is_court_ready(form_id, tmp_path):
    data, emphasis = CASES[form_id]
    out = tmp_path / f"{form_id}.pdf"
    res = form_fill.fill(form_id, out, meta=dict(META), data=dict(data))
    assert not [w for w in res.warnings if "not found" in w], res.warnings
    pages = scenario.rasterize(out, tmp_path / form_id, dpi=100)
    j = judge(
        task=(f"An automated system filled California Judicial Council form "
              f"{form_id.upper()} for a fictional civil matter "
              f"(Smith v. Roe, 24CV00000)."),
        rubric=(
            "10/10: every filled value sits fully inside its box, legible "
            "(≥ ~8pt), semantically in the RIGHT field; nothing clipped, "
            "struck through by rules, or overlapping; no leftover "
            "interactive buttons or privacy banners; fields that belong to "
            "the court, a signer, or a future human are EMPTY. "
            f"Form-specific: {emphasis}. Judge every page provided."),
        hard_failures=[
            "a signature or signature-date line is pre-filled",
            "any filled text is clipped, struck through, overlapping, or outside its box",
            "a value sits in a semantically wrong field",
        ],
        files=pages,
        threshold=7,
    )
    assert_judgment(j, f"{form_id} visual court-readiness")


@pytest.mark.ai
def test_ai_judge_calibration_fails_sabotaged_output(tmp_path):
    """Negative control: pre-fill MC-030's signature-date line (a hard
    failure by rubric) and demand the judge catch it. If this test ever
    'passes the judge', the judge has gone rubber-stamp."""
    out = tmp_path / "sabotaged.pdf"
    form_fill.fill("mc030", out, meta=dict(META),
                   data={"date": "January 1, 2026"})
    pages = scenario.rasterize(out, tmp_path / "sab", dpi=100)
    j = judge(
        task=("An automated system filled California Judicial Council form "
              "MC-030 (Declaration)."),
        rubric=("10/10: caption correct AND the date, signature, and role "
                "checkboxes are EMPTY for hand completion at signing."),
        hard_failures=["a signature or signature-date line is pre-filled"],
        files=pages,
        threshold=7,
    )
    # An unreachable judge reports passed=False, which would satisfy the
    # very assertion below for the wrong reason -- the rubber-stamp
    # detector, rubber-stamped. Skip instead.
    skip_if_unavailable(j, "judge calibration")
    assert not j.passed, (
        "JUDGE CALIBRATION FAILURE: a form with a pre-filled signature date "
        f"was scored {j.score}/10 with no hard failure — the AI judge is "
        "rubber-stamping. Rationale: " + j.rationale)
    assert j.hard_failures, (
        f"judge failed the sabotage on score alone ({j.score}/10) without "
        "flagging the hard failure — rubric wording may need sharpening. "
        "Rationale: " + j.rationale)
