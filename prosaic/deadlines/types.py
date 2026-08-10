"""Foundation types for date computation.

Court days and calendar days obey different arithmetic — a court-day count
skips weekends and holidays at every step, a calendar-day count only rolls
the endpoint — and California rules mix the two in a single computation
(CCP § 1005(b) measures notice in court days but service extensions in
calendar days). Making them distinct types forces every rule to say which
unit it means.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class CalendarDays:
    """A span counted in calendar days; weekends and holidays count."""

    count: int

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError(
                f"day counts are non-negative; direction belongs to the operation, got {self.count}"
            )


@dataclass(frozen=True, slots=True)
class CourtDays:
    """A span counted in court days; weekends and court holidays are skipped."""

    count: int

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError(
                f"day counts are non-negative; direction belongs to the operation, got {self.count}"
            )


class ServiceMethod(StrEnum):
    """How a document was served, as it bears on deadline extensions.

    The mail categories are split by destination because CCP § 1013(a)
    extends by 5, 10, or 20 calendar days depending on where the mail goes.
    """

    PERSONAL = "personal"
    MAIL_WITHIN_CALIFORNIA = "mail_within_california"
    MAIL_OUTSIDE_CALIFORNIA = "mail_outside_california"
    MAIL_OUTSIDE_UNITED_STATES = "mail_outside_united_states"
    EXPRESS_OVERNIGHT = "express_overnight"
    ELECTRONIC = "electronic"
    FAX = "fax"
