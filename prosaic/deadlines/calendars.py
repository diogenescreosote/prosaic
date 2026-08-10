"""Court calendars: the days a clerk's office is closed.

Holiday schedules are data, not code. The computation layer takes a
``CourtCalendar`` argument, and a calendar can be built from the packaged
statewide California data or from any caller-supplied schedule. A calendar
knows its coverage window and refuses to answer outside it: silently treating
an unloaded year as holiday-free would compute a confident, wrong deadline.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from importlib import resources


class CalendarCoverageError(ValueError):
    """A computation touched a date outside the loaded holiday data."""


@dataclass(frozen=True, slots=True)
class CourtCalendar:
    """An immutable set of court holidays with an explicit coverage window."""

    first_day: datetime.date
    last_day: datetime.date
    holidays: frozenset[datetime.date]

    def __post_init__(self) -> None:
        if self.first_day > self.last_day:
            raise ValueError(f"coverage window is inverted: {self.first_day} > {self.last_day}")
        stray = {day for day in self.holidays if not self.first_day <= day <= self.last_day}
        if stray:
            raise ValueError(f"holidays outside the coverage window: {sorted(stray)}")

    def _require_covered(self, day: datetime.date) -> None:
        if not self.first_day <= day <= self.last_day:
            raise CalendarCoverageError(
                f"{day} is outside this calendar's coverage "
                f"({self.first_day} to {self.last_day}); load holiday data for that period"
            )

    def is_holiday(self, day: datetime.date) -> bool:
        self._require_covered(day)
        return day in self.holidays

    def is_court_day(self, day: datetime.date) -> bool:
        """True when the court is open: a weekday that is not a holiday."""
        self._require_covered(day)
        return day.weekday() < 5 and day not in self.holidays


def california_court_calendar() -> CourtCalendar:
    """The packaged statewide California superior court holiday calendar.

    Covers the window stated in the packaged data file; computations that
    reach beyond it raise ``CalendarCoverageError``.
    """
    raw = resources.files("prosaic.deadlines").joinpath("data/ca_court_holidays.json")
    payload = json.loads(raw.read_text(encoding="utf-8"))
    return CourtCalendar(
        first_day=datetime.date.fromisoformat(payload["coverage"]["first_day"]),
        last_day=datetime.date.fromisoformat(payload["coverage"]["last_day"]),
        holidays=frozenset(
            datetime.date.fromisoformat(entry["date"]) for entry in payload["holidays"]
        ),
    )
