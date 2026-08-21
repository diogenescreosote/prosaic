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
```

## Why "just fill the PDF" doesn't work

JC forms are fillable PDFs in theory. In practice, filling them the
normal way produces filings that look right in one viewer and broken
on the clerk's screen. Failure modes we've hit, and the engine's
countermeasures:

| Failure mode | What you see | Countermeasure |
|---|---|---|
| Appearance streams don't regenerate | Filled values invisible in some viewers | `/NeedAppearances` set on every output |
| XFA layer shadows the AcroForm | Form renders *blank* in XFA-aware viewers despite filled values | `technology: xfa` → the XFA layer is stripped so all viewers read the AcroForm |
| Auto-size fields (`0 Tf`) | Microscopic or out-of-view text | Engine measures the text and pins an explicit font size (`/DA`) |
| Text longer than the box | Silent clipping — words simply vanish | `fit:` strategies — `shrink`, `wrap`, `shrink_wrap`, and `overflow_attachment` (below) |
| Field names lie | `Dismissal_Type_cb3` is actually "with prejudice" | Descriptors document the *verified* meaning; names are treated as opaque IDs |
| Caption repeats per page as separate fields | Page 3's caption silently blank | Descriptor maps every occurrence; each binds the same `auto:` value |
| Broken/missing widgets | Value lands nowhere, or in the wrong place | `method: overlay` — draw the text directly at a rectangle, ignoring the widget |
| Interactive chrome on filing copies | "Clear this form" buttons, privacy banners | `chrome_fields:` stripped from output |
| Silent form revisions by the JC | Field names change; everything above, silently | `test_descriptor_matches_blank` fails loudly; descriptors record the verified `revision` |
| All of the above, viewer-dependently | The same filled PDF looks right in one viewer, wrong in another | `technology: overlay` — values are drawn as ordinary page content at each widget's rectangle and the output is **flattened** (no AcroForm at all), so every viewer renders identical ink |

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
technology: acroform         # or xfa (strips the XFA layer), or
                             # overlay (draw everything, flatten; below)
chrome_fields: [Save, Print, ResetForm]

# technology: overlay only — abstract signer roles, in signing order;
# fields reference them via esign: {type: ..., party: ...}
esign_parties: [filer, server]

fields:
  case_number:
    map: "SUBP-010[0].Page1[0].CaseNumber[0]"  # AcroForm/XFA field name
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
  broken_field:
    method: overlay          # ignore the widget; draw at rect
    page: 2
    rect: [72, 640, 540, 700]   # PDF points, [x0, y0, x1, y1]
    fit: shrink_wrap
    font_size: 9
    min_font_size: 6
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

## `technology: overlay` — flattened fills (ADR-0033)

AcroForm rendering is viewer-dependent no matter how carefully values
are set: appearance streams go stale, `/NeedAppearances` support
varies, and an inherited `/V` from a group node can make untouched
sibling fields render garbage. Under `technology: overlay` the engine
never sets a field value at all. Each `map:` names its widget only to
borrow the widget's **rectangle**; the value is drawn as ordinary page
content (checkboxes get a centered bold X), and the output is
flattened — no AcroForm dictionary, no widget annotations, identical
rendering everywhere. Fields with no widget (signature lines) carry a
hand-authored `rect:`.

Sizing under overlay balances fit against consistency: a field with no
explicit `fit:` defaults to `shrink`, and fields sharing a
`size_group:` all render at the smallest size any member needed, so a
block of related boxes never shows three different type sizes.

Fields may carry an e-sign tag — `esign: {type: date, party: filer}` —
marking areas reserved for signing rather than machine fill. The type
taxonomy (`signature`, `initials`, `date`, `name`, `email`, `phone`,
`text`, `checkbox`) is the least common multiple of DocuSeal, DocuSign,
and Dropbox Sign field types, so a descriptor's e-sign map can drive
`sc docuseal` (or any platform) without translation loss. Parties are
abstract roles declared in `esign_parties:`, in signing order.

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
