# Spec: SUBP-002 — Civil Subpoena (Duces Tecum) for Personal Appearance and Production at Trial or Hearing

## Purpose

SUBP-002 is how a California litigant compels a witness — very often a
non-party records custodian — to appear at a **trial or hearing** and
bring documents, electronically stored information, or things, with
the CCP § 1985(b) supporting declaration (good cause + materiality)
built into page 2. It is the instrument for putting records in front
of the **court** at a hearing; it is not deposition discovery, so the
deposition statutes and their timing do not govern it. An attorney of
record issues and signs it; a self-represented party has the clerk
issue it; service is personal (CCP § 1987(a)) with witness fees
payable on demand (Gov. Code § 68093), and the server completes the
page-3 proof of service after service.

Its place in the subpoena family: SUBP-001 is appearance-only at
trial/hearing; SUBP-010/015/020 are the deposition-stage forms. On
SUBP-002 a business-records custodian has two compliance modes, chosen
on the form's face (item 3): personal attendance with the original
records, or the Evidence Code §§ 1560–1562 mail-in — a sealed copy of
the records plus a § 1561 custodian declaration mailed to the **clerk
of the court**, no appearance required.

## Promises

1. **The caption fills itself from the case front matter, on all
   three pages** — the page-2 declaration caption and page-3
   proof-of-service caption are independent widget sets and are filled
   too. *(tested: smoke fill asserts the case number lands)*
2. **The court line carries the full court designation.** Unlike most
   JC captions, this form prints a bare "NAME OF COURT:" label, so the
   field receives "SUPERIOR COURT OF CALIFORNIA, COUNTY OF EXAMPLE"
   (the `court_name_full` binding), never the county alone. *(tested:
   test_court_name_full)*
3. **The command is stated in full and in the right boxes**: the
   witness, the hearing date/time, the department/division/room
   fill-ins with their selector checkboxes (on-state `/Yes`), the
   courthouse address, and the item-4 contact. The department box is
   `HearingDept_ft1` and the division box is `HearingDept_ft` — the
   un-suffixed name is the division, verified visually. *(tested:
   test_every_field_lands_in_its_mapped_widget +
   test_no_two_fields_share_a_widget)*
4. **Item 3's compliance modes are exclusive alternatives** —
   appear-and-produce (on `/1`) or records-by-mail to the clerk (on
   `/2`), sibling widgets both named `subp1`. The descriptor documents
   check-exactly-one; nothing checks a default.
5. **The page-2 declaration is a first-class citizen**: declarant
   capacity (a six-way radio with specify fields), the records demand,
   good cause, and materiality each land in their own multiline box,
   and each overflows to its own attachment — the records demand to
   **Attachment 2** (not 3, as on SUBP-010), good cause to Attachment
   3, materiality to Attachment 4 — via MC-025 with the matching
   "Continued on Attachment N." box (on-state `/2`) kept consistent
   automatically.
6. **Nothing is signed, dated, or decided by the machine.** Both
   signature dates, both signature lines, and every page-3
   proof-of-service field and checkbox stay blank at issuance; the
   print-name lines are pre-filled from the filer so only pen strokes
   and dates remain.
7. **The cover-sheet flow treats the body as Attachment 2**: a source
   with `cover_sheet: subp002` is a continuation of the form
   (`ATTACHMENT_COVER_SHEETS`), must carry `no_caption: true`, and
   should be titled as Attachment 2 to the subpoena.

## Non-obvious constraints

- **Consumer/employee records need SUBP-025 notices** (CCP §§ 1985.3,
  1985.6) on the statutory clocks, exactly as with SUBP-010; the
  `consumer_notices:` mechanism serves this form identically.
- **Good cause and materiality are load-bearing.** CCP § 1985(b)
  requires the declaration to show both, and the subpoena stands or
  falls on that showing under CCP § 1987.1. The agent_guide tells
  authors to state concrete, case-specific reasons.
- **The blank is the pinned 2012-01 revision**; the descriptor-vs-blank
  test alarms on drift, like every registered form.
- **XFA must be stripped after filling** (LiveCycle hybrid, same
  generation as SUBP-010), and the page-3 privacy-banner underlay is
  painted out by a whiteout.
