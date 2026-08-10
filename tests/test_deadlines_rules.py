"""Golden-date tests for the statutory rules.

Every expected date here was worked out by hand against the packaged
holiday calendar; the docs/DEADLINES.md examples mirror these cases.
"""

from __future__ import annotations

import datetime

from prosaic.deadlines import (
    ServiceMethod,
    california_court_calendar,
    case_management_statement_deadline,
    complaint_service_deadline,
    demurrer_deadline,
    earliest_motion_hearing,
    motion_filing_deadline,
    opposition_deadline,
    reply_deadline,
)

CAL = california_court_calendar()
HEARING = datetime.date(2026, 10, 2)  # a Friday; Labor Day and Native American Day intervene


def test_motion_filing_personal_service() -> None:
    deadline = motion_filing_deadline(HEARING, ServiceMethod.PERSONAL, CAL)
    assert deadline.date == datetime.date(2026, 9, 9)
    assert "1005(b)" in deadline.citation


def test_motion_filing_mail_within_california() -> None:
    deadline = motion_filing_deadline(HEARING, ServiceMethod.MAIL_WITHIN_CALIFORNIA, CAL)
    assert deadline.date == datetime.date(2026, 9, 4)


def test_motion_filing_electronic_service() -> None:
    # Two court days back from September 9 crosses the Labor Day weekend.
    deadline = motion_filing_deadline(HEARING, ServiceMethod.ELECTRONIC, CAL)
    assert deadline.date == datetime.date(2026, 9, 4)


def test_opposition_nine_court_days_before_hearing() -> None:
    assert opposition_deadline(HEARING, CAL).date == datetime.date(2026, 9, 18)


def test_reply_five_court_days_before_hearing() -> None:
    assert reply_deadline(HEARING, CAL).date == datetime.date(2026, 9, 24)


def test_earliest_hearing_inverts_the_electronic_deadline() -> None:
    result = earliest_motion_hearing(datetime.date(2026, 9, 4), ServiceMethod.ELECTRONIC, CAL)
    assert result.date == HEARING


def test_demurrer_rolls_sunday_landing_forward() -> None:
    # Served Friday May 22; thirty days lands Sunday June 21; next court day.
    deadline = demurrer_deadline(datetime.date(2026, 5, 22), ServiceMethod.PERSONAL, CAL)
    assert deadline.date == datetime.date(2026, 6, 22)


def test_demurrer_rolls_holiday_landing_past_the_weekend() -> None:
    # Thirty days from May 20 is Friday June 19 — Juneteenth — so the
    # deadline crosses the whole weekend to Monday June 22.
    deadline = demurrer_deadline(datetime.date(2026, 5, 20), ServiceMethod.PERSONAL, CAL)
    assert deadline.date == datetime.date(2026, 6, 22)


def test_demurrer_mail_service_adds_five_calendar_days() -> None:
    deadline = demurrer_deadline(
        datetime.date(2026, 5, 22), ServiceMethod.MAIL_WITHIN_CALIFORNIA, CAL
    )
    assert deadline.date == datetime.date(2026, 6, 26)


def test_demurrer_overnight_service_adds_two_court_days() -> None:
    # Thirty days from November 20 is Sunday December 20; two court days
    # after that is Tuesday December 22.
    deadline = demurrer_deadline(datetime.date(2026, 11, 20), ServiceMethod.EXPRESS_OVERNIGHT, CAL)
    assert deadline.date == datetime.date(2026, 12, 22)


def test_complaint_service_sixty_days_from_filing() -> None:
    deadline = complaint_service_deadline(datetime.date(2026, 1, 5), CAL)
    assert deadline.date == datetime.date(2026, 3, 6)
    assert "3.110(b)" in deadline.citation


def test_case_management_statement_rolls_backward_off_a_sunday() -> None:
    # Fifteen days before a Monday conference is a Sunday; the safe day is
    # the preceding Friday, not the following Monday.
    deadline = case_management_statement_deadline(datetime.date(2026, 4, 20), CAL)
    assert deadline.date == datetime.date(2026, 4, 3)
    assert "3.725" in deadline.citation
