"""The court a matter is pending in."""

from __future__ import annotations

from pydantic import BaseModel

from prosaic.model.parties import Address


class Court(BaseModel):
    """A superior court location, as it appears in a caption block."""

    county: str
    branch: str = ""
    address: Address
    department: str = ""
