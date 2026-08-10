"""Property-based tests for the deadline engine.

Examples prove single points; these assert the shape of the arithmetic over
the whole coverage window of the packaged calendar. Input ranges leave
margin at both edges so extensions cannot walk a computation out of
coverage.
"""

from __future__ import annotations

import datetime

from hypothesis import given
from hypothesis import strategies as st

from prosaic.deadlines import (
    CourtDays,
    ServiceMethod,
    add_court_days,
    california_court_calendar,
    case_management_statement_deadline,
    complaint_service_deadline,
    demurrer_deadline,
    earliest_motion_hearing,
    motion_filing_deadline,
    opposition_deadline,
    reply_deadline,
    roll_forward,
    subtract_court_days,
)

CAL = california_court_calendar()

mid_range_days = st.dates(datetime.date(2025, 3, 1), datetime.date(2028, 10, 1))
hearing_days = st.dates(datetime.date(2025, 4, 1), datetime.date(2028, 11, 30))
trigger_days = st.dates(datetime.date(2025, 1, 2), datetime.date(2028, 10, 1))
methods = st.sampled_from(list(ServiceMethod))
spans = st.integers(min_value=1, max_value=30)


@given(day=mid_range_days, count=spans)
def test_court_day_subtraction_then_addition_lands_on_rolled_start(
    day: datetime.date, count: int
) -> None:
    earlier = subtract_court_days(day, CourtDays(count), CAL)
    assert CAL.is_court_day(earlier)
    assert add_court_days(earlier, CourtDays(count), CAL) == roll_forward(day, CAL)


@given(day=mid_range_days)
def test_roll_forward_is_idempotent_and_never_moves_backward(day: datetime.date) -> None:
    rolled = roll_forward(day, CAL)
    assert rolled >= day
    assert CAL.is_court_day(rolled)
    assert roll_forward(rolled, CAL) == rolled


@given(hearing=hearing_days, method=methods)
def test_motion_deadline_is_a_court_day_before_the_hearing(
    hearing: datetime.date, method: ServiceMethod
) -> None:
    deadline = motion_filing_deadline(hearing, method, CAL)
    assert CAL.is_court_day(deadline.date)
    assert deadline.date < hearing


@given(hearing=hearing_days, method=methods)
def test_service_method_never_shortens_motion_notice(
    hearing: datetime.date, method: ServiceMethod
) -> None:
    personal = motion_filing_deadline(hearing, ServiceMethod.PERSONAL, CAL)
    other = motion_filing_deadline(hearing, method, CAL)
    assert other.date <= personal.date


@given(served=trigger_days, method=methods)
def test_service_method_never_shortens_a_response_period(
    served: datetime.date, method: ServiceMethod
) -> None:
    personal = demurrer_deadline(served, ServiceMethod.PERSONAL, CAL)
    other = demurrer_deadline(served, method, CAL)
    assert other.date >= personal.date


@given(served=trigger_days, method=methods)
def test_response_deadline_is_a_court_day_after_service(
    served: datetime.date, method: ServiceMethod
) -> None:
    deadline = demurrer_deadline(served, method, CAL)
    assert CAL.is_court_day(deadline.date)
    assert deadline.date > served


@given(first=trigger_days, second=trigger_days, method=methods)
def test_response_deadline_is_monotonic_in_the_trigger(
    first: datetime.date, second: datetime.date, method: ServiceMethod
) -> None:
    early, late = sorted((first, second))
    assert demurrer_deadline(early, method, CAL).date <= demurrer_deadline(late, method, CAL).date


@given(first=hearing_days, second=hearing_days, method=methods)
def test_motion_deadline_is_monotonic_in_the_hearing_date(
    first: datetime.date, second: datetime.date, method: ServiceMethod
) -> None:
    early, late = sorted((first, second))
    assert (
        motion_filing_deadline(early, method, CAL).date
        <= motion_filing_deadline(late, method, CAL).date
    )


@given(hearing=hearing_days, method=methods)
def test_backward_motion_computation_round_trips_through_the_forward_rule(
    hearing: datetime.date, method: ServiceMethod
) -> None:
    deadline = motion_filing_deadline(hearing, method, CAL)
    recovered = earliest_motion_hearing(deadline.date, method, CAL)
    assert recovered.date <= roll_forward(hearing, CAL)
    if method in (ServiceMethod.PERSONAL, ServiceMethod.ELECTRONIC) and CAL.is_court_day(hearing):
        assert recovered.date == hearing


@given(hearing=hearing_days)
def test_motion_papers_precede_opposition_precede_reply_precede_hearing(
    hearing: datetime.date,
) -> None:
    filing = motion_filing_deadline(hearing, ServiceMethod.PERSONAL, CAL).date
    opposition = opposition_deadline(hearing, CAL).date
    reply = reply_deadline(hearing, CAL).date
    assert filing < opposition < reply < hearing


@given(filed=trigger_days)
def test_complaint_service_deadline_is_a_court_day_at_least_sixty_days_out(
    filed: datetime.date,
) -> None:
    deadline = complaint_service_deadline(filed, CAL)
    assert CAL.is_court_day(deadline.date)
    assert (deadline.date - filed).days >= 60


@given(conference=hearing_days)
def test_case_management_statement_is_due_a_court_day_at_least_fifteen_days_early(
    conference: datetime.date,
) -> None:
    deadline = case_management_statement_deadline(conference, CAL)
    assert CAL.is_court_day(deadline.date)
    assert (conference - deadline.date).days >= 15
