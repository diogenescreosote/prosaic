# ADR-0046: Form-layer filling removed; overlay is the only form technology

**Status:** Accepted (September 10, 2026)

Supersedes the legacy-list clause of
[ADR-0037](0037-no-acroform-filling.md), which prohibited authoring a new
descriptor the AcroForm way but kept a shrinking list of forms that still
filled through the PDF form layer, each printing a warning on use.

## Context

ADR-0037's reasoning stands in full: **how a form-layer fill renders is a
property of the viewer, not of the file.** What it kept was a transition:
thirteen forms, eight in this repository and four in the family-law
module, still wrote values into widgets, stripped XFA packets, set
`/NeedAppearances`, and pinned `/DA` font sizes, on the theory that a
warning on every use was better than blocking a filing.

The warning did not work as a control. A SUBP-025 was filled through the
form layer on September 10, 2026, warning and all, and the attorney block
rendered three of its four lines: the engine judged a 9-point block to fit
a 45-point box at its own leading, and the viewer, laying the text out
itself with its own leading and inset, clipped the city line. Nothing in
the file was wrong — the value carried all four lines — which is exactly
the class of defect ADR-0033 named, and exactly what a warning cannot
catch: the artifact looked filled.

Keeping two code paths also kept two sets of tests, two descriptions in
every document, a descriptor key (`technology: acroform | xfa | overlay`)
whose only safe value was one of three, and a per-field `method:` escape
hatch that existed to work around form-layer failures overlay does not
have.

## Decision

1. **There is one technology.** `pleading/form_fill.py` draws every value
   as page content at its rectangle and flattens the output. The
   form-layer path — value writing, XFA stripping, `/NeedAppearances`,
   `/DA` edits, checkbox `/V`/`/AS` — is deleted, not disabled.

2. **`technology: overlay` is required, explicitly.** A descriptor with any
   other value, or with no `technology` key, is refused at load with a
   message naming this ADR. There is no legacy list.

3. **Every descriptor that was on the legacy list is migrated**: `civ110`,
   `efs020`, `mc025`, `mc030`, `mc050`, `subp001`, `subp002`, `subp010`,
   `subp025` here; `fl323`, `fl327`, `fl330`, `fl335` in the family-law
   module. Migration is a one-line change to the descriptor because a
   `map:` already names the widget whose rectangle overlay borrows;
   what makes it a migration is the fill-render-look pass on each
   form's page 1 that accompanies it.

4. **Text is centered in its box by default.** A single-line value is
   drawn centered horizontally and vertically in its rectangle: a name
   on a signature line sits on the line, a case number in its box sits
   in the box. A block of several lines anchors top-left. Descriptors
   pin exceptions per field with `align: left | center | right` and
   `valign: top | middle | bottom`. The rule was set by looking at a
   filled SUBP-025: "when there's a line to put stuff, try to center the
   text on the line; when there's a box, center it in the box."

5. **Fit is measured against our own leading.** Because the engine draws
   the lines, the height a block needs is known exactly; no allowance for
   a viewer's layout is made because no viewer lays anything out. A
   widget's multiline flag is still read from the blank, as geometry: a
   multiline box wraps a long value rather than shrinking it to one line.

6. **Tests read the page, not the form.** Assertions about a filled form
   inspect rendered text (`pdftotext`, pymupdf) and rasterized pages;
   nothing reads a field value back, because there are none to read.

## Consequences

- A filled form has no live fields. It cannot be typed into and nothing
  can read a value out of it; both are correct for a filing copy, which
  is a print-equivalent artifact.
- `chrome_fields:` remains, for non-button chrome that the bake would
  otherwise ink into a filing; pushbuttons are recognized and stripped
  without being listed.
- `sc form fields <blank.pdf>` scaffolds `technology: overlay`; the
  descriptor schema no longer has a `method:` key.
- Hand-authored `rect:` entries remain the drift surface ADR-0033 named,
  and `sc form preview` remains the geometry check. A migrated form is
  not done until someone has looked at a fill.
