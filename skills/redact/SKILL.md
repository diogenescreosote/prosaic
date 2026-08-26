---
name: redact
description: Produce a verified redacted or sealed version of a filing from a declarative JSON schedule - choose redaction units, build with redact_pdf.py, prove the withheld text is gone with verify_redactions.py, and hand a human a reviewable render. Use when asked to redact, seal, strike, or prepare a public version of any PDF, or to check that an existing redacted PDF actually withholds what it claims.
---

# Redact a filing

Redaction is the one task where a confident-looking result and a
catastrophic result are the same picture. A drawn rectangle looks
exactly like a removal. A covered name is still selectable. A row whose
name you covered still carries the phone number two cells over. So the
discipline here is not "apply the boxes" — it is **declare, build,
prove, show**.

Never hand-place boxes ad hoc, and never report a redaction as done on
the strength of having looked at it.

## The loop

1. **Declare.** Write a JSON schedule under `src/redactions/<name>.json`.
   One entry per item, each with a `description` naming the item and its
   basis, and an `item` naming the identifier in the human-facing
   schedule that authorises it. The schedule is the work product; the
   PDF is its output.
2. **Build.** `python3 <prosaic>/pleading/redact_pdf.py <cfg>.json --force`
   Every entry must match. If any finds nothing the build writes no
   output and exits nonzero — a success means every listed entry applied.
3. **Prove.** `python3 <prosaic>/pleading/verify_redactions.py <out>.pdf
   --terms <terms>.txt --config <cfg>.json --report <report>.md
   --contact-sheet <dir>/`
   Exit 0 only when nothing in the term list survives in the text layer,
   the annotations, the metadata, or the raw bytes.
4. **Reconcile.** `python3 <prosaic>/pleading/check_redaction_schedule.py
   <the letter or motion>.md src/redactions/*.json`
   Every operation must cite an item the schedule enumerates.
5. **Show.** Give the human the contact sheet and the report, and say
   plainly what is machine-verified and what is only your judgment.

Steps 2, 3 and 4 are not optional and not reorderable. Verification and
reconciliation are part of producing the artifact.

### Identifiers must be stable per section

Use `A1`, `B2`, `C12` --- never one running `1..N`. A schedule gets edited
for argument, so rows get dropped and narrowed; with a single sequence,
dropping one row renumbers every row after it and silently invalidates
every config label downstream, while both files still look internally
consistent. That happened: two rows were dropped from a 51-item
schedule and every config label from that point on pointed at the wrong
item, with nothing to reveal it.

The drift is a legal problem, not bookkeeping. A redaction the schedule
does not enumerate is relief nobody asked the court for, applied anyway.
An enumerated item nothing implements is relief asked for and not
delivered. Expect the configs to find material the schedule missed ---
they are written while reading the documents --- and feed it back into
the schedule rather than leaving it implemented but unauthorised.

## Pick the right unit

This is where redactions actually fail. Match the unit to the
structure of the thing, not to the phrase you happened to search for.

| Structure | Op | Why |
|---|---|---|
| Ruled table (witness list, exhibit list, schedule of assets) | `redact_row` | A row's identifiers live in its other cells |
| One cell of a table | `redact_row` with `"scope": "cell"` | Bounded by the vertical rules |
| Whole exhibit, or a known page span | `seal_page_range` | Explicit pages, no anchor to misfire |
| A paragraph | `redact_block` (start/end on one page) | Full column width, top of first hit to bottom of last |
| A clause inside a sentence | `redact_clause` | Redacts **every** match document-wide |
| Signature, handwriting, stamp, photo, OCR noise | `redact_region` | Explicit page + 0–1 page fractions |
| A page span found only by its text | `seal_pages` | Last resort — see the traps |

### The two granularity errors, which are opposites

Both are easy to make in the same document, and each looks like care.

**In a table, go wider than the phrase.** Covering a clinician's name
while leaving their street address and direct line in the next two
cells redacts nothing: the row identifies the person several times
over, and an address plus a phone number identifies them without any
name at all. If the anchor sits in a table, `redact_row` is the default
and anything narrower needs a stated reason.

**In prose, go no wider than the fact.** Redact the minimum phrase that
carries the protected material, not the line or the sentence containing
it. A line reading

> Mother asserts that Father's chronic mental instability, as well as his history of domestic

needs exactly `chronic mental instability` removed. Covering the line
also removes "Mother asserts that Father's" and half of an unrelated
allegation, and it does so for no reason: a redaction that takes more
than its justification supports invites the response that the whole
schedule is overreaching, and the reader can see it.

**A word naming a category is not a disclosure of anything.** This is
the third granularity error and the most common false positive. A
sentence reading

> Mother, or his own providers about his diagnoses or treatments. For this reason, the Parties

contains the words "providers", "diagnoses" and "treatments" and
discloses no provider, no diagnosis and no treatment. There is nothing
to redact. Protected material is the *specific fact* -- this diagnosis,
that facility, those dates -- never the vocabulary used to refer to the
category in the abstract. Procedural sentences about disclosure,
consent, releases and discovery are full of that vocabulary and are
almost never redactable.

