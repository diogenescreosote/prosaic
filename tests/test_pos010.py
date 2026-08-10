"""Golden-file and validation tests for the POS-010 proof of service.

The form is built from the shared synthetic matter, compared against its
committed golden values, filled into the official blank, and read back
out of the produced PDF, mirroring the other civil-form suites.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from importlib import resources
from pathlib import Path

import pytest

from prosaic.forms.acroform import fill_acroform, read_filled_values
from prosaic.forms.pack import FormValidationError
from prosaic.model import Address, Matter
from prosaic.packs.civil import pos010
from tests.synthetic import doe_v_roe

GOLDEN_DIR = Path(__file__).parent / "golden"

PROOF_OF_SERVICE = pos010.ProofOfServiceContext(
    filer_party_id="doe",
    served_party_id="roe",
    documents_served=("Summons", "Complaint", "Civil Case Cover Sheet"),
    service_address=Address(street="800 Freight Way", city="Oakland", state="CA", zip_code="94607"),
    served_at=datetime.datetime(2026, 1, 20, 10, 30),
    notice_basis=pos010.NoticeBasis.ON_BEHALF_OF_ENTITY,
    entity_ccp_section=pos010.EntityServiceSection.CORPORATION_416_10,
    server_name="Pat Process",
    server_address=Address(street="99 Courier Court", city="Oakland", state="CA", zip_code="94612"),
    server_phone="(510) 555-0177",
    fee_for_service="40.00",
    signed_on=datetime.date(2026, 1, 21),
)

_LIST6 = "POS-010[0].Page2[0].List6[0]"


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


def test_pos010_proof_of_service_renders_from_the_case_model(matter: Matter) -> None:
    _check_against_golden_and_pdf("pos010", pos010.build_values(matter, PROOF_OF_SERVICE))


def test_pos010_marks_an_individual_defendant_notice(matter: Matter) -> None:
    individual = dataclasses.replace(
        PROOF_OF_SERVICE, notice_basis=pos010.NoticeBasis.INDIVIDUAL, entity_ccp_section=None
    )
    values = pos010.build_values(matter, individual)
    assert values[f"{_LIST6}.Lia[0].CheckBox40[0]"] == "/1"
    assert f"{_LIST6}.Lid[0].CheckBox45[0]" not in values


def test_pos010_fictitious_name_flows_to_items_3b_and_6b(matter: Matter) -> None:
    fictitious = dataclasses.replace(
        PROOF_OF_SERVICE,
        notice_basis=pos010.NoticeBasis.FICTITIOUS_NAME,
        entity_ccp_section=None,
        fictitious_name="Roe Trucking",
    )
    values = pos010.build_values(matter, fictitious)
    assert values["POS-010[0].Page1[0].List3[0].Lib[0].limited2[0]"] == "/1"
    assert values["POS-010[0].Page1[0].List3[0].Lib[0].TextField16[0]"] == "Roe Trucking"
    assert values[f"{_LIST6}.Lib[0].CheckBox41[0]"] == "/2"
    assert values[f"{_LIST6}.Lib[0].TextField40[0]"] == "Roe Trucking"


def test_pos010_spells_out_an_other_ccp_section(matter: Matter) -> None:
    other = dataclasses.replace(
        PROOF_OF_SERVICE,
        entity_ccp_section=pos010.EntityServiceSection.OTHER,
        other_ccp_section="Code Civ. Proc., § 415.95",
    )
    values = pos010.build_values(matter, other)
    assert values[f"{_LIST6}.Lid[0].CheckBox65[0]"] == "/1"
    assert values[f"{_LIST6}.Lid[0].other[0]"] == "Code Civ. Proc., § 415.95"


def test_pos010_requires_a_case_number(matter: Matter) -> None:
    unfiled = matter.model_copy(update={"case_number": None})
    with pytest.raises(FormValidationError, match="no case number"):
        pos010.build_values(unfiled, PROOF_OF_SERVICE)


def test_pos010_rejects_a_plaintiff_as_the_served_party(matter: Matter) -> None:
    on_plaintiff = dataclasses.replace(PROOF_OF_SERVICE, served_party_id="doe")
    with pytest.raises(FormValidationError, match="proved on a defendant"):
        pos010.build_values(matter, on_plaintiff)


def test_pos010_requires_the_documents_served(matter: Matter) -> None:
    undocumented = dataclasses.replace(PROOF_OF_SERVICE, documents_served=())
    with pytest.raises(FormValidationError, match="documents served"):
        pos010.build_values(matter, undocumented)


def test_pos010_rejects_a_registered_process_server(matter: Matter) -> None:
    registered = dataclasses.replace(PROOF_OF_SERVICE, server_is_registered=True)
    with pytest.raises(FormValidationError, match="registered process servers are not supported"):
        pos010.build_values(matter, registered)


def test_pos010_fictitious_name_service_requires_the_name(matter: Matter) -> None:
    unnamed = dataclasses.replace(
        PROOF_OF_SERVICE, notice_basis=pos010.NoticeBasis.FICTITIOUS_NAME, entity_ccp_section=None
    )
    with pytest.raises(FormValidationError, match="fictitious name"):
        pos010.build_values(matter, unnamed)


def test_pos010_entity_service_requires_a_ccp_section(matter: Matter) -> None:
    sectionless = dataclasses.replace(PROOF_OF_SERVICE, entity_ccp_section=None)
    with pytest.raises(FormValidationError, match="CCP section"):
        pos010.build_values(matter, sectionless)


def test_pos010_other_ccp_section_requires_the_section_text(matter: Matter) -> None:
    unspecified = dataclasses.replace(
        PROOF_OF_SERVICE, entity_ccp_section=pos010.EntityServiceSection.OTHER
    )
    with pytest.raises(FormValidationError, match="spells out the section"):
        pos010.build_values(matter, unspecified)
