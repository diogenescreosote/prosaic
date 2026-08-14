# Spec: SUBP-001 — Civil Subpoena for Personal Appearance at Trial or Hearing

## Purpose

SUBP-001 compels a witness to appear and testify at a California
**trial or hearing** — and nothing else; there is no records demand on
its face. An attorney of record issues and signs it (a
self-represented party has the clerk issue it), service is personal
(CCP § 1987(a)) with witness fees payable on demand (Gov. Code
§ 68093), and the server completes the page-2 proof of service after
service. A subpoena that should also produce documents at the
trial/hearing is SUBP-002; deposition-stage process is
SUBP-010/015/020.

## Promises

1. **The caption fills itself from the case front matter on both
   pages**, including the independent page-2 proof-of-service caption.
   *(tested: smoke fill asserts the case number lands)*
2. **The court line carries the full court designation** — this form
   prints a bare "NAME OF COURT:" label, so the field receives the
   `court_name_full` composition, never the county alone. *(tested:
   test_court_name_full)*
3. **The command lands in the right boxes despite three lying widget
   names**: the ATTORNEY FOR line is a widget named `Email[0]` (the
   2007 caption has no e-mail line at all — `filer_email` goes nowhere
   on this form); item 1b's address box is named `HearingDept_ft`
   under a different parent than the true department box; and the
   department/division names are distributed differently than on
   SUBP-002 (`HearingDept_ft` = department here, with `HearingDiv` the
   division). *(tested: test_every_field_lands_in_its_mapped_widget +
   test_no_two_fields_share_a_widget)*
4. **Nothing is signed, dated, or decided by the machine.** The
   issuance date, both signature lines, and every page-2
   proof-of-service field and checkbox stay blank at issuance; the
   print-name and title lines are pre-filled from the filer.
5. **No attachment flow.** The form has no records description, no
   continuation boxes, and is not an `ATTACHMENT_COVER_SHEETS` member;
   it is filled standalone, not as a cover sheet over a demand.

## Non-obvious constraints

- **The blank is the pinned 2007-01 revision**; the
  descriptor-vs-blank test alarms on drift.
- **XFA must be stripped after filling** (LiveCycle hybrid), and the
  page-2 privacy-banner underlay is painted out by a whiteout.
- The item-1a department/division/room selector checkboxes use
  on-state `/Yes`, while the page-2 proof-of-service boxes use `/1`
  except the registered-photocopier and § 22451 boxes, which use `/3`
  — the same family quirk as SUBP-002 and SUBP-010.
