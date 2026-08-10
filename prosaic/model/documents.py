"""Source documents, docket entries, service events, and exhibits."""

from __future__ import annotations

import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from prosaic.deadlines.types import ServiceMethod
from prosaic.model.provenance import Fact


class DocumentKind(StrEnum):
    PLEADING = "pleading"
    MOTION = "motion"
    ORDER = "order"
    NOTICE = "notice"
    PROOF_OF_SERVICE = "proof_of_service"
    DISCOVERY = "discovery"
    CORRESPONDENCE = "correspondence"
    OTHER = "other"


class SourceDocument(BaseModel):
    """One received document, exactly as it arrived.

    ``sha256`` is the hash of the received bytes and doubles as the
    deduplication key across connectors: the same PDF arriving by mail
    and by download is one document.
    """

    id: str
    title: str
    kind: DocumentKind
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    received: datetime.date | None = None
    origin: str = Field(description="name of the connector that ingested it")
    location: str = Field(description="connector-specific locator: path, message id, record id")


class DocketEntry(BaseModel):
    """One line of the court's register of actions."""

    date: Fact[datetime.date]
    description: str
    filed_by: str | None = Field(default=None, description="party id")
    document_id: str | None = None


class ServiceEvent(BaseModel):
    """Service of one document on one party.

    The date and method drive deadline computation, so both are facts with
    provenance — a wrong service date silently shifts every downstream
    deadline.
    """

    document_id: str
    served_on: str = Field(description="party id")
    date: Fact[datetime.date]
    method: ServiceMethod


class Exhibit(BaseModel):
    """A labeled exhibit drawn from a source document."""

    label: str = Field(pattern=r"^[A-Z]{1,2}$|^\d{1,3}$")
    description: str
    document_id: str
    first_page: int = Field(default=1, ge=1)
    last_page: int | None = Field(default=None, ge=1)
