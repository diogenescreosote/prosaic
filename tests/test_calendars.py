"""Court calendar behavior and packaged holiday data integrity."""

from __future__ import annotations

import datetime
from collections import Counter

import pytest

from prosaic.deadlines import (
    CalendarCoverageError,
    CourtCalendar,
    CourtDays,
    add_court_days,
    california_court_calendar,
)

CAL = california_court_calendar()


def test_weekday_is_court_day() -> None:
    assert CAL.is_court_day(datetime.date(2026, 8, 10))  # a plain Monday


def test_weekend_is_not_court_day() -> None:
    assert not CAL.is_court_day(datetime.date(2026, 8, 8))
    assert not CAL.is_court_day(datetime.date(2026, 8, 9))


def test_observed_holiday_is_not_court_day() -> None:
    # Independence Day 2026 falls on a Saturday; courts observe Friday July 3.
    assert CAL.is_holiday(datetime.date(2026, 7, 3))
    assert not CAL.is_court_day(datetime.date(2026, 7, 3))
    assert CAL.is_court_day(datetime.date(2026, 7, 6))


def test_dates_outside_coverage_raise_rather_than_answer() -> None:
    with pytest.raises(CalendarCoverageError):
        CAL.is_court_day(datetime.date(2024, 12, 31))
    with pytest.raises(CalendarCoverageError):
        add_court_days(datetime.date(2028, 12, 20), CourtDays(10), CAL)


def test_calendar_rejects_holidays_outside_its_window() -> None:
    with pytest.raises(ValueError, match="outside the coverage window"):
        CourtCalendar(
            first_day=datetime.date(2026, 1, 1),
            last_day=datetime.date(2026, 12, 31),
            holidays=frozenset({datetime.date(2027, 1, 1)}),
        )


def test_calendar_rejects_inverted_window() -> None:
    with pytest.raises(ValueError, match="inverted"):
        CourtCalendar(
            first_day=datetime.date(2027, 1, 1),
            last_day=datetime.date(2026, 1, 1),
            holidays=frozenset(),
        )


def test_packaged_holidays_are_weekdays() -> None:
    # Observed dates always fall Monday through Friday; a weekend date in the
    # data file would be a transcription error.
    weekend = [day for day in CAL.holidays if day.weekday() >= 5]
    assert weekend == []


def test_packaged_holiday_counts_per_year() -> None:
    # 14 statewide holidays a normal year; New Year's Day 2028 is observed
    # Friday, December 31, 2027, moving one into 2027's count.
    counts = Counter(day.year for day in CAL.holidays)
    assert counts == {2025: 14, 2026: 14, 2027: 15, 2028: 13}
