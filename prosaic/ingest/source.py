"""The connector protocol.

A record source yields fetched documents: raw bytes plus enough metadata
to locate the original again. Everything downstream — hashing,
deduplication, the case model — is connector-agnostic, so adding a
source means implementing one method.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    """One document as it arrived, before normalization."""

    origin: str
    location: str
    filename: str
    content: bytes
    received: datetime.date | None


class RecordSource(Protocol):
    """Anything that can produce documents for a matter."""

    @property
    def name(self) -> str: ...

    def fetch(self) -> Iterator[FetchedDocument]: ...
