# Spec: the Judicial Council form system

## Purpose

A person in a California case should be able to produce a filled,
filing-ready Judicial Council form from structured data — without
knowing PDF internals, without discovering the hard way that the
form's fillable layer is broken, and without a rejected filing being
the first signal that something didn't fit. The long-term ambition is
coverage of every JC form (then federal and other states); the design
must therefore make adding a form a matter of *describing* it, never
of programming.

## Promises

1. **What you put in is what the court sees.** Every value supplied
   lands in the intended box, fully visible in common viewers
   (Adobe, Preview, browser, poppler — including clerk-side stacks
   that don't regenerate appearances). No silent clipping, no
   invisible text, no microscopic auto-sizing.
   *(tested: scenario form_filling — deterministic + AI visual)*
2. **Nothing is signed, dated, or decided by the machine.** Signature
   lines, date-of-signature lines, role checkboxes, and court-use
   fields (hearing details, judicial officer) are always left blank
   for the human or the court. *(tested)*
3. **Text that cannot fit becomes a proper attachment.** Rather than
   shrinking below legibility or truncating — either of which changes
   what the court reads — overflow produces "See Attachment N." plus a
   correctly captioned MC-025 appended to the output, per California
   practice. Related "attached / listed below" checkboxes reflect what
   actually happened. *(tested)*
4. **A form revision cannot hurt silently.** Each descriptor records
   the revision it was verified against, and the test suite fails
   loudly when the shipped blank stops matching the descriptor.
   *(tested: test_descriptor_matches_blank)*
5. **Every form teaches its own use.** A descriptor carries an
   `agent_guide` sufficient for a competent agent (or person) who has
   never seen the form: when to use it, field semantics, sensible
   combinations, what stays blank. *(tested: registry-wide invariant)*
6. **Filled forms remain interactive** (fields stay live for
   downstream correction) and carry no interactive chrome (buttons,
   privacy banners) that doesn't belong on a filing.
7. **A form a filing needs one of per person is produced per
   person.** Some Judicial Council forms are not one-per-filing:
   SUBP-025 must be filled and served once for each consumer or
   employee whose records a subpoena reaches. The pleading build takes
   that list from the source's front matter and emits one filled,
   individually addressed form per recipient, alongside — never inside
   — the document that requires them (specs/pleading/generator.md,
   promise 11). *(tested: form_filling scenario)*

## Non-obvious constraints

- **Field names lie; only verification is trusted.** JC field names
  are frequently mislabeled relative to their own tooltips and visual
  position (documented cases: SUBP-010's `HearingDate_dt` is the
  production deadline, not a hearing date, and its `HearingDept_ft` is
  the deposition officer, not a department). A descriptor entry is
  legitimate only after an empirical fill-render-inspect pass; no
  mapping may be inferred from a name.
- **XFA forms must have their XFA layer stripped** — otherwise
  XFA-aware viewers show the *unfilled* template while the AcroForm
  layer silently carries values.
- **The blank is part of the artifact.** Fills run against the blank
  shipped in-repo (pinned revision), never against whatever
  courts.ca.gov serves today.
- **Original blanks are never modified in place**; filling clones.
- Captions repeat per page as independent fields on multi-page forms;
  all copies must be filled.

## Per-form specs

Each registered form has a sibling spec (`subp010.md`, `mc030.md`, …)
stating what the form is for in the legal process, who files it and
when, and the form-specific constraints a filler and its tests must
honor. The descriptor's `agent_guide` is the operational summary; the
spec is the authority it summarizes.
