# Judicial Council form filling

A shocking fraction of litigation is
filling out Judicial Council (JC) forms. prosaic treats each form
as **data**: a YAML descriptor that records where every field lives,
how it breaks, and what to do about it. One engine
(`pleading/form_fill.py`) executes all descriptors; adding a form
means writing YAML, not Python.

```bash
sc form list                 # registered forms
sc form info subp010         # a form's agent guide + field schema
sc form fill mc030 --meta caption.yaml --data values.yaml -o out.pdf
sc form fields blank.pdf     # introspect a new blank → descriptor skeleton
sc form preview mc040 -o preview.pdf   # geometry check: colored boxes over every fillable/e-sign area
sc form check                # fill + preview every registered form; exit 1 on any failure
PROSAIC_LAYERS_ROOT=/path/to/deployment sc form check   # same, against that deployment's local/ and modules/ descriptors
```

## Why "just fill the PDF" doesn't work

JC forms are fillable PDFs in theory. In practice, how a value written
into a PDF's form layer renders is a property of the viewer, not of the
file: appearance streams go stale, auto-size text vanishes, multiline
boxes clip their last line, an inherited value on a group node makes
untouched siblings render garbage, XFA-aware viewers show the blank
template, and a page-level merge into a packet drops the form
dictionary altogether. A filing that looked right on the author's
screen reaches the clerk saying something else.

So prosaic never writes a form value (ADR-0037, ADR-0046). Every field
is **drawn** as ordinary page content at its rectangle — a `map:` names
a widget on the blank only to borrow its geometry — and the output is
**flattened**: widget appearances are baked into the page, every widget
annotation and the form dictionary are removed, viewer chrome is
stripped first so it is never baked in. What is filed is ink that
renders identically everywhere. The remaining failure modes, and the
engine's countermeasures:

| Failure mode | What you see | Countermeasure |
|---|---|---|
| Text longer than the box | Silent clipping — words simply vanish | `fit:` strategies — `shrink`, `wrap`, `shrink_wrap`, and `overflow_attachment` (below); a multiline widget wraps under `shrink` |
| Text floating in its box | A phone number far from "TELEPHONE NO.:"; a name flush left above its signature line; a case number tucked in a corner | The blank's own labels, rules and cells decide: beside the label, centered on the rule, centered in the cell; blocks anchor top-left; `layout:`/`align:`/`valign:` pin exceptions |
| Field names lie | `Dismissal_Type_cb3` is actually "with prejudice" | Descriptors document the *verified* meaning; names are treated as opaque IDs |
| Caption repeats per page as separate fields | Page 3's caption silently blank | Descriptor maps every occurrence; each binds the same `auto:` value |
| No widget where the value goes | Signature-line names, hand-drawn boxes | A hand-authored `rect:` on the field |
| Two widgets share one name | A radio pair; only the first is ever found by name | A hand-authored `rect:` on the checkbox |
| Interactive chrome on filing copies | "Clear this form" buttons, privacy banners | Pushbuttons are recognized and stripped; other chrome is listed in `chrome_fields:`; `whiteouts:` paint over static junk |
| Silent form revisions by the JC | Field names change; everything above, silently | `test_descriptor_matches_blank` fails loudly; descriptors record the verified `revision` |
| Geometry that is simply wrong | The right value drawn in the wrong box | `sc form preview` — look before trusting any fill |

## Overflow: the legally correct escape hatch

When text can't fit even after shrinking, truncating it would change
the meaning of a court filing. The correct practice is the JC's own:
put **"See Attachment N."** in the field and attach an **MC-025**
(Attachment to Judicial Council Form) carrying the full text. Fields
marked `fit: overflow_attachment` do this automatically — the engine
fills MC-025(s) with the overflow and appends them to the output. You
still proofread the result like anything else you file.

## Using forms from a pleading source

Three patterns, all driven by the source file's YAML front matter:

**Cover sheet** — prepend a filled form to a rendered pleading:

```yaml
cover_sheet: mc030      # any registered form
```

**Explicit field values** — the `forms:` block overrides any
auto-derived value, using the descriptor's logical field names:

```yaml
forms:
  subp010:
    records_description: >
      The records demanded, at whatever length; overflow goes to
      Attachment 3 automatically.
    method_mail_to_officer: true
```

**Companion notices** — some forms are one-per-*person*, not
one-per-filing. A records subpoena that reaches an identifiable
individual's records is invalid unless that person is separately
served with a Notice to Consumer or Employee (SUBP-025) and a copy of
the subpoena (Code Civ. Proc. §§ 1985.3, 1985.6). List the recipients
and the build emits one filled, individually addressed SUBP-025 per
entry *beside* the document's PDF — never merged into it, because each
goes to a different person:

```yaml
cover_sheet: subp010
forms:
  subp025:                      # shared by every notice
    requesting_party: "JANE ROE, Respondent"
    production_date: "September 15, 2026"    # must match the subpoena
    witness: "Custodian of Records, Example Bank, N.A., 500 Market Street, …"
consumer_notices:
  - consumer: "JOHN SMITH"
  - consumer: "MARY MAJOR"
    slug: mary_major            # optional; default is slugified consumer
    witness: "Custodian of Records, Example Employer, Inc., …"
```

