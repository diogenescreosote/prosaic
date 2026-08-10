# Spec: SUBP-010 — Deposition Subpoena for Production of Business Records

## Purpose

SUBP-010 is how a California litigant gets documents out of a
**non-party** — a bank, employer, school, hospital, therapist, phone
carrier — without anyone appearing or testifying. It commands a
records custodian to deliver business records to a *deposition
officer* by a stated date (CCP §§ 2020.410–2020.440). An attorney of
record issues and signs it with no court involvement (CCP
§ 2020.210(b)); a self-represented party has the clerk issue it. The
person who serves it completes the proof of service on page 2 after
service, and the subpoenaing party also serves a copy on every other
party.

It is the records-only member of the subpoena family, and the family
matters: SUBP-020 adds the custodian's personal appearance, SUBP-030 is
appearance-for-testimony, and SUBP-001/002 reach appearance at trial or
a hearing rather than production to a deposition officer. SUBP-010 has
no personal-appearance option anywhere on its face; a workflow that
wants testimony wants a different form, not a different checkbox.

## Promises

1. **The caption fills itself from the case front matter**, on both
   pages — the page-2 proof-of-service caption is an independent set
   of widgets and is filled too. In a civil action the `petitioner`
   and `respondent` meta keys carry the plaintiff and defendant; the
   form's own labels read "PLAINTIFF/PETITIONER" and
   "DEFENDANT/RESPONDENT". *(tested: smoke fill asserts the case
   number lands; own-name landing confirms both copies are distinct
   widgets)*
2. **The command is stated in full and in the right boxes**: the
   deponent custodian, the deposition officer, the production date,
   the production time, and the production location each land in
   their own field, despite four of those widgets carrying recycled
   *hearing* names (`HearingDept_ft`, `HearingDate_dt`,
   `HearingTime_dt`). *(tested:
   test_every_field_lands_in_its_mapped_widget +
   test_no_two_fields_share_a_widget)*
3. **A real records demand becomes a proper attachment.** Item 3's
   widget is a single line; anything longer produces "See Attachment
   3." on the form plus an appended MC-025 carrying the full demand,
   and the form's own "Continued on Attachment 3." box is set to
   match what actually happened. *(tested:
   test_subp010_records_overflow_checks_attachment_3 — long demand
   overflows, box checked, MC-025 appended, sentinel text survives;
   short demand fits, box unchecked)*
4. **Exactly one production method is commanded** — mailed copies to
   the officer (1a), copies to the officer at the witness's address
   (1b), or originals inspected at the witness's business address
   (1c). Zero leaves the custodian no lawful way to comply; two give
   contradictory commands. *(untested: coherence is stated in the
   agent_guide and belongs to the human choosing the method)*
5. **Nothing is issued by the machine.** "Date issued" stays blank —
   issuance *is* the signature, and the date issued starts the
   20-day production clock. The signature line has no widget at all;
   only the issuer's printed name and title are pre-filled, from
   `filer_name` (SBN suffix stripped) and `filer_role` verbatim.
   *(tested: test_mandatory_blanks_survive_a_rich_fill + AI visual
   court-readiness judgment)*
6. **Page 2 travels blank.** Every proof-of-service field and
   checkbox is mapped so a post-service workflow can complete it from
   real service facts, and every one of them is empty on any fill
   driven by case metadata. *(tested:
   test_mandatory_blanks_survive_a_rich_fill covers the pos_* text
   fields; pos_* checkboxes have no defaults)*
7. **The output is a clean service copy**: the XFA layer is stripped
   so viewers render the values we filled, the Print/Save/Clear
   buttons and the privacy banner are removed, and the gray block the
   banner leaves behind is painted out. *(tested:
   test_xfa_layer_stripped_from_output; the whiteout is confirmed by
   the AI visual judgment)*
8. **The descriptor matches the shipped blank's revision**
   (Rev. January 1, 2012), including the two odd checkbox on-states.
   *(tested: test_descriptor_matches_blank)*

## Non-obvious constraints

- **Item 3 is one line, not a paragraph.** The printed form leaves
  what looks like a text area under item 3, but the widget is a
  single-line box ~12 pt tall spanning the page width. Roughly one
  line of 9 pt text fits. This is why the form prints its own
  "Continued on Attachment 3." box, and why the descriptor marks the
  field `fit: overflow_attachment` rather than shrinking. Shrinking a
  records demand to fit would produce an illegible — and therefore
  unenforceable — command.
- **The item-1 field names are hearing names.** `HearingDept_ft` is
  the *deposition officer*, `HearingDate_dt` the *production date*,
  `HearingTime_dt` the *production time*. Nothing on SUBP-010
  concerns a hearing; a name-inferred remapping would put a
  department number where a records service belongs.
- **Two checkbox on-states are `/3`, not `/1`.** Page 2's items 3f
  (registered professional photocopier) and 3g (exempt under B&P
  § 22451) differ from every other box on the form. Assuming `/1`
  would leave them silently unchecked.
- **The deposition officer is not the subpoenaing attorney.** CCP
  § 2020.420 requires a professional photocopier or other qualified
  person; naming the propounding lawyer's own office invalidates the
  production channel.
- **The 20/15-day floor is on the form's face** (item 2; CCP
  § 2020.410(c)): production may be no sooner than 20 days after
  issuance or 15 days after service, whichever is later. Because the
  issuance date is deliberately blank, no code path can check that
  arithmetic — the human who picks the production date owns it.
- **Consumer and employee records need a companion.** For records
  about an identifiable individual (bank, medical, insurance, phone,
  personnel, school), CCP § 1985.3 and § 1985.6 require serving that
  person with a Notice to Consumer or Employee (SUBP-025) and a copy
  of the subpoena on a statutory clock, plus proof of that service on
  the custodian. Item 4 of the form warns the *custodian* about this;
  it imposes nothing on the subpoenaing party's own paperwork, so a
  SUBP-010 produced alone for consumer or employee records is invalid
  however well it renders. A source declares the recipients in
  `consumer_notices:` and the build emits the notices alongside the
  subpoena (specs/pleading/forms/subp025.md). Medical and
  psychotherapy records may additionally require the patient's written
  authorization or a court order.
- **Page 2 is the server's sworn statement, not the filer's.** It is
  mapped for a later, fact-driven fill; it must never be populated
  from case metadata at issuance, and the copy served on the
  custodian carries it blank.
