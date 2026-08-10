"""Provenance for extracted facts.

Facts enter the case model from two places: a page of a source document
(usually placed there by the extraction layer) or an assertion by the user.
Provenance is recorded on each fact, not on the containers around it, so a
renderer or reviewer can trace any single value on a filing back to the page
it came from — or see that it has no page and needs human confirmation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class DocumentProvenance(BaseModel):
    """The fact was read off a specific page of a source document."""

    kind: Literal["document"] = "document"
    document_id: str
    page: int = Field(ge=1, description="1-indexed page within the source document")


class UserProvenance(BaseModel):
    """The fact was asserted directly by the operator of the tool."""

    kind: Literal["user"] = "user"
    note: str = ""


Provenance = Annotated[DocumentProvenance | UserProvenance, Field(discriminator="kind")]


class Fact[T](BaseModel):
    """A value plus where it came from."""

    value: T
    provenance: Provenance

    @classmethod
    def from_user(cls, value: T, note: str = "") -> Fact[T]:
        return cls(value=value, provenance=UserProvenance(note=note))

    @classmethod
    def from_document(cls, value: T, document_id: str, page: int) -> Fact[T]:
        return cls(value=value, provenance=DocumentProvenance(document_id=document_id, page=page))
