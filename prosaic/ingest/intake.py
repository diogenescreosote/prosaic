"""Normalization and deduplication of fetched documents.

A fetched document becomes a ``SourceDocument`` with a content hash, and
the hash is the identity: the same PDF arriving from two connectors — or
twice from one — joins the matter once. Original bytes are never altered.
"""

from __future__ import annotations

import hashlib
import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from prosaic.ingest.source import FetchedDocument
from prosaic.model import DocumentKind, Matter, SourceDocument


def _page_count(content: bytes) -> int:
    try:
        return max(len(PdfReader(io.BytesIO(content)).pages), 1)
    except PdfReadError:
        return 1


def normalize(fetched: FetchedDocument) -> SourceDocument:
    """A fetched document as the case model stores it.

    The kind starts as OTHER; classification is a judgment the extraction
    layer or the operator makes later, not something a hash pipeline should
    guess at.
    """
    digest = hashlib.sha256(fetched.content).hexdigest()
    return SourceDocument(
        id=f"doc-{digest[:12]}",
        title=fetched.filename,
        kind=DocumentKind.OTHER,
        sha256=digest,
        page_count=_page_count(fetched.content),
        received=fetched.received,
        origin=fetched.origin,
        location=fetched.location,
    )


def ingest(matter: Matter, fetched: list[FetchedDocument]) -> tuple[Matter, list[SourceDocument]]:
    """Add whatever is new; return the updated matter and the additions."""
    known_hashes = {document.sha256 for document in matter.documents}
    added: list[SourceDocument] = []
    for item in fetched:
        normalized = normalize(item)
        if normalized.sha256 in known_hashes:
            continue
        known_hashes.add(normalized.sha256)
        added.append(normalized)
    if not added:
        return matter, []
    updated = matter.model_copy(update={"documents": [*matter.documents, *added]})
    return Matter.model_validate(updated.model_dump()), added