Never generate prose redactions -- or a term list -- by sweeping for a
keyword pattern. A pattern cannot tell a treating psychiatrist from the
court's own evaluator, nor a disclosed diagnosis from the word
"diagnosis", and it will redact all of them.

Never generate prose redactions by sweeping lines that match a keyword
pattern. That is line granularity wearing the costume of precision: it
is simultaneously too wide (it eats neighbouring text) and too narrow
(it stops at a line break, so the second half of a wrapped phrase
survives). Author the phrase list by reading the passage, then let
verification catch the wrapped remnants.

## Traps that have actually bitten

- **`seal_pages` searches case-insensitively and takes the first match
  in the whole document.** An anchor of `EXHIBIT A` matches a body-text
  "(See Exhibit A.)" nine pages earlier and seals the wrong pages while
  reporting success. Use `seal_page_range` whenever the pages are known.
  Reserve `seal_pages` for when they genuinely are not, and verify the
  anchor is unique first.
- **`redact_clause` hits every occurrence in the document.** Good for a
  name sweep, dangerous for a short string: `"plan."` catches "treatment
  plan", "safety plan", and "planned". Check the match count before
  committing to a short clause.
- **Ops run in order and each applies immediately.** A later op can find
  nothing because an earlier one already removed its text — which then
  fails the build. Put document-wide sweeps **last**, and page seals
  **before** the line-level work on those same pages.
- **Line-level redaction of an OCR layer leaves ragged edges.** The text
  layer is registered to the image but wraps differently, so fragments
  survive: an orphaned `hospitalizations:` after the list above it went,
  a surname stranded when its line was covered. Verification catches
  these; expect a second pass.
- **A label can disclose the thing it removes.** `[HOSPITALIZATION
  CATALOG SEALED]` tells the reader the fact you just withheld. Labels
  name the *authority and item number*, never the content:
  `[ITEM 5 -- SEALED]`.
- **Base-14 label fonts encode Latin-1.** An em dash renders as `?` on
  the page. `sanitize_label` now folds typographic punctuation
  automatically, but do not rely on it: write labels in plain ASCII.
  House form is a colon, `[ITEM 23: SEALED]` --- not a dash of any
  width.

## Who is actually protected

Not everyone with a title is a covered provider, and this is a legal
question that no keyword pattern can answer. Getting it wrong in the
generous direction is not "safe" -- it redacts material nobody has a
right to withhold, and it tells the reader the schedule was assembled
carelessly.

- **Treating providers** -- the therapist, the psychiatrist, the
  hospital, the clinic. Identity, contact details, dates of contact and
  everything they learned or opined are in scope.
- **Court-appointed neutrals** -- the court's appointed evaluator, the
  forensic examiner, counsel for a minor, a mediator. **Not** treating
  providers.
  Their identity is a matter of public record in the case and carries no
  privilege. Do not redact their names, and do not redact the fact of
  their appointment or the existence of their evaluation. What they
  *report about diagnosis or treatment* may still be protected; who they
  are is not.
- **Supervisors, monitors, and lay third parties** -- not providers.
  Their descriptions of someone's mental state may be protected as
  medical privacy even so, since that interest does not depend on a
  clinician being the source. Their own names usually are not.

A provider who is court-*involved* (a therapist the parties engaged and
the court knows about) is still a treating provider. A provider the
court *appointed to examine* is not. The distinction is the function,
not the docket.

Decide this per person, in writing, in the config's `_comment`. Then
build the term list from those decisions.

## The term list

`verify_redactions.py` is only as good as its terms, and the terms are
a legal judgment, not a technical one. Derive them from the schedule:
every proper name, facility, program, diagnosis, medication, statutory
hold, date of treatment, licence number, and identifier that the relief
covers. One per line; prefix `re:` for a regex.

Keep the term list in the matter beside the configs and under version
control. It is the written statement of what must not survive, so it is
reviewable on its own.

## What redaction does and does not do

`apply_redactions(graphics=1)` genuinely deletes the underlying text and
image content — this is removal, not covering. But:

- **An image-only page cannot be verified by search.** No text layer
  means nothing to find, and silence is not safety.
  `verify_redactions.py` reports such pages and exits nonzero unless
  `--allow-image-only`. They need eyes on the render.
- **Redact the `_ocr` sibling for scans.** The as-filed scan has no text
  layer, so there is nothing to search or remove. The OCR layer is
  registered to the image, so the boxes land correctly and the image
  beneath them goes too.
- **Sealing and striking are different remedies.** Struck material is
  removed from consideration; sealed material stays available to the
  court but leaves the public file. Say which each entry is, in its
  `description`, and keep the placeholder text consistent with it.

## Source hygiene

Redact **from the court-filed version**, never from a working copy
someone has already marked up. Check `pleadings/MANIFEST.md` first and
run `pleadings_manifest.py <matter>`; if the source is a substitute or
unverified, say so in the config's `_comment` and in what you report.

Two files being byte-identical proves only that they are the same file.
It is not evidence that either came from the court.

## Reporting

Say which of these is true, separately, because they are different
claims:

- the build applied every declared entry (mechanical)
- verification found no surviving term in any carrier (mechanical)
- the schedule covers the right material (**judgment, unverified**)

The third is the one a human must check. Never let the first two imply it.
