# Writing a form pack

A pack is the unit of jurisdiction- and practice-area-specific knowledge.
The engine (`prosaic/forms/`) knows how to read and fill AcroForms and how
to reject bad values; a pack knows what the fields of particular court
forms mean. `prosaic/packs/civil/` — six California Judicial Council civil
forms — is the reference implementation, and everything below is how it was
built.

## The interface

A pack is a `FormPack`: a name, a jurisdiction, and a tuple of `Form`s.
Each `Form` is created with `define_form`:

```python
define_form(
    number="MC-030",  # the form's official number
    title="Declaration",
    package="prosaic.packs.civil",  # where the blank PDF is packaged
    resource="blanks/mc030.pdf",
    context_type=DeclarationContext,  # the per-filing decisions
    build=mc030.build_values,  # (Matter, context) -> field values
)
```

`define_form` wraps the typed builder for the type-erased registry: your
builder keeps its precise context parameter, and the adapter's runtime
`isinstance` check is what makes calling through the registry safe.
`Form.fill(matter, context)` then produces a `FilledForm` — the exact
values written and the finished PDF bytes.

## What a form module contains

One module per form, four things in it:

1. **A context dataclass.** The case model holds what is true about the
   case; the context holds the per-filing decisions it cannot know — who
   files, what a declaration says, the date of signing, which box of a
   choice gets checked. Keep it frozen and typed; use enums for anything
   the form expresses as checkboxes.
2. **`build_values(matter, context) -> dict[str, str | bool]`.** Maps the
   case model plus the context to fully-qualified AcroForm field names.
   Text fields take strings; checkboxes take `True` (single on-state) or
   the explicit state name (`"/2"`) where the form uses numbered states.
3. **Validation.** Accumulate human-readable problems — missing case
   number, wrong party role, empty declaration body — and raise
   `FormValidationError(NUMBER, problems)` before building anything.
4. **A module docstring stating the quirks.** Official forms have them:
   misspelled field names, stale tooltips, radio groups with irregular
   on-states, read-only computed fields. The docstring is where the next
   reader learns what the mapping already discovered.

## Discovering a form's field map

The blanks ship as published, some AES-encrypted with an empty user
password (`fill_acroform` decrypts on read). To map a new form:

1. `read_fields(blank_bytes)` lists every fillable field with its kind,
   on-states, and tooltip. Judicial Council tooltips are usually accurate —
   but not always; two SUM-100 tooltips are stale text from a different
   form, so treat them as evidence, not truth.
2. Cross-check against geometry: render the blank (`pdftoppm`), and confirm
   which printed label sits beside each widget's rectangle.
3. Fill a synthetic fixture, render the result, and look at it. The golden
   tests then pin what you verified: exact expected values committed as
   JSON, and a read-back of every field from the produced PDF.

Expect traps. In the six shipped forms alone: a field literally named
`Nmae[0]`; case-type checkboxes whose on-states run `/1`–`/16`, then `/17`
inserted mid-column shifting the rest, then `/44`; mutually exclusive
choices that are independent checkboxes rather than radio groups, so
exclusivity is the builder's job; and page-2 header captions that are
read-only fields the form computes from page 1, which must not be written.

## Shared caption logic

Judicial Council forms open with the same caption block. `caption.py`
computes the semantics once (`caption_for`), and provides field builders
for the two itemized block layouts that recur across forms
(`attorney_block_fields`, `court_block_fields`). A new California form
module should start from these; a pack for another jurisdiction would
write its own equivalents.

## Adding a pack for another jurisdiction

Nothing in `prosaic/forms/`, `prosaic/documents/`, or the engine imports
from `prosaic/packs/`. A new pack is a new package: blanks, form modules,
a caption helper appropriate to that jurisdiction's forms, and a
`FormPack` registry. The deadline rules are likewise per-jurisdiction —
`prosaic/deadlines/` currently implements California's; the computation
layer (`add_court_days`, `roll_forward`, `CourtCalendar`) is generic and
reusable, and holiday calendars are data you supply.
