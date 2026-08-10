"""The structured case model.

Everything downstream — deadline callers, form renderers, the agent's tools —
reads from these types. Facts extracted from records carry provenance to the
source document and page; see ``prosaic.model.provenance``.
"""

from prosaic.model.court import Court
from prosaic.model.documents import (
    DocketEntry,
    DocumentKind,
    Exhibit,
    ServiceEvent,
    SourceDocument,
)
from prosaic.model.matter import Matter
from prosaic.model.parties import Address, Counsel, Party, PartyRole
from prosaic.model.provenance import DocumentProvenance, Fact, Provenance, UserProvenance

__all__ = [
    "Address",
    "Counsel",
    "Court",
    "DocketEntry",
    "DocumentKind",
    "DocumentProvenance",
    "Exhibit",
    "Fact",
    "Matter",
    "Party",
    "PartyRole",
    "Provenance",
    "ServiceEvent",
    "SourceDocument",
    "UserProvenance",
]
