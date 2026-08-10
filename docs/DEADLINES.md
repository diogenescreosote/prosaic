# The deadline engine

Every date the engine produces is computed by a pure function from a trigger
date, a service method where the statute cares, and a court calendar. The
tables below list every implemented rule with its citation and the test that
pins it. If a rule is not in this file, prosaic does not compute it.

The packaged calendar covers California statewide judicial holidays from
2025-01-01 through 2028-12-31, cross-checked against the Judicial Council
and county court published schedules; the data file carries its source
URLs. The quirks are in the data — for example, New Year's Day 2028 falls
on a Saturday and is observed Friday, December 31, 2027, so that day is a
2027 holiday. A computation that touches a date outside the
covered window raises `CalendarCoverageError` rather than treating unknown
years as holiday-free.

## Day arithmetic (CCP §§ 12, 12a, 12c)

| Operation | Rule | Function | Test |
| --- | --- | --- | --- |
| Count a period excluding the first day, including the last | CCP § 12 | `add_calendar_days` | `test_deadlines_properties.py` (round-trip, monotonicity) |
| Roll a last day that falls on a weekend or holiday forward to the next court day | CCP § 12a | `roll_forward` | `test_roll_forward_is_idempotent_and_never_moves_backward` |
| Count court days backward from a hearing, excluding the hearing date | CCP § 12c | `subtract_court_days` | `test_court_day_subtraction_then_addition_lands_on_rolled_start` |

Backward-measured deadlines roll **backward**: when the last day to act
before a hearing lands on a holiday, acting later would eat the opponent's
notice period, so the safe day is the previous court day.

## Statutory rules

Triggers are the dates the statutes run from: for a demurrer, the date
service of the complaint was **complete** under the applicable service
statute; for motion papers, the hearing date.

| Rule | Trigger | Computation | Citation | Service adjustment | Test |
| --- | --- | --- | --- | --- | --- |
| Demurrer (and responsive pleading) | Service of complaint complete | 30 calendar days, extended per method, rolled forward | CCP §§ 430.40(a), 12a, 1013 | After-service table below | `test_demurrer_*` (4 golden cases) |
| Motion filing and service | Hearing date | 16 court days backward, notice increased per method, rolled backward | CCP §§ 1005(b), 12c; CRC 3.1300(a) | Motion-notice table below | `test_motion_filing_*` (3 golden cases) |
| Earliest motion hearing | Papers served | Forward image of the filing rule | CCP §§ 1005(b), 12c | Motion-notice table below | `test_earliest_hearing_inverts_the_electronic_deadline` |
| Opposition papers | Hearing date | 9 court days backward | CCP §§ 1005(b), 12c | None — the § 1005(b) additions apply to moving papers' notice, not opposition timing | `test_opposition_nine_court_days_before_hearing` |
| Reply papers | Hearing date | 5 court days backward | CCP §§ 1005(b), 12c | None | `test_reply_five_court_days_before_hearing` |
| Serve complaint, file proofs | Complaint filed | 60 calendar days, rolled forward | CRC 3.110(b); CCP § 12a | None | `test_complaint_service_sixty_days_from_filing` |
| Case management statement | Conference date | 15 calendar days backward, rolled backward | CRC 3.725(a) | None | `test_case_management_statement_rolls_backward_off_a_sunday` |

`deadline_after_service` is the generic form of the demurrer computation:
any period that runs from service of a paper, with the § 1013 / § 1010.6
extensions and the § 12a roll.

## The two extension tables

They differ on purpose, and conflating them produces dates wrong by a
weekend.

**Periods running after service** (CCP § 1013; electronic per § 1010.6):

| Method | Extension |
| --- | --- |
| Personal | none |
| Mail within California | +5 calendar days |
| Mail to elsewhere in the United States | +10 calendar days |
| Mail outside the United States | +20 calendar days |
| Express / overnight | +2 **court** days |
| Fax | +2 **court** days |
| Electronic | +2 **court** days |

**The § 1005(b) motion-notice period** (electronic per § 1010.6):

| Method | Addition to the 16 court days |
| --- | --- |
| Personal | none |
| Mail within California | +5 calendar days |
| Mail to elsewhere in the United States | +10 calendar days |
| Mail outside the United States | +20 calendar days |
| Express / overnight | +2 **calendar** days |
| Fax | +2 **calendar** days |
| Electronic | +2 **court** days |

## Properties, not just examples

The golden dates in `tests/test_deadlines_rules.py` were worked out by hand
against the holiday calendar. `tests/test_deadlines_properties.py` then
asserts, with Hypothesis, over the calendar's whole coverage window:

- a computed deadline required to be a court day never lands on a weekend
  or court holiday;
- a service-method extension never shortens a period, in either direction —
  response deadlines never move earlier, notice deadlines never move later;
- every rule is monotonic in its trigger date;
- backward motion computation round-trips through the forward rule —
  exactly, for personal and electronic service on a court-day hearing;
- court-day subtraction then addition lands on the rolled starting day.

## Worked example

Hearing Friday, October 2, 2026. Counting sixteen court days backward
crosses Labor Day (September 7) and Native American Day (September 25):
the last day to file and serve is **Wednesday, September 9** for personal
service. Serving electronically adds two court days of notice, and stepping
those back from September 9 crosses the Labor Day weekend, landing on
**Friday, September 4** — the same day mail service happens to give, by a
different computation. All three are golden tests.
