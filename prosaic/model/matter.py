"""The matter aggregate."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from prosaic.model.court import Court
from prosaic.model.documents import DocketEntry, Exhibit, ServiceEvent, SourceDocument
from prosaic.model.parties import Counsel, Party
from prosaic.model.provenance import Fact


class Matter(BaseModel):
    """One case: everything the tool knows about it, with referential integrity.

    Cross-references between the collections (service events to documents and
    parties, counsel to parties, exhibits to documents) are validated on
    construction, so any ``Matter`` that exists is internally consistent.
    """

    title: str
    case_number: Fact[str] | None = None
    court: Court
    parties: list[Party]
    counsel: list[Counsel] = []
    documents: list[SourceDocument] = []
    docket: list[DocketEntry] = []
    service_events: list[ServiceEvent] = []
    exhibits: list[Exhibit] = []

    @model_validator(mode="after")
    def _check_references(self) -> Matter:
        party_ids = {party.id for party in self.parties}
        if len(party_ids) != len(self.parties):
            raise ValueError("duplicate party ids")
        document_ids = {document.id for document in self.documents}
        if len(document_ids) != len(self.documents):
            raise ValueError("duplicate document ids")

        for attorney in self.counsel:
            missing = set(attorney.represents) - party_ids
            if missing:
                raise ValueError(
                    f"counsel {attorney.id} represents unknown parties: {sorted(missing)}"
                )
        for event in self.service_events:
            if event.document_id not in document_ids:
                raise ValueError(f"service event references unknown document {event.document_id}")
            if event.served_on not in party_ids:
                raise ValueError(f"service event references unknown party {event.served_on}")
        for entry in self.docket:
            if entry.document_id is not None and entry.document_id not in document_ids:
                raise ValueError(f"docket entry references unknown document {entry.document_id}")
            if entry.filed_by is not None and entry.filed_by not in party_ids:
                raise ValueError(f"docket entry references unknown party {entry.filed_by}")
        for exhibit in self.exhibits:
            if exhibit.document_id not in document_ids:
                raise ValueError(
                    f"exhibit {exhibit.label} references unknown document {exhibit.document_id}"
                )
            if exhibit.last_page is not None and exhibit.last_page < exhibit.first_page:
                raise ValueError(f"exhibit {exhibit.label} page range is inverted")
        return self

    def party(self, party_id: str) -> Party:
        for candidate in self.parties:
            if candidate.id == party_id:
                return candidate
        raise KeyError(party_id)

    def document(self, document_id: str) -> SourceDocument:
        for candidate in self.documents:
            if candidate.id == document_id:
                return candidate
        raise KeyError(document_id)