Outputs land next to the source's own PDF as
`<stem>.subp025.<slug>.pdf` — here `Subpoena to Example
Bank.subp025.john_smith.pdf` and `….subp025.mary_major.pdf`. Each
entry may override any SUBP-025 field or checkbox for that recipient.
A missing `consumer`, an unknown field name, or two recipients whose
slugs collide fails the build rather than shipping a packet with a
notice missing. The full schema is in
`pleading/pleading_markdown_spec.md`; the service clocks are in
`sc form info subp025`.

Everything else — attorney block, court block, parties, case number —
derives from the same caption front matter every pleading already has
(`filer_name`, `court_county`, `petitioner`, …) via `auto:` bindings
(see `pleading/jc_common.py`).

**For AI agents:** `sc form info <id>` prints the descriptor's
`agent_guide` — when to use the form, what each field means, which
checkbox combinations make sense, and what must stay blank (dates,
signatures, role checkboxes are *always* left for the human). Read it
before filling a form you haven't used.

## Descriptor schema

```yaml
form: subp010                # id = registry filename
title: Deposition Subpoena for Production of Business Records
domain: ca/civil             # ca/general, ca/civil, …
revision: "2020-01"          # the JC revision this map was VERIFIED against
source_url: https://courts.ca.gov/documents/subp010.pdf
blank: subp010.pdf           # under pleading/forms/
technology: overlay          # required, and the only value (ADR-0046)
chrome_fields: [Save, Print, ResetForm]   # non-button chrome to strip
                                          # before the bake (optional)

# Abstract signer roles, in signing order; fields reference them via
# esign: {type: ..., party: ...}
esign_parties: [filer, server]

fields:
  case_number:
    map: "SUBP-010[0].Page1[0].CaseNumber[0]"  # the blank's widget, for geometry
    page: 1
    doc: "Case number"
    auto: case_number        # caption binding (jc_common.AUTO_BINDINGS)
  facts_in_support:
    map: "..."
    doc: "Item 9 — facts supporting the requested orders"
    fit: overflow_attachment
    attachment_label: Attachment 9
    overflow_checkbox: attachment_9      # checked iff the value spilled
    inline_checkbox: facts_listed_below  # checked iff it fit on-form
  phone:
    map: "..."
    layout: labeled          # normally detected from the blank (labeled |
                             # line | box); pin it when the geometry is
                             # ambiguous. align:/valign: override outright.
  signature_line_name:
    page: 2
    rect: [72, 640, 540, 700]   # no widget: PDF points, [x0, y0, x1, y1]
    fit: shrink_wrap
    font_size: 9
    min_font_size: 6
    valign: bottom
  date:
    map: "..."
    doc: "LEAVE BLANK — hand-dated at signature"
    default: ""

checkboxes:
  method_mail_to_officer:
    map: "...Method1_cb[0]"
    on_value: "/1"           # verified widget "on" state
    doc: "Item 1a — mail copies to the deposition officer"

agent_guide: |
  Free text for humans and AI agents: when to use this form, field
  semantics, what stays blank, front-matter examples.
```

Value precedence, low → high: field `default` → `auto` binding over
the front matter → `forms.<id>.<field>` block → explicit `--data` /
API data dict. Unknown keys in data are *reported*, not ignored.

## `technology: overlay` — the only kind of fill (ADR-0033, ADR-0046)

The engine never sets a form value. Each `map:` names its widget only
to borrow the widget's **rectangle** (and its multiline flag); the
value is drawn as ordinary page content (checkboxes get a centered
bold X), and the output is flattened — no form dictionary, no widget
annotations, identical rendering everywhere. Fields with no widget
(signature lines) carry a hand-authored `rect:`. A descriptor must say
`technology: overlay`; any other value, or none, is refused at load.

Sizing balances fit against consistency: a field with no explicit
`fit:` defaults to `shrink`, and fields sharing a `size_group:` all
render at the smallest size any member needed, so a block of related
boxes never shows three different type sizes. Because the engine draws
the lines itself, the height a block needs is exact — first baseline
one em below the top, then 1.15 em per line — and nothing is left to a
viewer's layout.

Placement: the engine reads what the blank prints around each field
and places a single-line value accordingly — beside its label
(`labeled`: left, vertically centered), centered on its signature rule
(`line`), or centered in the free area of its bordered cell (`box`,
under a "CASE NUMBER:"-style label); with none of those it centers in
the widget's rectangle. A block of lines (an address, a wrapped answer)
anchors at the top left. `layout: labeled | line | box`, `align: left |
center | right` and `valign: top | middle | bottom` on a field pin the
exceptions; `sc form fill <id> ... --verbose` prints every decision and
the geometry behind it, so decide overrides by looking at a fill.

