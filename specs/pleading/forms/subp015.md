# Spec: SUBP-015 — Deposition Subpoena for Personal Appearance

## Purpose

SUBP-015 compels a nonparty witness to appear and testify at a
**deposition** — and nothing else; there is no records demand on its
face. Because it commands no personal records, the consumer-notice
machinery of CCP § 1985.3 (SUBP-025, the consumer's written objection
that freezes production) does not attach to it, and no good-cause
declaration accompanies it. An attorney of record issues and signs it
(CCP § 2020.210(b)); a self-represented party has the clerk issue a
signed blank and completes it. Service is personal on the deponent
(CCP § 2020.220(b)) with witness fees and mileage both ways payable
with service or at the deposition at the subpoenaing party's option
(Gov. Code § 68093; item 3 of the form recites this), and the server
completes the page-2 proof of service after service.

The subpoena addresses the witness; the parties are told by a separate
**deposition notice** (CCP § 2025.220) — a captioned pleading, not a
form field — that must match the subpoena's date, time, place and
recording method and, for a remote deposition, say so (CCP § 2025.310;
Cal. Rules of Court, rule 3.1010). A deposition subpoena that should
also produce documents, ESI or things is SUBP-020; records without a
witness is SUBP-010; trial or hearing process is SUBP-001/002.

## Promises

1. **The caption fills itself from the case front matter on both
   pages**, including the independent page-2 proof-of-service caption
   and — on this 2009 revision — a real e-mail line. *(tested: smoke
   fill asserts the case number lands; every-field fill)*
2. **The command lands in the right boxes despite two recycled widget
   names**: item 1's TIME box is a `TextField1[0]` under
   `List1.Info`, the same leaf name as the attorney block under
   `P1Caption`; and the issuer TITLE box is a `TextField9[0]`, the same
   leaf name as the page-2 address-where-served box. Parents
   distinguish them; the descriptor keys do too. *(tested:
   test_every_field_lands_in_its_mapped_widget +
   test_no_two_fields_share_a_widget)*
3. **Entity-only items stay off for a natural person.** Item 1a (the
   § 2025.230 designee order), item 2's selector, and the
   matters-for-examination box are filled only when the deponent is an
   organization; the agent guide says so and nothing sets them by
   default. A description of subject matter for an individual is
   surplusage and is not offered.
4. **Nothing is signed, dated, or decided by the machine.** The
   issuance date, the issuing signature, and every page-2
   proof-of-service field and checkbox stay blank at issuance; the
   print-name and title lines are pre-filled from the filer.
5. **No attachment flow.** The form has no records description, no
   continuation boxes, and is not an `ATTACHMENT_COVER_SHEETS` member;
   it is filled standalone, never as a cover sheet over a demand.

## Non-obvious constraints

- **The blank is the pinned 2009-01 revision**; the
  descriptor-vs-blank test alarms on drift.
- **The output is flattened** (the blank is a LiveCycle hybrid whose
  form layer never reaches the service copy, ADR-0046). The page-2
  privacy-banner underlay is painted out by a whiteout sized to the
  Warning widget's own rect (`[36.0, 10.2, 247.3, 33.4]` plus a 1-pt
  margin); SUBP-001's taller rect clips this form's footer title and
  must not be copied.
- All page-1 checkboxes use on-state `/1`. The three page-2 witness-fee
  boxes (item 1e) share the leaf name `ch1[0]` and are told apart by
  parent and on-state (`/1`, `/2`, `/3`); the page-2 server-identity
  boxes (item 3a–g) all use `/1` — this revision does not carry the
  `/3` quirk of SUBP-001/002/010 on the photocopier and § 22451 boxes.
- Item 3's recital of CCP § 2025.250 (75 miles of the deponent's
  residence; 150 within the county where the action is pending) keys
  on the deponent's **residence**, not the address printed in the
  deponent box; a filler that knows only a business address should say
  so in the notice rather than assume the residence is nearby.
