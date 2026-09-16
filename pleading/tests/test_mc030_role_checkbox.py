"""MC-030's role checkbox row: Attorney for/Plaintiff/Petitioner/
Defendant/Respondent/Other.

Left entirely blank, the declarant checks the right one by hand at
signing -- that stays valid (a party or attorney declaring in their
own case, where the role could plausibly go either way at signing
time). But once a source starts setting boxes in the row -- the
third-party-declarant case, where the role is fixed and knowable at
drafting time -- exactly one of Plaintiff/Petitioner/Defendant/
Respondent/Other must be checked, and Other requires
other_role_specify to say what the role is. This file pins that
constraint (``checkbox_groups:`` in the mc030 descriptor).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))

import form_fill  # noqa: E402

from pypdf import PdfReader  # noqa: E402


def test_all_boxes_blank_is_still_valid(tmp_path):
    """The historic default: hand-check at signing."""
    out = tmp_path / "d.pdf"
    res = form_fill.fill("mc030", out, meta={}, data={})
    assert not any("checkbox" in w for w in res.warnings)
    assert out.exists()


def test_exactly_one_role_box_succeeds(tmp_path):
    out = tmp_path / "d.pdf"
    form_fill.fill(
        "mc030", out, meta={"forms": {"mc030": {
            "role_other": True,
            "other_role_specify": "Family Therapist",
        }}},
    )
    reader = PdfReader(str(out))
    text = reader.pages[0].extract_text()
    assert "Family Therapist" in text


def test_two_role_boxes_raises(tmp_path):
    out = tmp_path / "d.pdf"
    with pytest.raises(ValueError, match="exactly one"):
        form_fill.fill(
            "mc030", out, meta={"forms": {"mc030": {
                "role_respondent": True,
                "role_other": True,
                "other_role_specify": "Family Therapist",
            }}},
        )


def test_other_without_specify_text_raises(tmp_path):
    out = tmp_path / "d.pdf"
    with pytest.raises(ValueError, match="other_role_specify"):
        form_fill.fill(
            "mc030", out, meta={"forms": {"mc030": {"role_other": True}}},
        )


def test_role_attorney_is_independent_of_the_group(tmp_path):
    """A party's own attorney may also be, say, the Respondent."""
    out = tmp_path / "d.pdf"
    form_fill.fill(
        "mc030", out, meta={"forms": {"mc030": {
            "role_attorney": True,
            "role_respondent": True,
        }}},
    )
    assert out.exists()