Fields may carry an e-sign tag — `esign: {type: date, party: filer}` —
marking areas reserved for signing rather than machine fill. The type
taxonomy (`signature`, `initials`, `date`, `name`, `email`, `phone`,
`text`, `checkbox`) is the least common multiple of DocuSeal, DocuSign,
and Dropbox Sign field types, so a descriptor's e-sign map can drive
`sc docuseal` (or any platform) without translation loss. Parties are
abstract roles declared in `esign_parties:`, in signing order.

## Two signing paths, and the date trap

A signed pleading takes one of two routes, and they want opposite
things from the build:

- **DocuSeal (remote, audit-trailed).** Build `--final` with no
  `sign_date`. The signature-block macros emit e-sign field tags into
  the `<pdf>.fields.json` sidecar (or embedded tags in `esign: tags`
  mode); `sc docuseal send` places DocuSeal's own signature *and date*
  fields there, and DocuSeal fills both when the signer acts. The date
  is a placed field the platform owns — never bake it. The sidecar is
  the build's to write, never a person's: `md_pleading` writes it for
  every `\signblock`, and `sc form fill` writes it for any form whose
  descriptor carries `esign:` fields (SUBP-025, FW-001, MC-030, MC-040,
  EFS-050 do), each stamped `"source": "build"`. `sc docuseal send`
  refuses a sidecar without that stamp unless `--allow-hand-fields` is
  passed, and refuses any sidecar — stamped or not — whose box covers
  printed text or straddles the rule it should rest on. A source that
  types `Date: ____ / Signature: ____` as prose gets no geometry at all;
  use `\signblock{dated}{NAME}{ROLE}` and the boxes land above the rules
  with the name printed beneath them.

- **Preview / wet ink (local).** Build `--final` with `sign_date:`
  (`today` or an ISO date) in the source. The macros then draw the
  signer's execution date as **page content** ("Executed this 3rd day
  of September, 2026, at …"), leaving only the signature rule blank for
  an ink mark. This exists because e-filing portals (Odyssey/eFileCA)
  re-flatten every upload and **drop typed FreeText annotations while
  keeping ink signatures** — a date hand-typed onto a blank rule in
  Preview vanishes at the clerk while the signature survives, yielding
  an undated declaration. Baking the date as content makes it
  unlosable. `sign_date` fires only on `--final` (a draft must never
  look executed) and never touches a judge block (the court dates its
  own signature). If you must annotate a date in Preview anyway,
  flatten before upload (`File → Print → Save as PDF`) so it becomes
  content.

**Geometry preview** — the visual sanity check that must precede
trusting any new adapter: `sc form preview <id> -o preview.pdf` renders
the blank with a translucent labeled box over every place the
descriptor can put ink — text fields blue, checkboxes purple, e-sign
areas color-coded by party and labeled by TYPE — plus a color legend.
Open it, look, fix the rects, look again.

## Authoring a new form (the workflow that keeps this honest)

1. **Get the blank** from courts.ca.gov into `pleading/forms/` and
   record the revision date printed on the form face.
2. **Introspect**: `sc form fields pleading/forms/<id>.pdf` dumps every
   widget (name, page, rect, tooltip, checkbox states, multiline flag)
   as a descriptor skeleton.
3. **Look at the form**: rasterize (`pdftoppm -png`) and match widgets
   to what the form actually says. Tooltips help; they also lie.
4. **Check the geometry**: `sc form preview <id> -o /tmp/p.pdf` and
   open it — every box should sit on the line it fills, and e-sign
   areas should cover the signature/date/name lines for the right
   party. AI-authored adapters get geometry wrong in ways only eyes
   catch; this view exists to catch them before a fill ever runs.
5. **Verify empirically** — the non-negotiable step: fill every text
   field with its own logical name, rasterize, and *look*. Wrong
   guesses are obvious ("attorney_for" rendered in the fax box).
   Iterate until every label lands in its box, then do the same for
   each checkbox's `on_value`.
6. **Write the `agent_guide`** while the form's semantics are fresh:
   the guide is what makes the descriptor usable by someone (or
   something) that has never seen the form.
7. **Run the tests** (`uv run pytest pleading/tests -q`). The suite
   checks every descriptor against its blank (names, checkbox states),
   smoke-fills every form, and exercises fit/overflow behavior.
8. **Proofread a real fill** before first courtroom use. Tests catch
   drift and plumbing errors; only eyes catch "this answer belongs in
   Item 3b, not 3a."

## Coverage and roadmap

Current registry: `mc030` (declaration), `mc025` (attachment),
`mc050` (substitution of attorney—civil, without court order),
`civ110` (request for dismissal), `efs020` (e-filing cover),
`subp010` (deposition subpoena for production of business records),
`subp025` (notice to consumer or employee and objection),
`mc040` (notice of change of address — the `technology: overlay`
pilot).

The near-term goal is broad general-civil coverage; the descriptor
format is deliberately
jurisdiction-agnostic (nothing in the engine knows about California),
so federal and other-state form families are a matter of registry
growth, not engine work. Contributions: one descriptor + verification
evidence per PR (see CONTRIBUTING.md).
