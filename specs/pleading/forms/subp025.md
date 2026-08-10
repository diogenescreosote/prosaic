# Spec: SUBP-025 — Notice to Consumer or Employee and Objection

## Purpose

SUBP-025 is the notice a subpoenaing party must serve on the person
whose records a subpoena reaches. Code Civ. Proc. § 1985.3 (consumer
records — a natural person's medical, psychotherapy, insurance,
banking, credit, phone, utility, school, or professional-service
records) and § 1985.6 (employment records) give that person a chance
to object *before* a stranger's custodian hands their file to the
parties. Without it, a records subpoena for such records is invalid
however well it renders: the custodian may not lawfully produce, and
the production is exposed to a motion to quash and to sanctions.

It is therefore a companion, never a standalone filing. It travels
with a copy of the subpoena to the consumer, and its own proof of
service travels to the custodian, who may not produce without it
(§ 1985.3(c)). It is also not filed with the court in the ordinary
course — it is served.

The form is two documents on one sheet. The top half of page 1 is the
notice, signed by the requesting party or that party's attorney. The
bottom half ("OBJECTION BY NON-PARTY TO PRODUCTION OF RECORDS") is a
reply form the *recipient* completes and serves. Page 2 carries two
unrelated proofs of service: one for the notice (the serving party's)
and one for the objection (the consumer's).

## Promises

1. **The caption fills itself from the case front matter**, on both
   pages — the page-2 caption echo is an independent set of widgets
   and is filled too. *(tested: caption count per notice in the
   form_filling scenario and in TestConsumerNotices)*
2. **The four notice facts land in their own boxes**: the consumer
   addressed ("TO (name)"), the requesting party, the date records are
   sought for examination, and the witness custodian's name and
   address. *(tested: test_every_field_lands_in_its_mapped_widget +
   test_no_two_fields_share_a_widget)*
3. **One notice per recipient, addressed individually.** A source
   declares `consumer_notices:` and the build emits one filled
   SUBP-025 per entry as a separate file beside the document's own
   PDF, each carrying only its own recipient's values. *(tested:
   envelope build in the form_filling scenario; naming, precedence,
   and isolation checks in TestConsumerNotices)*
4. **A defective notice list fails the build.** A missing `consumer`,
   a non-mapping entry, a value that is not a SUBP-025 field, or two
   recipients that collapse to one filename all raise rather than
   emit. The failure mode this forecloses is a packet that looks
   complete while a consumer went unserved. *(tested: four failure
   paths in TestConsumerNotices)*
5. **Nothing on the recipient's half is ever pre-filled.** The
   objection checkboxes, the objected-to records, the grounds, and the
   objection date and printed name stay empty on any fill driven by
   case metadata; so does every field and checkbox of both proofs of
   service. *(tested: test_mandatory_blanks_survive_a_rich_fill +
   scenario blank checks + AI visual judgment)*
6. **The notice is not signed or dated by the machine.** The date
   above the notice signature stays blank, the signature line has no
   widget, and the REQUESTING PARTY / ATTORNEY capacity boxes are left
   for the signer; only the signer's printed name is pre-filled, from
   `filer_name` (SBN suffix stripped). *(tested: the blank sweep and
   the AI visual judgment)*
7. **The output is a clean service copy**: the XFA layer is stripped
   so viewers render the values we filled, the Print/Save/Clear
   buttons and the privacy banner are removed, and the gray block the
   banner leaves behind is painted out. *(tested:
   test_xfa_layer_stripped_from_output; the whiteout is confirmed by
   the AI visual judgment)*
8. **The descriptor matches the shipped blank's revision**
   (Rev. January 1, 2008), including the checkbox on-states that are
   `/2`. *(tested: test_descriptor_matches_blank)*

## Non-obvious constraints

- **The service clocks run backward from the production date.** The
  notice and a copy of the subpoena must be served on the consumer or
  employee (and on their attorney of record in this action) at least
  10 days before the production date stated in the subpoena and at
  least 5 days before the subpoena is served on the custodian, plus
  the Code Civ. Proc. § 1013 extension for service by mail. Those
  floors sit under the subpoena's own 20-day-from-issuance /
  15-day-from-service floor, so the production date must be chosen
  last. Nothing in the descriptor can check the arithmetic — the
  issuance and service dates are deliberately blank — so the human
  choosing the dates owns it.
- **The examination date on the notice must equal the production date
  on the subpoena.** It is the date the recipient's rights expire
  against: an objection must be served before it, and a party-consumer
  must notice a § 1987.1 motion to quash at least five days before it.
  A notice stating a different date misstates the deadline, which is
  both a defect and an invitation to sanctions. The two values live in
  separate front-matter blocks (`forms.subp010.production_date` and
  `forms.subp025.production_date`) because the notice may accompany a
  subpoena the build did not produce; keeping them equal is the
  author's job.
- **Checkbox on-states are mixed.** "I object to all of my records" is
  `/1`; "I object only to the following specified records" is `/2`, as
  is every "Mail" box on page 2 whose "Personal Service" sibling is
  `/1`. Assuming `/1` throughout would leave half the boxes silently
  unchecked.
- **The role boxes are positional.** By the notice signature,
  `Ch1[0]` is REQUESTING PARTY and `Ch1[1]` is ATTORNEY; the widget
  names carry no hint. Both default off — the capacity in which a
  person signs is that person's declaration, not the machine's.
- **One recipient may need two names on one notice.** Where the
  consumer is represented in the action, the notice must reach the
  attorney too; the customary practice is a single notice addressed to
  both ("JOHN SMITH and his attorney of record, PAT COUNSEL"), which
  is why the `consumer` value is free text rather than a parsed name.
- **Notices are separate files by necessity, not convenience.**
  Merging them into the subpoena would send each consumer the other
  consumers' notices — disclosing whose records are being sought to
  people with no right to know.
- **Some records need more than notice.** Medical and psychotherapy
  records may require the patient's written authorization or a court
  order; a notice does not cure a privilege problem.
