"""Named statutory deadline rules for California civil practice.

Every rule takes facts — dates, a service method — plus a court calendar,
and returns a ``Deadline`` carrying the computed date, the citation, and a
description of what is due. Nothing here reads the case model or performs
I/O; the agent layer can obtain dates only by calling in with typed facts.

Two extension tables exist on purpose. Periods that run *after* service
extend under CCP § 1013 and § 1010.6, where overnight, fax, and electronic
service add two *court* days. The motion-notice period of CCP § 1005(b)
has its own table: there, overnight and fax service add two *calendar*
days. The statutes genuinely differ, and conflating the tables produces
dates that are wrong by a weekend.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from prosaic.deadlines.calendars import CourtCalendar
from prosaic.deadlines.computation import (
    add_calendar_days,
    add_court_days,
    roll_backward,
    roll_forward,
    subtract_calendar_days,
    subtract_court_days,
)
from prosaic.deadlines.types import CalendarDays, CourtDays, ServiceMethod


@dataclass(frozen=True, slots=True)
class Deadline:
    """A computed date with the rule it came from."""

    date: datetime.date
    citation: str
    description: str


_AFTER_SERVICE_EXTENSION: dict[ServiceMethod, CalendarDays | CourtDays] = {
    ServiceMethod.PERSONAL: CalendarDays(0),
    ServiceMethod.MAIL_WITHIN_CALIFORNIA: CalendarDays(5),
    ServiceMethod.MAIL_OUTSIDE_CALIFORNIA: CalendarDays(10),
    ServiceMethod.MAIL_OUTSIDE_UNITED_STATES: CalendarDays(20),
    ServiceMethod.EXPRESS_OVERNIGHT: CourtDays(2),
    ServiceMethod.FAX: CourtDays(2),
    ServiceMethod.ELECTRONIC: CourtDays(2),
}

_MOTION_NOTICE_ADDITION: dict[ServiceMethod, CalendarDays | CourtDays] = {
    ServiceMethod.PERSONAL: CalendarDays(0),
    ServiceMethod.MAIL_WITHIN_CALIFORNIA: CalendarDays(5),
    ServiceMethod.MAIL_OUTSIDE_CALIFORNIA: CalendarDays(10),
    ServiceMethod.MAIL_OUTSIDE_UNITED_STATES: CalendarDays(20),
    ServiceMethod.EXPRESS_OVERNIGHT: CalendarDays(2),
    ServiceMethod.FAX: CalendarDays(2),
    ServiceMethod.ELECTRONIC: CourtDays(2),
}


def _later(
    start: datetime.date, span: CalendarDays | CourtDays, calendar: CourtCalendar
) -> datetime.date:
    if isinstance(span, CalendarDays):
        return add_calendar_days(start, span)
    return add_court_days(start, span, calendar)


def _earlier(
    reference: datetime.date, span: CalendarDays | CourtDays, calendar: CourtCalendar
) -> datetime.date:
    if isinstance(span, CalendarDays):
        return subtract_calendar_days(reference, span)
    return subtract_court_days(reference, span, calendar)


def deadline_after_service(
    served: datetime.date,
    period: CalendarDays,
    method: ServiceMethod,
    calendar: CourtCalendar,
    *,
    citation: str,
    description: str,
) -> Deadline:
    """A period that begins when a document is served.

    Computes CCP § 12 (first day excluded), extends per § 1013 / § 1010.6
    for the service method, and rolls a weekend or holiday landing forward
    per § 12a. ``served`` is the date service was *complete* under the
    applicable service statute.
    """
    base = add_calendar_days(served, period)
    extended = _later(base, _AFTER_SERVICE_EXTENSION[method], calendar)
    return Deadline(
        date=roll_forward(extended, calendar),
        citation=citation,
        description=description,
    )


def demurrer_deadline(
    complaint_served: datetime.date, method: ServiceMethod, calendar: CourtCalendar
) -> Deadline:
    """Last day to demur: 30 days after service of the complaint.

    CCP § 430.40(a). The trigger is the date service of the complaint was
    complete; the same computation governs the answer under § 412.20(a)(3).
    """
    return deadline_after_service(
        complaint_served,
        CalendarDays(30),
        method,
        calendar,
        citation="CCP §§ 430.40(a), 12a, 1013",
        description="Last day to demur (or otherwise respond) to the complaint",
    )


def motion_filing_deadline(
    hearing: datetime.date, method: ServiceMethod, calendar: CourtCalendar
) -> Deadline:
    """Last day to file and serve moving papers for a noticed motion.

    CCP § 1005(b): sixteen court days before the hearing, counted backward
    excluding the hearing date (§ 12c), with the notice period increased per
    the method of service. A weekend or holiday landing rolls backward —
    rolling forward would eat into the opponent's notice.
    """
    base = subtract_court_days(hearing, CourtDays(16), calendar)
    earlier = _earlier(base, _MOTION_NOTICE_ADDITION[method], calendar)
    return Deadline(
        date=roll_backward(earlier, calendar),
        citation="CCP §§ 1005(b), 12c; CRC 3.1300(a)",
        description="Last day to file and serve notice of motion and moving papers",
    )


def earliest_motion_hearing(
    papers_served: datetime.date, method: ServiceMethod, calendar: CourtCalendar
) -> Deadline:
    """The first hearing date for which papers served today are timely.

    The forward image of ``motion_filing_deadline``: the notice addition for
    the service method, then sixteen court days.
    """
    after = _later(papers_served, _MOTION_NOTICE_ADDITION[method], calendar)
    return Deadline(
        date=add_court_days(after, CourtDays(16), calendar),
        citation="CCP §§ 1005(b), 12c",
        description="Earliest hearing date giving timely notice for papers served this day",
    )


def opposition_deadline(hearing: datetime.date, calendar: CourtCalendar) -> Deadline:
    """Opposition papers: nine court days before the hearing (CCP § 1005(b)).

    The service-method additions of § 1005(b) apply to the moving papers'
    notice period, not to opposition or reply timing.
    """
    return Deadline(
        date=subtract_court_days(hearing, CourtDays(9), calendar),
        citation="CCP §§ 1005(b), 12c",
        description="Last day to file and serve opposition papers",
    )


def reply_deadline(hearing: datetime.date, calendar: CourtCalendar) -> Deadline:
    """Reply papers: five court days before the hearing (CCP § 1005(b))."""
    return Deadline(
        date=subtract_court_days(hearing, CourtDays(5), calendar),
        citation="CCP §§ 1005(b), 12c",
        description="Last day to file and serve reply papers",
    )


def complaint_service_deadline(complaint_filed: datetime.date, calendar: CourtCalendar) -> Deadline:
    """Serve all named defendants and file proofs of service.

    CRC 3.110(b): within 60 days after the complaint is filed, rolled
    forward per CCP § 12a.
    """
    return Deadline(
        date=roll_forward(add_calendar_days(complaint_filed, CalendarDays(60)), calendar),
        citation="CRC 3.110(b); CCP § 12a",
        description="Last day to serve the complaint on all named defendants and file proofs",
    )


def case_management_statement_deadline(
    conference: datetime.date, calendar: CourtCalendar
) -> Deadline:
    """File and serve the case management statement.

    CRC 3.725(a): no later than 15 calendar days before the conference. A
    weekend or holiday landing rolls backward for the same reason as motion
    papers: later is not an option.
    """
    return Deadline(
        date=roll_backward(subtract_calendar_days(conference, CalendarDays(15)), calendar),
        citation="CRC 3.725(a)",
        description="Last day to file and serve the case management statement",
    )
