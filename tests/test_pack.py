"""The civil pack registry: enumeration, rendering, and context checking."""

from __future__ import annotations

import datetime

import pytest

from prosaic.forms.pack import FormContextError
from prosaic.packs.civil import CIVIL_PACK
from prosaic.packs.civil.mc030 import DeclarationContext
from tests.synthetic import doe_v_roe

DECLARATION = DeclarationContext(
    declarant_party_id="doe",
    body="1. I am the plaintiff in this action.",
    signed_on=datetime.date(2026, 3, 2),
)


def test_pack_lists_the_six_forms() -> None:
    assert [form.number for form in CIVIL_PACK.forms] == [
        "CM-010",
        "CM-110",
        "SUM-100",
        "POS-010",
        "MC-030",
        "MC-031",
    ]


def test_pack_renders_a_form_end_to_end() -> None:
    filled = CIVIL_PACK.form("MC-030").fill(doe_v_roe(), DECLARATION)
    assert filled.pdf.startswith(b"%PDF")
    assert filled.values["FillText18"] == "Jane Doe"


def test_unknown_form_number_raises() -> None:
    with pytest.raises(KeyError):
        CIVIL_PACK.form("MC-999")


def test_wrong_context_type_is_rejected_by_name() -> None:
    with pytest.raises(FormContextError, match="SUM-100 takes a SummonsContext"):
        CIVIL_PACK.form("SUM-100").fill(doe_v_roe(), DECLARATION)
