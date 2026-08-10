"""Parties and counsel."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from prosaic.model.provenance import Fact


class PartyRole(StrEnum):
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    CROSS_COMPLAINANT = "cross_complainant"
    CROSS_DEFENDANT = "cross_defendant"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"


class Address(BaseModel):
    street: str
    city: str
    state: str = Field(pattern=r"^[A-Z]{2}$")
    zip_code: str = Field(pattern=r"^\d{5}(-\d{4})?$")


class Party(BaseModel):
    """A named party to the action.

    The name is a fact, not a string: on ingested matters it is extracted
    from a caption and must be traceable to the page it was read from.
    """

    id: str
    name: Fact[str]
    role: PartyRole
    is_organization: bool = False
    address: Address | None = None
    self_represented: bool = False


class Counsel(BaseModel):
    """An attorney of record. Absent for a self-represented party."""

    id: str
    name: str
    bar_number: str = Field(pattern=r"^\d{1,6}$")
    firm: str = ""
    address: Address
    phone: str = ""
    email: str = ""
    represents: list[str] = Field(min_length=1, description="party ids")
