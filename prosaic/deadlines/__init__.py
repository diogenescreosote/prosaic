"""Statutory date computation.

The computation and rule layers are pure: no network, no language model, no
imports outside the standard library; every function maps input dates to
output dates deterministically. The single point of I/O in this package is
``california_court_calendar``, which loads the packaged holiday data —
calendars are data, and the rules take one as an argument.
"""

from prosaic.deadlines.calendars import (
    CalendarCoverageError,
    CourtCalendar,
    california_court_calendar,
)
from prosaic.deadlines.computation import (
    add_calendar_days,
    add_court_days,
    next_court_day,
    previous_court_day,
    roll_backward,
    roll_forward,
    subtract_calendar_days,
    subtract_court_days,
)
from prosaic.deadlines.rules import (
    Deadline,
    case_management_statement_deadline,
    complaint_service_deadline,
    deadline_after_service,
    demurrer_deadline,
    earliest_motion_hearing,
    motion_filing_deadline,
    opposition_deadline,
    reply_deadline,
)
from prosaic.deadlines.types import CalendarDays, CourtDays, ServiceMethod

__all__ = [
    "CalendarCoverageError",
    "CalendarDays",
    "CourtCalendar",
    "CourtDays",
    "Deadline",
    "ServiceMethod",
    "add_calendar_days",
    "add_court_days",
    "california_court_calendar",
    "case_management_statement_deadline",
    "complaint_service_deadline",
    "deadline_after_service",
    "demurrer_deadline",
    "earliest_motion_hearing",
    "motion_filing_deadline",
    "next_court_day",
    "opposition_deadline",
    "previous_court_day",
    "reply_deadline",
    "roll_backward",
    "roll_forward",
    "subtract_calendar_days",
    "subtract_court_days",
]
