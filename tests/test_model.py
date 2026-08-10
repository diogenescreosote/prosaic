"""Case model construction, referential integrity, and serialization."""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from prosaic.deadlines import ServiceMethod
from prosaic.model import (
    DocumentProvenance,
    Fact,
    Matter,
    ServiceEvent,
    UserProvenance,
)
from tests.synthetic import doe_v_roe


def test_synthetic_matter_validates() -> None:
    matter = doe_v_roe()
    assert matter.party("doe").self_represented
    assert matter.document("doc-answer").page_count == 6


def test_matter_round_trips_through_json() -> None:
    matter = doe_v_roe()
    assert Matter.model_validate_json(matter.model_dump_json()) == matter


def test_fact_provenance_is_a_discriminated_union() -> None:
    from_page = Fact.from_document("26CV012345", document_id="doc-complaint", page=1)
    from_user = Fact.from_user("26CV012345")
    assert isinstance(from_page.provenance, DocumentProvenance)
    assert isinstance(from_user.provenance, UserProvenance)
    revived = Fact[str].model_validate_json(from_page.model_dump_json())
    assert isinstance(revived.provenance, DocumentProvenance)
    assert revived.provenance.page == 1


def test_document_provenance_rejects_page_zero() -> None:
    with pytest.raises(ValidationError):
        Fact.from_document("anything", document_id="doc-complaint", page=0)


def test_duplicate_party_ids_rejected() -> None:
    matter = doe_v_roe()
    duplicated = matter.model_dump()
    duplicated["parties"].append(duplicated["parties"][0])
    with pytest.raises(ValidationError, match="duplicate party ids"):
        Matter.model_validate(duplicated)


def test_service_event_must_reference_known_document() -> None:
    matter = doe_v_roe()
    stray = ServiceEvent(
        document_id="doc-nonexistent",
        served_on="doe",
        date=Fact.from_user(datetime.date(2026, 3, 1)),
        method=ServiceMethod.PERSONAL,
    )
    with pytest.raises(ValidationError, match="unknown document"):
        Matter.model_validate({**matter.model_dump(), "service_events": [stray.model_dump()]})


def test_counsel_must_represent_known_party() -> None:
    matter = doe_v_roe()
    broken = matter.model_dump()
    broken["counsel"][0]["represents"] = ["nobody"]
    with pytest.raises(ValidationError, match="unknown parties"):
        Matter.model_validate(broken)


def test_exhibit_page_range_must_be_ordered() -> None:
    matter = doe_v_roe()
    broken = matter.model_dump()
    broken["exhibits"][0]["first_page"] = 9
    broken["exhibits"][0]["last_page"] = 5
    with pytest.raises(ValidationError, match="page range is inverted"):
        Matter.model_validate(broken)


def test_service_event_must_reference_known_party() -> None:
    matter = doe_v_roe()
    broken = matter.model_dump()
    broken["service_events"][0]["served_on"] = "nobody"
    with pytest.raises(ValidationError, match="unknown party"):
        Matter.model_validate(broken)


def test_docket_entry_references_are_checked() -> None:
    matter = doe_v_roe()
    broken = matter.model_dump()
    broken["docket"][0]["document_id"] = "doc-nonexistent"
    with pytest.raises(ValidationError, match="unknown document"):
        Matter.model_validate(broken)
    broken = matter.model_dump()
    broken["docket"][0]["filed_by"] = "nobody"
    with pytest.raises(ValidationError, match="unknown party"):
        Matter.model_validate(broken)


def test_exhibit_must_reference_known_document() -> None:
    matter = doe_v_roe()
    broken = matter.model_dump()
    broken["exhibits"][0]["document_id"] = "doc-nonexistent"
    with pytest.raises(ValidationError, match="unknown document"):
        Matter.model_validate(broken)


def test_duplicate_document_ids_rejected() -> None:
    matter = doe_v_roe()
    broken = matter.model_dump()
    broken["documents"].append(broken["documents"][0])
    with pytest.raises(ValidationError, match="duplicate document ids"):
        Matter.model_validate(broken)


def test_lookups_raise_key_error_for_unknown_ids() -> None:
    matter = doe_v_roe()
    with pytest.raises(KeyError):
        matter.party("nobody")
    with pytest.raises(KeyError):
        matter.document("doc-nonexistent")
