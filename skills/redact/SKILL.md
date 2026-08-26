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

Two granularity errors, the traps that have actually bitten, and the full
map of who is protected are in `specs/redact.md`. Read that spec before a
first redaction; the loop above is the part you run every time.

## The term list

`verify_redactions.py` is only as good as its terms, and the terms are
a legal judgment, not a technical one. Derive them from the schedule:
every proper name, facility, program, diagnosis, medication, statutory
hold, date of treatment, licence number, and identifier that the relief
covers. One per line; prefix `re:` for a regex.

Keep the term list in the matter beside the configs and under version
control. It is the written statement of what must not survive, so it is
reviewable on its own.

What redaction does and does not do, in tool terms, is in
`specs/redact.md`.

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
