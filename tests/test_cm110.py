"""Golden-file and validation tests for the CM-110 Case Management Statement.

The statement is built from the shared synthetic matter, compared against
its committed golden values, filled into the official blank, and read back
out of the produced PDF, mirroring the harness in ``test_civil_forms``.
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
from prosaic.packs.civil import cm010, cm110
from tests.synthetic import doe_v_roe

GOLDEN = Path(__file__).parent / "golden" / "cm110.json"

STATEMENT = cm110.CaseManagementContext(
    filer_party_id="doe",
    amount=cm010.AmountDemanded.UNLIMITED,
    case_description=(
        "Breach of a written services agreement. Plaintiff seeks contract "
        "damages of $80,000 plus prejudgment interest."
    ),
    signed_on=datetime.date(2026, 3, 2),
    hearing=datetime.datetime(2026, 6, 15, 9, 0),
    department="99",
    complaint_filed=datetime.date(2026, 1, 12),
    all_parties_served=True,
    requests_jury_trial=True,
    willing_to_mediate=True,
)


def _check_against_golden_and_pdf(values: dict[str, str | bool]) -> None:
    golden = json.loads(GOLDEN.read_text())
    assert values == golden

    blank = resources.files("prosaic.packs.civil").joinpath("blanks/cm110.pdf").read_bytes()
    produced = read_filled_values(fill_acroform(blank, values))
    for name, value in values.items():
        assert produced[name] == value, name


@pytest.fixture
def matter() -> Matter:
    return doe_v_roe()


def test_cm110_statement_renders_from_the_case_model(matter: Matter) -> None:
    _check_against_golden_and_pdf(cm110.build_values(matter, STATEMENT))


def test_statement_defaults_leave_the_optional_items_blank(matter: Matter) -> None:
    values = cm110.build_values(
        matter,
        cm110.CaseManagementContext(
            filer_party_id="roe",
            amount=cm010.AmountDemanded.LIMITED,
            case_description="Defense of a contract claim arising from a services agreement.",
            signed_on=datetime.date(2026, 3, 4),
        ),
    )
    caption = "CM-110[0].Page1[0].P1Caption[0]"
    assert values[f"{caption}.AttyPartyInfo[0].Name[0]"] == "Sam Stone"
    assert values[f"{caption}.AttyPartyInfo[0].AttyBarNo[0]"] == "123456"
    assert values["CM-110[0].Page5[0].Sign[0].SigName1[0]"] == "Sam Stone"
    assert values[f"{caption}.FormTitle[0].limit12[1]"] == "/2"
    assert values["CM-110[0].Page2[0].List5[0].item5[0].jurytrial1[1]"] == "/2"
    assert values["CM-110[0].Page1[0].Note[0].Date1[0]"] == ""
    assert values["CM-110[0].Page1[0].Note[0].Time1[0]"] == ""
    assert values["CM-110[0].Page1[0].List2[0].Lia[0].Date3[0]"] == ""
    assert "CM-110[0].Page1[0].List3[0].Lia[0].limitedee[0]" not in values
    assert not any("Page3[0]" in name for name in values)


def test_statement_requires_a_case_description(matter: Matter) -> None:
    blank_description = cm110.CaseManagementContext(
        filer_party_id="doe",
        amount=cm010.AmountDemanded.UNLIMITED,
        case_description="  ",
        signed_on=datetime.date(2026, 3, 2),
    )
    with pytest.raises(FormValidationError, match="description of the case"):
        cm110.build_values(matter, blank_description)


def test_statement_requires_a_case_number(matter: Matter) -> None:
    unfiled = matter.model_copy(update={"case_number": None})
    with pytest.raises(FormValidationError, match="no case number"):
        cm110.build_values(unfiled, STATEMENT)
