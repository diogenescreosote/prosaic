"""Day arithmetic under CCP §§ 12 through 12c.

CCP § 12 computes a period by excluding the first day and including the
last; § 12a extends a period whose last day is a weekend or holiday to the
next court day; § 12c measures backward from a hearing in court days,
excluding the hearing date itself.

Forward periods roll forward (§ 12a gives more time). Periods measured
backward from a hearing roll backward: rolling forward would land the act
inside the protected notice window, so the safe day is the prior court day.
"""

from __future__ import annotations

import datetime

from prosaic.deadlines.calendars import CourtCalendar
from prosaic.deadlines.types import CalendarDays, CourtDays

_ONE_DAY = datetime.timedelta(days=1)


def next_court_day(day: datetime.date, calendar: CourtCalendar) -> datetime.date:
    """The first court day strictly after ``day``."""
    candidate = day + _ONE_DAY
    while not calendar.is_court_day(candidate):
        candidate += _ONE_DAY
    return candidate


def previous_court_day(day: datetime.date, calendar: CourtCalendar) -> datetime.date:
    """The last court day strictly before ``day``."""
    candidate = day - _ONE_DAY
    while not calendar.is_court_day(candidate):
        candidate -= _ONE_DAY
    return candidate


def roll_forward(day: datetime.date, calendar: CourtCalendar) -> datetime.date:
    """``day`` itself when the court is open, else the next court day (CCP § 12a)."""
    return day if calendar.is_court_day(day) else next_court_day(day, calendar)


def roll_backward(day: datetime.date, calendar: CourtCalendar) -> datetime.date:
    """``day`` itself when the court is open, else the previous court day."""
    return day if calendar.is_court_day(day) else previous_court_day(day, calendar)


def add_calendar_days(trigger: datetime.date, span: CalendarDays) -> datetime.date:
    """CCP § 12 count forward: the trigger day is excluded, the last day included.

    Returns the raw last day; apply ``roll_forward`` where § 12a governs.
    """
    return trigger + datetime.timedelta(days=span.count)


def subtract_calendar_days(reference: datetime.date, span: CalendarDays) -> datetime.date:
    """Count backward in calendar days, excluding the reference day."""
    return reference - datetime.timedelta(days=span.count)


def add_court_days(start: datetime.date, span: CourtDays, calendar: CourtCalendar) -> datetime.date:
    """Count forward ``span`` court days, excluding ``start`` (CCP § 12)."""
    day = start
    for _ in range(span.count):
        day = next_court_day(day, calendar)
    return day


def subtract_court_days(
    reference: datetime.date, span: CourtDays, calendar: CourtCalendar
) -> datetime.date:
    """Count backward ``span`` court days, excluding ``reference`` (CCP § 12c)."""
    day = reference
    for _ in range(span.count):
        day = previous_court_day(day, calendar)
    return day
