# ADR-0037: AcroForm filling is prohibited; overlay is the only technology

**Status:** Accepted (August 26, 2026)

Supersedes the migration clause of
[ADR-0033](0033-overlay-form-technology.md), which introduced
`technology: overlay` as something a descriptor **may** opt into and left
existing AcroForm and XFA descriptors to "migrate opportunistically."

## Context

ADR-0033 established why overlay is right: **how an AcroForm fill renders
is a property of the viewer, not of the file.** Every countermeasure
narrows the variance and none eliminates it, and the failure that
prompted it — a checkbox value written on a shared parent node making
untouched sibling text fields render "1" in some viewers — is invisible
to value-level inspection, because the values are correct.

What ADR-0033 got wrong was the disposition. Making overlay opt-in, with
legacy descriptors migrating when convenient, meant the repository kept
two ways of filling a form: one whose output is knowable and one whose
output is a guess about someone else's PDF reader. Opportunistic
migration is not a plan, and eleven months of it produced eleven forms
still on the old path.

The cost is not hypothetical and it is not evenly distributed. These are
court filings. A field that renders differently in the clerk's viewer
than in the author's is not a cosmetic defect: it is a document that says
something other than what was reviewed and signed.

Two further consequences of AcroForm state showed up in practice this
month:

- **It does not survive assembly.** A page-level merge of a filled
  AcroForm into a packet drops most of the form dictionary. A
  request-for-order packet reached a court with every checkbox on one
  page blank, because the merge — not the fill — lost them.
- **It cannot be verified from the artifact.** Asking whether a box is
  checked means reading `/V` and `/AS` and trusting a viewer to resolve
  inheritance the same way. Drawn ink is answerable by rendering.

## Decision

1. **`technology: overlay` is mandatory.** Every Judicial Council form
   descriptor draws its values as page content and flattens the output.
   No descriptor writes AcroForm field values.

2. **A non-overlay descriptor that is not on the legacy list is a hard
   error**, raised where the descriptor loads, naming this ADR. A new
   form cannot be authored the old way, including by an agent that has
   read an older descriptor and copied its shape.

3. **The legacy list may only shrink.** `LEGACY_ACROFORM_FORMS` in
   `pleading/form_fill.py` enumerates the forms not yet migrated. Each
   load of one prints a warning saying what it renders is
   viewer-dependent. Entries come off the list as forms are migrated;
   nothing is ever added.

   As of August 26, 2026: `civ110`, `efs020`, `mc025`, `mc030`, `mc050`,
   `subp001`, `subp002`, `subp010`, `subp025`, and — in the family-law
   module — `fl323`, `fl327`, `fl330`, `fl335`.

4. **Migration is not complete until the geometry has been looked at.**
   `sc form preview <id> -o out.pdf` renders every rect the descriptor
   can ink. The recurring authoring failure is geometric — a value drawn
   in the wrong box — and no value-level test sees it.

## Consequences

- The thirteen listed forms remain viewer-dependent until migrated, and
  now say so on every use. Two are load-bearing: `fl335` is a proof of
  service by mail and `mc050` a substitution of attorney.
- Overlay outputs carry no live fields. Nothing can read values back out
  of a filed PDF, and a recipient cannot type into one. Both are correct
  for a filing copy, which is a print-equivalent artifact.
- Hand-authored `rect:` entries remain the drift surface ADR-0033 named;
  the geometry preview remains the only check.
- The warning is deliberately not a failure for listed forms. Making it
  one would break the ability to file a substitution of attorney today in
  service of a cleanliness the migration will deliver anyway.
