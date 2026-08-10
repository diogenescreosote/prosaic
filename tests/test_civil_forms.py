"""Golden-file and validation tests for the civil pack forms.

Each implemented form is built from the shared synthetic matter, compared
against its committed golden values, filled into the official blank, and
read back out of the produced PDF. The goldens pin the exact field names
and values; the read-back proves the values actually landed in the PDF.
"""

from __future__ import annotations

import datetime
import json
from importlib import resources
from pathlib import Path

import pytest

from prosaic.forms.acroform import fill_acroform, read_filled_values
from prosaic.forms.pack import FormValidationError
from prosaic.model import Matter
from prosaic.packs.civil import cm010, mc030, mc031, sum100
from tests.synthetic import doe_v_roe

GOLDEN_DIR = Path(__file__).parent / "golden"

DECLARATION = mc030.DeclarationContext(
    declarant_party_id="doe",
    body=(
        "1. I am the plaintiff in this action.\n"
        "2. On January 5, 2026, I signed the services agreement attached as Exhibit A.\n"
        "3. Roe Logistics did not perform."
    ),
    signed_on=datetime.date(2026, 3, 2),
)

COVER_SHEET = cm010.CoverSheetContext(
    filer_party_id="doe",
    case_type=cm010.CaseType.BREACH_OF_CONTRACT_WARRANTY,
    amount=cm010.AmountDemanded.UNLIMITED,
    remedies=frozenset({cm010.Remedy.MONETARY}),
    causes_of_action=2,
    is_class_action=False,
    signed_on=datetime.date(2026, 1, 12),
)


def _blank(stem: str) -> bytes:
    return resources.files("prosaic.packs.civil").joinpath(f"blanks/{stem}.pdf").read_bytes()


def _check_against_golden_and_pdf(stem: str, values: dict[str, str | bool]) -> None:
    golden = json.loads((GOLDEN_DIR / f"{stem}.json").read_text())
    assert values == golden

    produced = read_filled_values(fill_acroform(_blank(stem), values))
    for name, value in values.items():
        if value is True:
            assert produced[name] not in ("", "/Off"), name
        else:
            assert produced[name] == value, name


@pytest.fixture
def matter() -> Matter:
    return doe_v_roe()


def test_mc030_declaration_renders_from_the_case_model(matter: Matter) -> None:
    _check_against_golden_and_pdf("mc030", mc030.build_values(matter, DECLARATION))


def test_mc031_attached_declaration_renders_from_the_case_model(matter: Matter) -> None:
    _check_against_golden_and_pdf("mc031", mc031.build_values(matter, DECLARATION))


def test_sum100_summons_renders_from_the_case_model(matter: Matter) -> None:
    values = sum100.build_values(matter, sum100.SummonsContext(filer_party_id="doe"))
    _check_against_golden_and_pdf("sum100", values)


def test_cm010_cover_sheet_renders_from_the_case_model(matter: Matter) -> None:
    _check_against_golden_and_pdf("cm010", cm010.build_values(matter, COVER_SHEET))


def test_declaration_requires_a_body(matter: Matter) -> None:
    empty = mc030.DeclarationContext(
        declarant_party_id="doe", body="  ", signed_on=datetime.date(2026, 3, 2)
    )
    with pytest.raises(FormValidationError, match="body is empty"):
        mc030.build_values(matter, empty)


def test_declaration_requires_a_case_number(matter: Matter) -> None:
    unfiled = matter.model_copy(update={"case_number": None})
    with pytest.raises(FormValidationError, match="no case number"):
        mc031.build_values(unfiled, DECLARATION)


def test_summons_rejects_a_defendant_filer(matter: Matter) -> None:
    with pytest.raises(FormValidationError, match="issued for a plaintiff"):
        sum100.build_values(matter, sum100.SummonsContext(filer_party_id="roe"))


def test_cover_sheet_requires_a_cause_of_action(matter: Matter) -> None:
    broken = cm010.CoverSheetContext(
        filer_party_id="doe",
        case_type=cm010.CaseType.FRAUD,
        amount=cm010.AmountDemanded.LIMITED,
        remedies=frozenset({cm010.Remedy.MONETARY}),
        causes_of_action=0,
        is_class_action=False,
        signed_on=datetime.date(2026, 1, 12),
    )
    with pytest.raises(FormValidationError, match="cause of action"):
        cm010.build_values(matter, broken)


def test_cover_sheet_supports_counsel_caption(matter: Matter) -> None:
    values = cm010.build_values(
        matter,
        cm010.CoverSheetContext(
            filer_party_id="roe",
            case_type=cm010.CaseType.OTHER_CONTRACT,
            amount=cm010.AmountDemanded.LIMITED,
            remedies=frozenset({cm010.Remedy.NONMONETARY}),
            causes_of_action=1,
            is_class_action=False,
            signed_on=datetime.date(2026, 2, 20),
        ),
    )
    assert values["CM-010[0].Page1[0].P1Caption[0].AttyPartyInfo[0].Name[0]"] == "Sam Stone"
    assert values["CM-010[0].Page1[0].P1Caption[0].AttyPartyInfo[0].AttyBarNo[0]"] == "123456"
    assert (
        values["CM-010[0].Page1[0].P1Caption[0].AttyPartyInfo[0].AttyFor[0]"]
        == "Defendant Roe Logistics, Inc."
    )
