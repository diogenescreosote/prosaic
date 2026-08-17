# Markdown-to-California-Pleading Format Specification

This document defines the exact Markdown input expected by `md_pleading.py`, the PDF it produces, and the formatting conventions the generator is designed to satisfy.

## Purpose

The generator converts a Markdown file with YAML front matter into a filing-style PDF on U.S. Letter pages. The output is designed to match common California pleading conventions for line numbering, spacing, margins, caption-page structure, page numbering, footer placement, and exhibit handling.

It is designed around the California Rules of Court provisions governing trial-court paper format, especially:

- Rule 2.103: 8.5" × 11" pages.
- Rule 2.104: font size not smaller than 12 points.
- Rule 2.105: font style essentially equivalent to Courier, Times New Roman, or Arial.
- Rule 2.107: left margin at least 1 inch; right margin at least 1/2 inch.
- Rule 2.108: one-and-one-half or double spacing; consecutive line numbers at the left margin; at least three line numbers per vertical inch.
- Rule 2.109: consecutive page numbering at the bottom; first-page number may be suppressed.
- Rule 2.110: footer below the page number, divided from the page by a printed line, containing the paper title.
- Rule 2.111: first-page caption format, including filer information on the upper left and blank stamp space in the upper right.

The first page is also laid out to track the commonly cited caption-page convention that reserves the first 2 inches of space between lines 1 and 7 to the right of center for the clerk's filing stamp and begins the court title on line 8.

## Compliance target

The generator's defaults are:

- **Page size:** U.S. Letter, 8.5" × 11"
- **Body font:** Century Schoolbook, 12 pt (via TeX Gyre Schola, a metric-compatible free clone; TTF files bundled in `fonts/`)
- **Font variants:** regular, bold, italic, bold-italic
- **Line numbers:** 1–28 on every page of the pleading body and exhibit list, in 10 pt
- **Vertical rule:** at exactly 1.125" from the left page edge
- **Left text margin:** 1.375" (0.25" to the right of the vertical rule)
- **Right text margin:** 0.6" from the right page edge
- **Top margin:** line 1 baseline at 1.125" from the top edge
- **Bottom margin:** line 28 baseline at 1.125" from the bottom edge
- **Line spacing:** derived from the top and bottom margins across 28 lines; approximately 23.3 pt leading
- **Footer horizontal rule:** at 1.0" from the bottom edge (0.125" below the last text line)
- **Footer:** centered page number below the rule, then paper title (uppercased, regular weight) below that
- **First-page page number:** shown (page 1 is numbered)
- **Caption layout:** single-spaced (14 pt leading), independent of the 28-line grid
- **Caption structure:** filer block → court name (centered, bold) → two-column party table with `)` divider → horizontal rule → body begins on the next grid line
- **Party table left column:** party names (bold) with indented labels (Petitioner, / vs. / Respondent.)
- **Party table right column:** case number, paper title (bold, uppercased), optional subtitle, statutory basis, hearing info, concurrent filings
- **Exhibit tab sheets:** standalone U.S. Letter pages with centered exhibit label (bold, 24 pt) and title (14 pt)
- **Image exhibits:** scaled to fit within a 7.5" × 10" box and centered on a blank U.S. Letter page
- **PDF exhibits:** imported (optionally filtered by page range) and scaled to fit within the same 7.5" × 10" box and centered on a blank U.S. Letter page

That is meant to fit the statewide trial-court format rules cleanly. Local rules and department preferences still exist. Check those before filing.

## Supported input structure

The input file must be:

1. YAML front matter at the top, delimited by `---` lines; then
2. a Markdown body.

Example skeleton:

```md
---
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(510) 555-1212"
filer_email: "name@example.com"
filer_role: "Plaintiff, In Pro Per"

court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "COUNTY OF EXAMPLE"

petitioner: "JANE ROE"
respondent: "BAYSIDE MUNICIPAL TRANSIT DISTRICT"
case_number: "SCV-123456"

paper_title: "NOTICE OF MOTION AND MOTION TO COMPEL"
paper_subtitle: "[PROPOSED] ORDER; MEMORANDUM OF POINTS AND AUTHORITIES"
statutory_basis: "(Code Civ. Proc. §§ 527, 526a)"

hearing_date: "April 2, 2026"
hearing_time: "8:30 a.m."
hearing_dept: "16"
judge: "Hon. Patrick M. Broderick"

concurrent_filings:
  - "Memorandum of Points and Authorities"
  - "Declaration of Jane Roe"

exhibits:
  - shortname: "whitfield_email"
    title: "January 23, 2026 Email from Dana Whitfield"
    path: "exhibits/whitfield_email.pdf"
  - shortname: "jones_texts"
    title: "Screenshots of Text Messages with Jones"
    path: "exhibits/jones_texts.png"
---
# INTRODUCTION

This brief cites \exhibit{whitfield_email} and also refers to \exhibit{jones_texts}.

## FACTUAL BACKGROUND

More text. See *Doe v. Roe* (2024) 100 Cal.App.5th 123, 130---a case directly on point.
```

## Inline body markup

Body text supports exactly these inline constructs — this dialect is
NOT full Markdown:

| Markup | Renders as |
|---|---|
| `***text***` | bold italic |
| `**text**` | bold |
| `*text*` | italic |
| `<u>text</u>` | underline |
| `\highlight{text}` | yellow background (nests emphasis) |
| `\fixedwidth{text}` | verbatim monospace (Courier) |
| `` `text` `` | verbatim monospace — a synonym for `\fixedwidth{text}` |
| `\filelink{path}` or `\filelink{path}{text}` | monospace, underlined, carrying a relative-file link annotation (/GoToR) that opens `path` when the PDF is viewed beside its companions |
| `[^id]` | footnote reference marker |

`\fixedwidth{...}` is the construct for file paths, hashes, Bates
tokens, and code: its contents render in Courier, are taken verbatim
(no nested emphasis parsing), and are exempt from every typographic
substitution (`---`/`--`/smart quotes), so a hyphenated filename comes
through uncorrupted. A block form also exists for multi-line verbatim
material: `\fixedwidth{` alone on a line, verbatim lines, then `}`
alone on a line.

**Backticks are a synonym for `\fixedwidth`.** Where standard
Markdown can be adopted verbatim it is: `` `text` `` and
`\fixedwidth{text}` render identically. `\filelink{path}{text}` adds
a relative /GoToR link annotation on top of the same monospace
styling; the link resolves only when the PDF is opened from a
location where `path` exists beside it (desktop viewers, not web
previews), so documents using it should say so.

Separately, `envelopes.yaml` may include envelope-level `copies:` entries for
static files that should be copied into `out/<envelope>/` (or
`out/<envelope>/<variant>/`) alongside generated pleadings:

```yaml
envelopes:
  initial_complaint:
    sources:
      - complaint.md
    copies:
      - src: assets/cm010_signed.pdf
      - src: assets/civil_case_cover_sheet.pdf
        dest: cover_sheet.pdf
```

## YAML front matter schema

Recognized top-level keys are enumerated in
[`front_matter_keys.yaml`](front_matter_keys.yaml). Anything else
**warns** at build time — never fails — naming the key and saying it
has no effect.

That warning exists because of a specific failure. `plain: true` sat in
six sources across two matters for months; nothing read it, so every
rebuild reprinted a caption the sources were trying to suppress. A key
nothing reads is indistinguishable, to every reader of the source, from
one that works — and gets copied into new files as a
demonstrated-correct example. If you want a note for a human, use a
YAML comment, which no one can mistake for configuration.

### Every build is a draft until `--final`

A build with no `--final` flag stamps a red banner on every page —
`DRAFT—NOT FILED` (pleadings), `DRAFT—NOT EXECUTED` (documents),
`DRAFT—NOT SENT` (letters) — and writes a machine-readable twin into
the PDF metadata, which `sc docuseal send` refuses unless overridden.
Rendered output is what circulates, and an unmarked draft is the
accident waiting to happen. Suppression is per-invocation only
(`sc build <envelope> --final`, `make <envelope> FINAL=1`); a
front-matter `_final:` is stripped, so a source can never finalize
itself. *(tested: pleading/tests/test_draft_banner.py)*

### `notreal` — the custom marker for hypotheticals, and it prints

```yaml
notreal: "DRAFT---not served as of August 7, 2026"
```

Marks a document that has not been filed, served, or sent. It is not
only a note to whoever opens the source: the marker renders as a **red
banner in the top margin of every page** of the assembled packet —
filled Judicial Council forms and merged exhibits included — in the
DOCX page header, and as a delimited first line in the TXT.

Write it as the sentence you want stamped on the page: "not filed" and
"not sent" are different facts, and a simulation is a third thing. The
house dash rule applies, since it is rendered text; markers written
before this printed are normalized on the way out.

Removing `notreal:` is what clears the banner, which makes clearing it
a deliberate act by someone who knows the document is going out.

The band is reclaimed by scaling each page's content, not drawn over
it, so it cannot collide with a form's own header and pagination is
unchanged — a page-and-line citation taken against the draft still
finds the same words on the same line.

### `no_caption` — for Judicial Council form attachments

```yaml
no_caption: true
```

Suppresses the entire standalone-pleading caption: the attorney block,
the filer role, the court name and county, the two-column party
caption, and the paper title. The body begins on line 1.

**Required** on anything that continues a Judicial Council form. An
"Attachment 3 to Deposition Subpoena for Production of Business
Records" is part of SUBP-010, which carried the caption one page
earlier; reprinting it presents the attachment as a separate paper
that was separately filed. It is not — it has no independent
existence.

The build **fails** when a source whose `paper_title` begins
`ATTACHMENT`, or which declares a subpoena `cover_sheet`, omits this
key. Add the key; do not remove `cover_sheet:` to silence the error.

This does not apply to a declaration attached to a CIV-110 — that is a
distinct document the request incorporates, and it is captioned
normally.

`plain: true` is accepted as an older spelling and warns. It was never
implemented, so for a long time sources that said it got the caption
anyway; if you see it, rename it.

### Required fields

These fields are expected for a normal pleading-style caption:

- `filer_name` — string
- `filer_address_lines` — list of strings
- `filer_phone` — string
- `filer_email` — string
- `filer_role` — string, e.g. `Plaintiff, In Pro Per`
- `court_name` — string
- `court_county` — string
- `petitioner` — string
- `respondent` — string
- `paper_title` — string

### Optional fields

- `caption_first_party_label` — string; printed under the first party’s name in
  the left column (default `Petitioner`). Use `Plaintiff` in unlimited civil
  actions; keep defaults for petition-style captions.
- `caption_second_party_label` — string; printed under the second party’s name
  (default `Respondent`). Use `Defendant` when `caption_first_party_label` is
  `Plaintiff`.
- `caption_versus_label` — string; the divider word between the party names
  in the caption (default `vs.`). Use `v.` for federal-court captions.
- `caption_divider_shift` — number (points, default `0`); shifts the `)`
  divider column to the right of its default position, widening the left
  party column and narrowing the right column. Useful when a long party
  name (e.g., a federal agency) would otherwise wrap onto too many lines.
  Values around `40`–`60` work well for agency-length names.
- `case_number` — string
- `paper_subtitle` — string; rendered in the right column below the paper title
- ~~`footer_title`~~ — **removed**; the footer now always uses `paper_title` (uppercased, regular weight). No other key overrides the footer: `short_title` is read only by JC cover-form fills (see `jc_common.py`) and never reaches the footer.
- `statutory_basis` — string; rendered in the right column below the title/subtitle, e.g. `"(Code Civ. Proc. §§ 527, 526a)"`
- `hearing_date` — string
- `hearing_time` — string
- `hearing_dept` — string
- `judge` — string
- `concurrent_filings` — list of strings; rendered as a bullet list in the right column under "Filed concurrently with:"
- `exhibits` — list of exhibit objects; if omitted or empty, no exhibit appendix is generated
- `redactions` — mapping from literal sealed text to its public replacement,
  used by one-argument `\redact{...}` in the Markdown body
- `consumer_notices` — list of mappings; one Notice to Consumer or
  Employee (SUBP-025) is filled and written beside this source's PDF
  per entry. See **Consumer/employee notices** below.
- `redaction_log_sources` — list of sibling source filenames (e.g.
  `["complaint.md", "declaration.md"]`). When present, the `\redactionlog`
  body macro scans those files for three-parameter `\redact` entries and
  auto-generates a numbered redaction log. See **Redaction log macro** below.

### Declarations with an MC-030 cover sheet

Declarations filed in California matters commonly use the
Judicial Council MC-030 form as a cover sheet, with "See attached
declaration" in the form's body field and the full declaration text
on attached pages.

To opt a pleading into this treatment, add `cover_sheet: mc030` to the
YAML front matter. At build time, the generator:

1. Fills a blank MC-030 from `pleading_gen/forms/mc030.pdf` using the
   pleading metadata.
2. Caches the filled MC-030 at
   `<case_dir>/assets/decl_cover_sheets/<source_stem>.mc030.pdf`.
3. Prepends the cached MC-030 as page 1 of the final output PDF.

The cache is regenerated automatically whenever the source `.md` or
the bundled blank form is newer than the cache.

The filled MC-030 leaves the date field, signature line, and role
checkbox blank for the declarant to complete by hand at signing. The
"TYPE OR PRINT NAME" line is pre-filled with the declarant's name.

Because the MC-030 already carries the boilerplate
`I declare under penalty of perjury under the laws of the State of
California that the foregoing is true and correct.` and a single
signature block, the attached declaration should omit both the
perjury clause and any `\signblock{decl}` at the end of the body.

Additional YAML keys supported by `cover_sheet: mc030`:

- `declarant_name` — string, required unless derivable from
  `paper_title` (the generator strips `"DECLARATION OF "` and any
  `" IN SUPPORT OF ..."` suffix)
- `filer_bar_number` — string; appended to the attorney block as
  `(SBN NNNNNN)`
- `filer_fax` — string; optional fax number
- `filer_attorney_for` — string override for the "Attorney for
  (Name):" field; by default derived from `filer_role`
- `court_street_address` — string
- `court_mailing_address` — string
- `court_city_zip` — string
- `court_branch` — string (e.g. `"Civic Center Courthouse"`)
- `mc030_body` — string override for the body field content (default
  is `"See attached Declaration of <declarant_name>."`)

The `court_county` field should hold just the county name
(e.g. `"SAN FRANCISCO"`) rather than `"COUNTY OF SAN FRANCISCO"` when used with
MC-030, because the form already prints the `"SUPERIOR COURT OF
CALIFORNIA, COUNTY OF "` label. The generator accepts either form
and strips the redundant prefix.

Example:

```yaml
---
cover_sheet: mc030
declarant_name: "JANE ROE"

filer_name: "Sally Sattler, Esq."
filer_bar_number: "234567"
filer_address_lines:
  - "Sattler Law Group"
  - "123 Main Street"
  - "San Francisco, CA 94102"
filer_phone: "(415) 555-0100"
filer_email: "sally@sattlerlawgroup.example.com"
filer_role: "Attorney for Petitioner JOHN SMITH"

court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "SAN FRANCISCO"
court_street_address: "400 McAllister Street"
court_mailing_address: "400 McAllister Street"
court_city_zip: "San Francisco, CA 94102"
court_branch: "Civic Center Courthouse"

petitioner: "JOHN SMITH"
respondent: "JANE ROE"
case_number: "23CV135875"
paper_title: "DECLARATION OF JANE ROE IN SUPPORT OF RESPONSIVE DECLARATION"

hearing_date: "June 8, 2026"
hearing_time: "9:00 a.m."
hearing_dept: "507"
---
# Introduction

I am Jane Roe. ...
```

### Civil dismissals with a CIV-110 cover sheet

Stipulated dismissals filed in California civil cases are commonly
accompanied by Judicial Council form CIV-110 ("Request for Dismissal"),
with both sides' signatures on the form and the full Stipulation for
Dismissal attached on subsequent pages.

To opt a pleading into this treatment, add `cover_sheet: civ110` to
the YAML front matter. At build time, the generator:

1. Fills a blank CIV-110 from `pleading_gen/forms/civ110.pdf` using the
   pleading metadata.
2. Caches the filled CIV-110 at
   `<case_dir>/assets/cover_sheets/<source_stem>.civ110.pdf`.
3. Prepends the cached CIV-110 (both pages) as the front of the final
   output PDF.

The cache is regenerated automatically whenever the source `.md` or
the bundled blank form is newer than the cache.

The filled CIV-110 leaves the body checkboxes (dismissal type at item
1.a, pleading type at item 1.b, fee-waiver at item 2), the date fields,
and all signature lines blank, so the parties can complete them by hand
at signing. The caption section (attorney/filer block, court county,
parties, case number) is pre-filled on both pages.

Additional YAML keys supported by `cover_sheet: civ110`:

- `filer_bar_number` — string
- `filer_fax` — string
- `filer_attorney_for` — string override for the "Attorney for (name):"
  field; by default derived from `filer_role` (the leading
  `"Attorney for "` is stripped if present)
- `filer_firm` — string; optional firm name
- `filer_street_address`, `filer_city`, `filer_state`, `filer_zip` —
  optional explicit overrides for the address split. By default, the
  generator parses the first two entries of `filer_address_lines` as
  `["<street>", "<city>, <state> <zip>"]`.
- `court_street_address`, `court_mailing_address`, `court_city_zip`,
  `court_branch` — optional

The `court_county` field should hold just the county name
(e.g. `"SAN FRANCISCO"`) rather than `"COUNTY OF EXAMPLE"`. The generator
accepts either form and strips the redundant prefix.

Example:

```yaml
---
cover_sheet: civ110

filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "jane.roe@example.com"
filer_role: "Petitioner, In Pro Per"

court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "SAN FRANCISCO"

petitioner: "JANE ROE"
respondent: "BAYSIDE MUNICIPAL TRANSIT DISTRICT"
case_number: "26CV00123"

paper_title: "STIPULATION FOR DISMISSAL WITH PREJUDICE"
---
This Stipulation is entered into ...
```

### Proposed orders with an EFS-020 cover sheet

Proposed orders e-filed in California courts that require a cover
sheet under Cal. Rules of Court 2.252 / 3.1312 use Judicial Council
form EFS-020 ("Proposed Order (Cover Sheet) — Electronic Filing").
The cover sheet identifies the proposed order and the proceeding it
relates to; an editable word-processing copy of the order must be
sent to the court at the same time.

To opt a proposed order into this treatment, add `cover_sheet: efs020`
to the YAML front matter. At build time, the generator:

1. Fills a blank EFS-020 from `pleading_gen/forms/efs020.pdf` using
   the pleading metadata.
2. Caches the filled EFS-020 at
   `<case_dir>/assets/cover_sheets/<source_stem>.efs020.pdf`.
3. Prepends the cached EFS-020 (both pages) as the front of the final
   output PDF.

The cache is regenerated automatically whenever the source `.md` or
the bundled blank form is newer than the cache.

The filled EFS-020 leaves the date and signature lines blank for
the filer to complete by hand at filing. Page 2 (Proof of Electronic
Service) is also left blank — the filer or the e-filing service
provider completes it at submission time.

Item 1 (party submitting the order) defaults to `filer_name`. Item 2
(title of the proposed order) defaults to `paper_title`. Items 3.a-c
(description / date and time / place of the related proceeding) come
from the YAML keys below; for dispositive orders that resolve the
action without a hearing, set the date/place fields to a value like
`"N/A -- no hearing"`.

Recommended companion practice: pair an EFS-020 cover sheet with a
matching `docx: true` source entry in `envelopes.yaml` so the
generator also emits an editable Word version of the proposed order,
satisfying the rule that an editable copy be sent to the court at
the same time as the PDF.

Additional YAML keys supported by `cover_sheet: efs020`:

- `judge` — populates the "JUDICIAL OFFICER:" field
- `hearing_dept` — populates the "DEPT:" field
- `filer_bar_number`, `filer_fax`, `filer_firm`, `filer_attorney_for`
  — same semantics as for `civ110`
- `filer_street_address`, `filer_city`, `filer_state`, `filer_zip`
  — overrides for the address split parsing
- `court_street_address`, `court_mailing_address`, `court_city_zip`,
  `court_branch`
- `efs020_party_name` — overrides item 1 (defaults to `filer_name`)
- `efs020_title` — overrides item 2 (defaults to `paper_title`)
- `efs020_proceeding_description` — item 3.a
- `efs020_proceeding_datetime` — item 3.b (default builds from
  `hearing_date` + `hearing_time`)
- `efs020_proceeding_place` — item 3.c (default builds from
  `hearing_dept`)

Example:

```yaml
---
cover_sheet: efs020

filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "jane.roe@example.com"
filer_role: "Petitioner, In Pro Per"

court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "SAN FRANCISCO"
court_street_address: "400 McAllister Street"
court_mailing_address: "400 McAllister Street"
court_city_zip: "San Francisco, CA 94102"
court_branch: "Civil"

petitioner: "JANE ROE"
respondent: "BAYSIDE MUNICIPAL TRANSIT DISTRICT"
case_number: "26CV00123"

paper_title: "[PROPOSED] ORDER ON STIPULATION FOR DISMISSAL WITH PREJUDICE"

efs020_proceeding_description: "Stipulated dismissal of action with prejudice; no hearing required"
efs020_proceeding_datetime: "N/A -- no hearing"
efs020_proceeding_place: "N/A -- chambers"
---
The Court has read and considered ...
```

### XFA (LiveCycle Designer) cover forms

Some Judicial Council forms are LiveCycle Designer (XFA) forms, unlike
MC-030/CIV-110/EFS020: their AcroForm fields have long hierarchical
dotted names (e.g.
`MC-025[0].Page1[0].AttyInfo[0].AttyName_ft[0]`), and the same logical
checkbox is repeated under different field names
across pages, so filling one occurrence does not fill the
others. Field names on such forms are NOT reliable indicators of
meaning — unrelated items can share identical leaf names, reused from
whatever template the form's designer copied. See the field-name `doc:`
comments in the form's registry descriptor
(`forms/registry/<form_id>.yaml`) if extending one — in particular,
most checkboxes on a given form share a single "on" state (`/1`), but
individual checkboxes can differ (`/3` has been observed on a single
checkbox of an otherwise-uniform form); never assume a shared
on-state for a new checkbox without checking its `/AP /N`
state name directly.

These forms go through the same descriptor-driven treatment as every
other cover sheet: add `cover_sheet: <form_id>` to the YAML front
matter, and at build time the generator:

1. Renders the document normally (caption, numbered paragraphs,
   exhibits, signature block — unchanged).
2. Fills the blank form from `forms/<form_id>.pdf` using the pleading
   metadata and the form's registry descriptor.
3. Caches the filled form at
   `<case_dir>/assets/decl_cover_sheets/<source_stem>.<form_id>.pdf`,
   regenerated whenever the source `.md`, the bundled blank form, or
   the descriptor is newer than the cache.
4. Prepends the cached form as the front of the final output PDF.

**Attached page counts.** Some cover forms state the page count of the
attached document (an "Additional orders attached" item with a
"Number of pages attached" blank, say), and that count is only knowable
after the document has actually been rendered. A descriptor declares
this with a top-level key:

```yaml
pages_attached_field: <logical field name>
```

When the key is present, the generator injects the rendered document's
page count into that field of the per-form block
(`forms: <form_id>:`) before filling, unless the source already
supplies a value explicitly.

Date-typed fields are left blank for completion at filing (a
placeholder like `hearing_date: "[TO BE SET]"` does not belong in a
date-typed field), as are judicial-officer and signature/date lines.
Which fields a form pre-fills, which it deliberately leaves blank, and
which per-form keys it accepts are documented per field in the registry
descriptor — see `sc form info <form_id>`.

The `court_county` field should hold just the county name (e.g.
`"SAN FRANCISCO"`) rather than `"COUNTY OF EXAMPLE"`; the generator accepts
either form and strips the redundant prefix.

### `cover_sheet_only` — a form with no accompanying document

Some sources exist solely to fill a standalone Judicial Council form —
MC-050 Substitution of Attorney, say, which has no declaration or
motion text riding behind it. Left to the ordinary `cover_sheet:`
treatment above, such a source would still get an automatic body
page: a numbered sheet of pleading paper, mostly blank because there
is no body to put on it, appended after the filled form's own pages.
That page is not part of the filing and should not exist.

```yaml
cover_sheet: mc050
cover_sheet_only: true
```

opts out of the body page entirely. At build time the generator:

1. Skips building or paginating a body PDF and skips any exhibit
   appendix — there is nothing to build one of.
2. Fills `cover_sheet` exactly as it would otherwise.
3. Writes the filled form directly as the output PDF (rather than
   prepending it onto a body, since there is no body).
4. Stamps the draft banner across the filled form's own pages, exactly
   as it would across a body plus cover sheet.

**Requires `cover_sheet:`.** `cover_sheet_only: true` with no
`cover_sheet` fails the build — there would be nothing to output.

**Rejects `exhibits:`.** A cover_sheet_only source has no body for an
exhibit appendix to attach behind; declaring both fails the build.

**Does not also need `no_caption: true`.** `no_caption` suppresses a
caption that a rendered body would otherwise carry, and cover_sheet_only
never renders a body in the first place — there is no caption-producing
code path for `no_caption` to switch off. Setting it anyway is harmless
but redundant.

Example — a fictional standalone substitution of attorney with no
accompanying declaration:

```yaml
---
cover_sheet: mc050
cover_sheet_only: true
forms:
  mc050:
    substituting_party_name: "JOHN SMITH"
    former_rep_attorney: true
    former_attorney_name: "Sally Sattler, Esq."
    new_rep_party_self: true

filer_name: "John Smith"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "john.smith@example.com"
filer_role: "Plaintiff, In Pro Per"
court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "EXAMPLE"
petitioner: "JOHN SMITH"
respondent: "JANE ROE"
case_number: "24CV00000"
paper_title: "SUBSTITUTION OF ATTORNEY"
---
```

builds `.../Substitution of Attorney.pdf` as MC-050's own pages and
nothing else.

### Consumer/employee notices (`consumer_notices`)

A records subpoena that reaches an identifiable individual's records
is invalid unless that person is separately served with a **Notice to
Consumer or Employee** (Judicial Council form SUBP-025) and a copy of
the subpoena (Code Civ. Proc. §§ 1985.3, 1985.6). One notice per
person, each addressed differently — so a source declares them as
data and the build emits one filled form per recipient.

`consumer_notices` is a **list of mappings**. Each entry describes one
recipient:

| Key | Required | Meaning |
|---|---|---|
| `consumer` | yes | The "TO (name):" line — the consumer or employee whose records are sought. Free text, so it can name the person and their attorney of record together. |
| `slug` | no | Filename component for this notice. Defaults to `consumer` lowercased with runs of non-alphanumerics collapsed to `_`, truncated to 40 characters. |
| *any SUBP-025 field or checkbox* | no | Per-recipient override of a value in the shared block (e.g. a different `witness`). Names are the descriptor's logical field names — see `sc form info subp025`. |

Values shared by every notice go in the ordinary per-form block,
`forms: subp025:`. Precedence is the usual one: descriptor default →
caption `auto:` binding → `forms.subp025` → the list entry.

Output: one PDF per entry, written **next to the source's own PDF**
(never merged into it — each notice is served on a different person),
named:

```
<source stem>.subp025.<slug>.pdf
```

The notices are treated as build outputs: a missing one makes the
source stale, so `build_envelope.py --check-stale` reports it and a
rebuild regenerates it.

The build **fails** — rather than emitting an incomplete set — when
`consumer_notices` is not a list of mappings, an entry has no
`consumer`, an entry carries a key that is not a SUBP-025 field, or
two entries resolve to the same slug (which would silently overwrite
one notice with another).

Example:

```yaml
---
cover_sheet: subp010
forms:
  subp010:
    deponent: "Keeper of Records, Example Bank, N.A., 500 Market Street, Example City, CA 90000"
    deposition_officer: "Example Records Service, Inc."
    production_date: "September 15, 2026"
    production_time: "10:00 a.m."
    production_location: "200 Commerce Way, Suite 300, Example City, CA 90000"
    method_mail_to_officer: true
  subp025:
    requesting_party: "JANE ROE, Respondent"
    production_date: "September 15, 2026"   # must equal the subpoena's
    witness: "Keeper of Records, Example Bank, N.A., 500 Market Street, Example City, CA 90000"

consumer_notices:
  - consumer: "JOHN SMITH"
  - consumer: "MARY MAJOR"
    slug: mary_major
    witness: "Keeper of Records, Example Employer, Inc., 900 Industrial Way, Example City, CA 90000"

filer_name: "Jane Roe"
petitioner: "JOHN SMITH"
respondent: "JANE ROE"
case_number: "24CV00000"
paper_title: "ATTACHMENT 3 TO DEPOSITION SUBPOENA FOR PRODUCTION OF BUSINESS RECORDS"
---
The records to be produced are: ...
```

builds `.../Subpoena to Example Bank.pdf` plus
`Subpoena to Example Bank.subp025.john_smith.pdf` and
`Subpoena to Example Bank.subp025.mary_major.pdf`.

Timing is the author's responsibility and is not computed: the notice
and a copy of the subpoena must be served on the consumer at least 10
days before the production date and at least 5 days before the
subpoena is served on the records witness (plus the Code Civ. Proc. § 1013
extension for mail), and the witness must receive proof that the
notice was served. See `sc form info subp025` and
`specs/pleading/forms/subp025.md`.

### Variant-aware values

Any YAML value may be made variant-aware by replacing the scalar with a mapping
whose keys are `sealed` and `public`:

```yaml
paper_subtitle:
  sealed: "CONDITIONALLY UNDER SEAL"
  public: "PUBLIC -- REDACTS MATERIALS FROM CONDITIONALLY SEALED RECORD"

redactions:
  "Robin Vance": "R.V."
```

Build with `VARIANT=sealed` or `VARIANT=public` (or the underlying
`--variant sealed|public` CLI flag), and the renderer resolves those values
before validation and exhibit processing.

If a field does not vary by version, keep it as an ordinary scalar instead of a
variant mapping.

Preferred workflow:

- Use `VARIANT=public` for public/redacted packets
- Use `VARIANT=sealed` for sealed/unredacted packets
- Avoid filing from unscoped outputs under `out/<envelope>/`

If no variant is supplied, the builder still works for backward compatibility,
but it emits a warning and writes to the legacy unscoped path:

- `out/<envelope>/`

That legacy mode is best treated as a draft/debug path rather than a filing
artifact. In it, **variant selection defaults toward safety**: any source
that carries redactions or variant-aware content (`\redact` macros, a
`redactions:` map, `sealed`/`public` value mappings, or sealed/redacted/
omitted exhibits) renders its **public** variant, with a loud stderr
warning. Sealed content is never written to the unscoped path by default —
rendering it always requires an explicit `--variant sealed`. Sources with
no variant-sensitive content render identically under either variant and
default to `sealed`. No `.redactions.json` sidecar is written on the
unscoped path (see the redaction-macro section).

### Exhibit object schema

Each exhibit entry in `exhibits` must be a YAML mapping with these fields:

- `shortname` — required string; unique identifier used for `\exhibit{shortname}` references in the Markdown body
- `title` — required string; used on the exhibit list and on the exhibit tab sheet
- `path` — required string (unless `sealed: true`); relative or absolute pathname to the attachment file. This may also be a variant-aware mapping with `sealed` / `public` branches. Bare filenames default to the sibling `exhibits/` directory next to `src/`.
- `pages` — optional string; page range selector for PDF attachments (see below)
- `sealed` — optional boolean (default `false`); if `true`, the exhibit is listed on the exhibit list page with a "[Lodged Conditionally Under Seal]" annotation but is **not attached** to the PDF. The `\exhibit{}` reference still resolves to the correct letter. No `path` is required for sealed exhibits. This is the direct attachment switch used by the active build variant. Tab sheets are asymmetric by design: in a **public** build the sealed exhibit gets a placeholder tab sheet labeled `LODGED CONDITIONALLY UNDER SEAL` (the public packet must show the gap); in a sealed-variant build the exhibit is skipped entirely — no tab sheet — because the packet is accompanied by the separately-lodged originals.
- `public_disclosure` — optional string controlling what happens in the **public**
  build. Allowed values:
  - `full` — attach the canonical exhibit as-is
  - `redacted` — attach the conventional `_redacted` companion file, or the
    explicit public `path` override if one is provided
  - `omitted` — keep the exhibit letter/reference, include a placeholder tab
    sheet labeled `LODGED CONDITIONALLY UNDER SEAL`, and omit the attachment
    from the public packet

If `public_disclosure` is omitted, the builder falls back to older fields for
backward compatibility, but new files should prefer `public_disclosure`.

#### Redacted exhibits convention

When an exhibit needs partial redaction (e.g., to remove PHI or third-party identifiers), maintain two versions of the file:

- `foo.pdf` — the original unredacted exhibit
- `foo_redacted.pdf` — the redacted version (black bars over sensitive content)

In the common case, keep one canonical `path` for the unredacted exhibit and
set `public_disclosure: redacted`:

```yaml
exhibits:
  - shortname: "service_agreement"
    title: "Service Agreement Signed by Both Parties"
    path: "service_agreement.pdf"
    public_disclosure: redacted
```

This convention expects both files to live in the same `exhibits/` directory:

- `service_agreement.pdf`
- `service_agreement_redacted.pdf`

If the redacted public filename is not a simple `_redacted` companion, use an
explicit public path override:

```yaml
exhibits:
  - shortname: "special_exhibit"
    title: "Special Exhibit"
    public_disclosure: redacted
    path:
      sealed: "../exhibits/original_scan.pdf"
      public: "../exhibits/public_extract.pdf"
```

To keep an exhibit out of the public packet entirely while preserving its letter
and references:

```yaml
exhibits:
  - shortname: "jan5_counsel"
    title: "Email from Whitfield to Counsel, January 5, 2026, 8:00 AM"
    path: "jan5_counsel_email.pdf"
    public_disclosure: omitted
```

This is distinct from plain `sealed: true`, which controls the current build
variant directly. `public_disclosure` is the preferred cross-variant policy
layer for single-source pleadings.

Configuration rules:

- Prefer one canonical unredacted `path` plus `public_disclosure: redacted`
- Use `public_disclosure: omitted` for exhibits that should be referenced but
  not attached in the public packet
- Use an explicit variant-aware `path` only as an override/escape hatch
- Do **not** combine old `public_redacted: true` with an explicit variant-aware
  `path`; that legacy combination is rejected because the two strategies
  conflict

Supported attachment file types:

- `.pdf`
- `.png`
- `.jpg`
- `.jpeg`

`path` resolution rules:

- absolute paths are used as-is
- bare filenames like `service_agreement.pdf` resolve to the sibling
  `exhibits/` directory next to `src/`
- paths with directory components (for example `../assets/foo.pdf` or
  `subdir/foo.pdf`) remain relative to the input Markdown file for backward
  compatibility

#### Page range selection (`pages`)

The optional `pages` field selects a subset of pages from a PDF attachment. The syntax follows the familiar print-dialog convention:

- Individual pages: `4` or `1,4,7`
- Ranges: `3-5` (pages 3, 4, and 5)
- Mixed: `1,4-5,8` (pages 1, 4, 5, and 8)
- From a page to the end: `3-` (page 3 through the last page)
- From the start to a page: `-5` (pages 1 through 5)

Pages are 1-indexed. Ranges are inclusive on both ends. Entries are separated by commas. Whitespace around commas and hyphens is tolerated.

If `pages` is omitted, all pages of the PDF are included. If `pages` is present on a non-PDF attachment (image), it is ignored.

Examples:

```yaml
exhibits:
  - shortname: "escalation_notice"
    title: "Email from Whitfield, December 5, 2025"
    path: "exhibits/intake_thread.pdf"
    pages: "4"
  - shortname: "delay_notice"
    title: "Email from Whitfield to Counsel, December 22, 2025"
    path: "exhibits/follow_up_thread.pdf"
    pages: "8-9"
  - shortname: "full_doc"
    title: "Complete Filing"
    path: "exhibits/filing.pdf"
```

### Exact semantics

#### Filer block

Caption elements are rendered on the 28-line grid to preserve alignment with line numbers. The filer block is sub-grid spaced (compressed to fit within a few grid lines), and all subsequent elements (role, court name, party table) land on grid positions.

The caption renders top-to-bottom as follows:

#### Filer block

Single-spaced, left-aligned, starting at the line 1 y-position:

- `filer_name`
- each entry in `filer_address_lines`
- `filer_phone`
- `filer_email`
- `filer_role` — uppercased and bold (e.g., `PLAINTIFF, IN PRO PER`)

#### Court title

Centered and bold, single-spaced:

- `court_name`
- `court_county`

#### Two-column party table

A two-column layout with a `)` character column as the divider:

**Left column** — party names and labels:
- `petitioner` (bold)
- "Petitioner," (indented)
- "vs." (indented)
- `respondent` (bold)
- "Respondent." (indented)

**Divider** — a column of `)` characters at roughly the page center

**Right column** — case info and document identification:
- `Case No.: {case_number}`
- `paper_title` (bold, uppercased)
- `paper_subtitle` (if present)
- `statutory_basis` (if present)
- Hearing metadata: `hearing_date`, `hearing_time`, `hearing_dept`, `judge` (if present)
- `concurrent_filings` (if present) — rendered as a bullet list under "Filed concurrently with:"

#### Caption separator

A horizontal rule spanning the text area is drawn below the party table. The body text begins on the next available line-grid position after this rule.

#### Footer

The footer appears below a horizontal rule drawn at 1.0" from the bottom edge:

- Page number: centered below the rule (shown on all pages including page 1)
- Paper title: centered below the page number, rendered in **regular weight, uppercased** — always matches the caption title

#### Exhibits

If `exhibits` is present and non-empty, the script appends an exhibit appendix after the pleading body.

The exhibit appendix consists of:

1. an **Exhibit List** page or pages, in pleading format with line numbers;
2. for each exhibit in order:
   - a tab sheet page reading `EXHIBIT A`, `EXHIBIT B`, etc.; then
   - one or more pages containing the associated attachment, scaled and centered.

Exhibit letters are automatic and assigned by list order:

- first exhibit → `A`
- second exhibit → `B`
- third exhibit → `C`
- and so on

## Markdown body rules

The body supports a deliberately narrow subset of Markdown so layout remains deterministic.

### Supported constructs

- `# Heading` → level-1 heading
- `## Heading` → level-2 heading
- `### Heading` → level-3 heading
- ordinary paragraphs separated by blank lines
- bulleted list items beginning with `- ` or `* `
- exhibit references in the form `\exhibit{shortname}`
- inline emphasis: `*italic*`, `**bold**`, `***bold italic***`

### Inline formatting

The generator supports standard Markdown inline emphasis:

- `*text*` renders in italic (e.g., `*Doe v. Roe*` → *Doe v. Roe*)
- `**text**` renders in bold
- `***text***` renders in bold italic

Use `*...*` for case citations, Latin phrases, and other conventionally italicized legal text.

### Typographic substitutions

The generator automatically converts ASCII approximations to proper Unicode glyphs:

- `---` → em dash (—)
- `--` → en dash (–)
- `"..."` → smart double quotes ("…")
- `'` after a letter → right single quote / apostrophe (e.g., `Whitfield's` → Whitfield's)
- `'` between an abbreviation's trailing period and a letter → apostrophe
  (e.g., `C.E.O.'s` → C.E.O.’s), so a possessive after an abbreviation is
  never misread as an opening quote

**Critical: no spaces around `---`.** The substitution converts the three
hyphens to an em dash but preserves any surrounding whitespace literally.
`text --- text` renders as `text — text` (with gaps on both sides), which
is typographically wrong. Always write `text---text` with no spaces.
This is the single most common authoring error in these source files.
Run `grep -rn ' --- ' src/` before building; zero matches is the target.
The generator also emits a stderr `WARNING` for every source line carrying
a spaced `' --- '` or `' -- '` at build time; the build still succeeds
(the substitution layer never rewrites or refuses an author's spacing).
- `'` before a letter → left single quote (e.g., `'hello` → 'hello)
- any remaining `'` → right single quote

Known limitation: a decade abbreviation like `'90s` matches the
opening-quote rule (apostrophe before a word character) and renders with
a LEFT single quote (‘90s), which is typographically wrong for an elision.
Write the Unicode apostrophe (`’90s`) directly in the source when this
matters; Unicode passes through untouched.

Unicode characters in the source are passed through directly. Use `§` for section signs, `¶` for pilcrow/paragraph marks, and any other Unicode symbols as needed. Passing a glyph through is not advice to use it: see [docs/writing-style.md](../docs/writing-style.md) for when `¶` is conventional (parenthetical citations only) and when to write "paragraph" instead.

The same substitutions apply to YAML-sourced display strings in the PDF
renderer — the caption block (`paper_title`, `paper_subtitle`, party
names, court names, the filer block, `statutory_basis`, hearing fields,
`concurrent_filings`), the letter header, the footer title, and exhibit
titles — so a `--` in a subtitle renders as an en dash in the caption
exactly as it would in the body.

The DOCX renderer applies its own house-style subset — dashes convert,
quotes/apostrophes stay ASCII so Word's autocorrect can manage them —
and that subset likewise covers both the body and the YAML-sourced
caption / letter-header strings. *(tested:
test_docx_caption_dashes_converted and
test_docx_keeps_straight_quotes_by_design in the pleading_typography
scenario)*

### Highlight macro (`\highlight{...}`)

`\highlight{text}` renders its contents with a yellow background, in both
PDF and DOCX output. It composes with the other inline emphasis macros —
`\highlight{**bold text**}` and `\highlight{*italic text*}` both work, and
ordinary `**bold**`/`*italic*` spans can themselves contain a `\highlight{}`
run. It is parsed by the same tokenizer as `*`/`**`/`***`/`<u>` (not a
pre-tokenization string substitution like `\redact`), so nesting is handled
uniformly rather than as a special case.

```md
The parties agree that \highlight{this paragraph was added by the drafting
assistant and needs counsel's review} before filing.
```

Intended use: flagging a passage that a non-attorney drafter (or an AI
drafting assistant) added or materially changed, so reviewing counsel can
find every substantive edit at a glance without diffing the whole document.
It is a review aid, not a pleading convention — a filed version should have
all `\highlight{}` markers either accepted (removed, leaving the enclosed
text as ordinary content) or reverted before the document is actually filed.

In DOCX output, the highlight uses python-docx's native yellow highlight
(`WD_COLOR_INDEX.YELLOW`), the same highlight color Word's own UI produces,
so reviewers can respond with tracked changes or comments as usual.

### Footnotes (`[^id]` / `[^id]: text`)

Footnotes use the common Markdown extension syntax: a reference marker
`[^id]` inline in the body, and a definition line `[^id]: note text`
anywhere in the source (conventionally grouped at the end). A definition
may continue across multiple source lines when the continuation lines are
indented. Definition lines are removed from the body before layout.

Rendering:

- **PDF:** references render as raised superscript numbers assigned in
  reading order; each note renders at the bottom of the page in 10 pt
  type below a short separator rule. A marker and its note always share
  a page (the note area shrinks the usable body area; a line that no
  longer fits travels to the next page together with its note).
- **DOCX:** references become real Word footnotes (`w:footnoteReference`
  runs plus a `footnotes.xml` part), so Word and Pages render and
  renumber them natively.
- **TXT:** references render as inline `[n]` markers and the notes are
  appended as an end-of-document notes section, one `[n] text` line per
  note in number order.

**Undefined ids surface visibly.** A reference whose id has no matching
definition renders as its literal `[^id]` marker in every output format —
never as a numbered reference with an empty note (PDF) or a dangling
package reference (DOCX). The error is meant to be seen in review, not
hidden.

*(tested: footnote numbering/placement/same-page checks and the
undefined-id control in `tests/scenarios/pleading_typography`, plus DOCX
footnotes-part and TXT notes-section parity checks in the same scenario)*

### Unsupported or minimally supported constructs

These are not the target of the current version:

- code fences
- embedded HTML
- inline images in the pleading body
- nested lists deeper than one level
- complex block quotes (simple `>` block quotes render indented)
- complex tables (simple pipe tables render on the grid with
  measured column widths and a bold header row)

If such constructs appear, they may render as plain wrapped text.

## Automatic section numbering

The generator automatically numbers headings in legal-outline style:

- `#` → `I.`, `II.`, `III.`
- `##` → `A.`, `B.`, `C.`
- `###` → `1.`, `2.`, `3.`

Examples:

```md
# INTRODUCTION
## FACTUAL BACKGROUND
### The January 9 Email
```

renders approximately as:

- `I. INTRODUCTION`
- `A. FACTUAL BACKGROUND`
- `1. The January 9 Email`

## Exhibit references in the body

Within the Markdown body, the syntax:

```md
\exhibit{jones_texts}
```

is replaced during generation with the exhibit letter assigned from the YAML list, as plain text:

```text
Exhibit B
```

If `jones_texts` is the second exhibit in the YAML list, the substitution result is `Exhibit B`.

This allows you to write stable symbolic references in Markdown without hardcoding exhibit letters by hand.

If a referenced shortname does not exist in the YAML `exhibits` list, generation fails with an error.

### Doctype-aware label: `Exhibit` vs `Attachment`

The citation word produced by `\exhibit{}` is doctype-aware. In pleadings
(`doctype: pleading`, the default) it renders as `Exhibit A`, `Exhibit B`,
etc. In letters (`doctype: letter`) it renders as `Attachment A`,
`Attachment B`, etc., the attachment-list page is headed `ATTACHMENT LIST`,
and the tab sheets read `ATTACHMENT A` instead of `EXHIBIT A`.

`\attachment{shortname}` is accepted as a synonym for `\exhibit{shortname}`
and is preferred in letters. Both macros are interchangeable: each is
resolved to the doctype's label at render time.

## Document layout primitives (plain instruments)

For `doctype: document` instruments (notes, contracts) whose grammar
is tabbed alignment rather than a pleading grid:

```
\leftright{$20,000.00}{August 13, 2026}   left at margin, right flush right
\center{text}                             one centered line
\sigrow{Name, Borrower}{Date}             side-by-side signature rules
```

`\leftright` and `\center` take inline styling (**bold** etc.).
`\sigrow` draws two rules with labels beneath (one signer per row —
signature left, date right; the labels take `\\` for a second line,
e.g. `{Sue Smith, Lender\\Accepted and agreed}`), is atomic across
page breaks, and carries the signer's e-sign field tags like any
signature block. *(tested: pleading/tests/test_document_layout.py)*

## Signature blocks — one macro, five styles

```
\signblock{dated}{NAME}{ROLE?}
\signblock{decl}{NAME}{LOCATION?}{ROLE?}
\signblock{judge}{TITLE}
\signblock{letter}{Name\\Firm\\Role}
\signblock{whereof}{NAME}{ROLE?}{INSTRUMENT?}
```

- **dated** — `Dated: ____, <year>`, signature rule, name, role (the
  role falls back to `filer_role`).
- **decl** — the declaration execution line (`Executed this ___ day
  of ___, <year>, at LOCATION.`), rule, name, role.
- **judge** — `Dated:` line, rule, and the title, for proposed
  orders.
- **letter** — `Sincerely,`, rule, and the `\\`-separated author
  block; the argument may span source lines.
- **whereof** — the testamentary execution clause and signature area
  as ONE block: `IN WITNESS WHEREOF, I, {NAME}, sign this
  {INSTRUMENT} on this ___ day of ___, 20__, at ___.` with the
  location blank for the ceremony, then rule, name, role. It prints
  no `Dated:` line — the clause recites the date, and the old
  pairing of a prose clause with a bare `\signblock` printed the
  date twice.

The legacy spellings (`\declsignblock`, `\judgesignblock`,
`\lettersignblock`, bare `\signblock{NAME}`) still build, mapped to
the styles above with a stderr deprecation warning — a live matter
mid-filing never breaks on a taxonomy change.

### E-signature fields, computed automatically

Every signature block and witness grid records an e-sign field
(signature, date, location, residence) sized to its rule or blank.
Front-matter `esign` picks the transport: absent (the default), the
geometry is written to a `<pdf>.fields.json` sidecar and NOTHING
enters the PDF text layer — embedded tags were invisible on paper
but rode along on every copy-paste; `esign: tags` draws classic
DocuSeal `{{...}}` text tags in white 6 pt (the only mode the free
web UI's tag parser reads; overlapping tags stagger vertically);
`esign: false` emits nothing at all — the wet-ink mode for
instruments e-signature cannot lawfully execute (wills, Prob. Code
6110; negotiable notes, UETA's Article 3 exclusion). Signer roles
number in document order — the same order `sc docuseal send --to`
assigns submitters. A `--sign` render's dated and decl blocks carry
no fields (the signature line is already executed); notarial
certificates carry none (a notary's ceremony is not an e-sign
flow); and judge blocks carry none — a judicial signature line is a
space for wet ink, never a DocuSeal role.

### Fill-in blanks: `\blank{<length>}`

`\blank{2in}` (units: `in`, `pt`, `cm`, `mm`) renders a fill-in
rule of that length — write intent, not underscore runs. Expansion
is shared by the PDF, TXT, and DOCX renderers, and the result still
reads as a blank run to the e-sign field machinery above.

## Output specification

The script emits a PDF file.

### Command-line usage

```bash
python md_pleading.py input.md output.pdf
```

### CLI behavior

- Reads `input.md`
- Parses front matter and body
- Resolves exhibit references in the body
- Applies typographic substitutions
- Parses inline emphasis (`*italic*`, `**bold**`, `***bold italic***`)
- Lays out the pleading onto U.S. Letter pages
- If exhibits are defined, appends:
  - an Exhibit List in pleading format
  - exhibit tab sheets
  - exhibit attachment pages
- Writes `output.pdf`

### Font dependency

The script requires TeX Gyre Schola TTF files in the `fonts/` directory relative to the script:

- `fonts/texgyreschola-regular.ttf`
- `fonts/texgyreschola-bold.ttf`
- `fonts/texgyreschola-italic.ttf`
- `fonts/texgyreschola-bolditalic.ttf`

These are converted from OTF originals distributed by GUST (the Polish TeX Users Group) under the GUST Font License. TeX Gyre Schola is a metric-compatible free clone of Century Schoolbook.

## Page model

Each pleading page is built on a fixed 28-line grid.

### Why this matters

The line numbers are not fake decorations added after the fact. The document body is laid out into fixed line slots, and the line numbers are drawn using the same slot geometry. That makes the alignment reliable.

### Line geometry

- 28 lines per page
- Line 1 baseline: 1.125" from the top edge (81 pt)
- Line 28 baseline: 1.125" from the bottom edge (81 pt)
- Leading: derived as (line 1 y − line 28 y) / 27 ≈ 23.3 pt
- Vertical rule: at exactly 1.125" from the left edge
- Text area: from 1.375" left to 7.9" (0.6" from right edge)

### Footer geometry

- Horizontal rule: at 1.0" from the bottom edge (72 pt), spanning the text area
- Page number: centered, 14 pt below the rule
- Footer title: centered, regular weight, 26 pt below the rule

## Exhibit appendix behavior

### Exhibit List output

When exhibits exist, the script creates a pleading-formatted exhibit list with a centered bold heading:

```text
EXHIBIT LIST
```

The list then contains one entry per exhibit, in order, such as:

```text
Exhibit A    January 23, 2026 Email from Dana Whitfield
Exhibit B    Screenshots of Text Messages with Jones
```

If the list runs longer than one page, it continues onto additional pleading-formatted pages.

### Exhibit tab sheets

Before each exhibit attachment, the script inserts a separate tab sheet page.

The tab sheet contains:

- `EXHIBIT A` (or B, C, etc.) centered on the page in **bold 24 pt** Century Schoolbook
- the exhibit title centered below it in **14 pt** Century Schoolbook
- the combined text block vertically centered and horizontally centered on the page

### Attachment rendering rules

#### Image attachments

For image files (`.png`, `.jpg`, `.jpeg`):

- the script reads the image dimensions;
- computes a scale factor preserving aspect ratio;
- scales so the maximal displayed size is within **7.5 inches wide** or **10 inches high**;
- centers the result on a blank U.S. Letter page.

#### PDF attachments

For PDF files:

- if `pages` is specified, only the selected pages are imported (in the order given); otherwise all pages are imported;
- each imported page is scaled proportionally so it fits within **7.5 inches wide** or **10 inches high**;
- each page is centered on a blank U.S. Letter page.

This means every appended exhibit attachment page becomes a U.S. Letter page in the final output, even when the original attachment had a different size.

Out-of-range page numbers in a `pages` specifier (e.g., requesting page 10 of a 3-page PDF) cause generation to fail with an error.

If a source PDF has malformed content streams (common with some Gmail PDF exports), the script falls back to importing the page without scaling rather than failing.

## Example with exhibits

```md
---
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(510) 555-1212"
filer_email: "name@example.com"
filer_role: "Plaintiff, In Pro Per"

court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "COUNTY OF EXAMPLE"
petitioner: "JANE ROE"
respondent: "JOHN SMITH"
case_number: "24CV000123"

paper_title: "DECLARATION OF JANE ROE"

exhibits:
  - shortname: "whitfield_email"
    title: "January 23, 2026 Email from Dana Whitfield"
    path: "exhibits/whitfield_email.pdf"
    pages: "2-3"
  - shortname: "jones_texts"
    title: "Screenshots of Text Messages with Jones"
    path: "exhibits/jones_texts.jpeg"
---
# FOUNDATION

Attached as \exhibit{whitfield_email} is a true and correct copy of the January 23, 2026 email.

See *Doe v. Roe* (2024) 100 Cal.App.5th 123, 130.

Attached as \exhibit{jones_texts} are true and correct screenshots of the relevant text messages.
```

## Block quotes

Lines beginning with `>` are parsed as block quotes. Consecutive `>` lines merge
into a single block (like paragraphs) and are rewrapped to the indented measure,
so the source's own line breaks do not survive into the PDF — break the source
wherever is convenient. Block quotes render as indented blocks (36 pt from the
left margin) on consecutive grid lines, with the same leading as body text, and
without bullet characters or quotation marks. Use them for extracted statutory
language or other quoted material:

```md
Education Code § 49069.7(a) provides:

> Parents of currently enrolled or former pupils have an absolute right to access
> to any and all pupil records related to their children that are maintained by
> school districts or private schools.
```

## Envelope build system (`envelopes.yaml`)

The `build_envelope.py` script reads `envelopes.yaml` from the current working
directory. Each envelope groups the source files for a single court filing.

### Schema

```yaml
envelopes:
  envelope_name:
    sent_on: 2026-03-19              # optional; marks envelope already sent/filed
    sources:
      - simple_source.md                # PDF only
      - file: proposed_order.md         # PDF + editable Word doc
        docx: true
```

Each entry in `sources` is either:

- **a string** — the filename of a markdown source in `src/`. Produces a PDF in
  `out/<envelope_name>/`.
- **a mapping** with:
  - `file` (required) — the source filename
  - `docx` (optional, default `false`) — if `true`, also generates an editable
    `.docx` alongside the PDF via `md_to_docx.py`. Use this for proposed orders
    that the court needs to edit and sign.

Envelope-level metadata:

- `sent_on` (optional) — ISO date string such as `2026-03-19`. If present, the
  envelope is treated as already sent/filed. `make all` skips it by default,
  and explicit rebuilds require force.

### Sent-envelope workflow

Use `sent_on` to preserve the definition of a packet that has already been sent
or filed without letting routine rebuilds overwrite it by accident.

Recommended pattern:

1. Draft normally with no `sent_on` key.
2. Build with `make <envelope_name>` or `make all`.
3. After the packet is actually sent or filed, add `sent_on: YYYY-MM-DD` to the
   envelope in `envelopes.yaml`.
4. From that point forward:
   - `make all` skips that envelope
   - `make list` shows it as sent with its date
   - `make <envelope_name>` refuses to rebuild it unless forced

Example:

```yaml
envelopes:
  prelitigation_364:
    sent_on: 2026-03-19
    sources:
      - notice_364.md
```

If you intentionally want to rebuild a sent envelope, use:

```bash
make prelitigation_364 FORCE=1
```

This is meant for exceptional cases only, because once a packet has been sent,
the generated output in `out/<envelope_name>/` may no longer match the exact
source text that was mailed or filed.

### Redaction macros

The preferred `\redact` syntax has these forms:

- `\redact{sealed text}`
- `\redact{sealed text}{public text}`
- `\redact{sealed text}{public text}{justification for log}`

Semantics:

- one argument:
  - sealed build renders the argument exactly as written
  - public build looks up that exact string in YAML `redactions:` and substitutes
    the mapped public value
- two arguments:
  - sealed build renders the first argument
  - public build renders the second argument
- three arguments:
  - rendering behavior is identical to two arguments
  - third argument is treated as a redaction-justification note and is recorded
    in a sidecar JSON log at `<output>.redactions.json` (e.g.
    `complaint.pdf.redactions.json`). The sidecar is a JSON array of objects,
    each with `"sealed"`, `"public"`, and `"justification"` keys. It is written
    automatically whenever at least one three-parameter `\redact` is present,
    **for sealed-variant builds only**: the sidecar quotes the verbatim sealed
    text, so public (and unscoped no-variant) builds never write it — the
    public output directory must stay free of sealed bytes end to end.

Example:

```yaml
redactions:
  "Robin Vance": "R.V."
  "Robin": "R.V."
  "Robin's": "R.V.'s"
```

```md
The account was opened by \redact{Robin Vance}.
Whitfield confirmed that \redact{Robin} was never notified.
This phrase is \redact{fully stated in sealed form}{pared down in public form}.
This phrase is \redact{sealed detail}{public summary}{C7 reputational harm; not required for public adjudication}.
```

Recommended pattern:

- Use one-argument `\redact{...}` for recurring names and identifiers so the
  sealed text stays legible inline.
- Use two-argument `\redact{...}{...}` for one-off passages or phrases that are
  only used once and don't need a justification in the redaction log.
- Use three-argument `\redact{...}{...}{...}` for nontrivial content redactions
  that need a logged justification (e.g. for an application to seal). The
  third parameter should be a brief category code and rationale, such as
  `C4/C7: character allegation; causes disproportionate reputational harm`.

Legacy note:

- `\redacttext{sealed}{public}` is still supported as a backward-compatible
  alias with identical semantics to `\redact` (all three arities, including
  the redaction-log third argument and the unknown-key error for the
  one-argument form), but new files should prefer `\redact{sealed}{public}`.
  *(tested: test_redacttext_legacy_alias_resolves_like_redact in the
  pleading_exhibits scenario)*

### Redaction log macro

Use `\redactionlog` in a document body to auto-generate a numbered log of
all three-parameter `\redact{}{}{justification}` entries found across multiple
source files. The document's YAML must include `redaction_log_sources`:

```yaml
redaction_log_sources:
  - complaint.md
  - declaration.md
  - memo_points_authorities.md
```

At render time the macro:

1. Opens each listed source file (resolved relative to the current file's
   directory). A listed source that does not exist or cannot be parsed
   **fails the build with an error** — the log exists to demonstrate
   completeness to a court, so a typo'd filename must never silently
   produce a shorter log.
2. Parses its YAML front matter and runs redaction substitution in a dry-run
   to collect all three-parameter log entries.
3. Collects any three-parameter entries from the current file as well.
4. Expands to numbered paragraphs grouped by source, each rendering the
   source's display name and the justification text, e.g.:

> 1. *Complaint* — C4/C7: justification text
>
> 2. *Declaration* — C2: justification text

The sealed excerpt itself is deliberately **not** quoted in the expansion:
the redaction log is typically filed publicly, so reproducing the sealed
text there would defeat the redaction. Entries whose justification (third
parameter) is empty are skipped.

This is designed for use in applications to seal where the court requires a
log demonstrating that each redaction is narrowly tailored and justified.

Because the macro reads source `.md` files directly (not sidecar JSON), it
always reflects the current state of the sources regardless of build order
or staleness.

Example usage in `application_to_seal.md`:

```md
The following log identifies each redaction and its justification:

\redactionlog
```

### Proof of service macro

Use `\posblock` to expand a complete California-style proof of service
(declaration form) at the place the macro appears. The macro reads
configuration from a `proof_of_service:` mapping in the document's YAML
front matter:

```yaml
proof_of_service:
  method: email                       # or "U.S. Mail" / "personal delivery"
  date: "May 8, 2026"                 # optional; blank renders as fill-in
  documents:
    - "Stipulation for Dismissal With Prejudice"
    - "[Proposed] Order ..."
  recipients:
    - name: "Alex Fenwick"
      role: "General Manager, Bayside Municipal Transit District"
      email: "afenwick@example.org"
    - name: "Priya Raman"
      role: "Counsel for Respondent, Raman & Ives LLP"
      email: "praman@example.com"
  server:                             # optional; defaults to filer block
    name: "Jane Roe"
    address: "123 Main Street, Springfield, CA 90000"
    email: "jane.roe@example.com"
    city_state: "San Francisco, California"   # for execution location
```

At render time the macro expands to a four-paragraph declaration:

1. Server's identity and address.
2. (Electronic only) Server's electronic service address.
3. Date of service and bulleted list of documents served.
4. Recipients with their email or mailing addresses.

The expansion ends with a perjury clause and a `\signblock{decl}` so the
server can date and sign at filing time. If `proof_of_service.date` is
omitted, the date in paragraph 3 renders as a fill-in blank.

The substitution also adapts to non-electronic methods:

- `method: email` (or `electronic` / `e-mail`) — uses CCP § 1010.6
  language; recipient line shows email address; paragraph 2 quotes the
  server's electronic service address.
- any other value (e.g. `U.S. Mail`, `personal delivery`) — uses CCP
  § 1013a-style language; recipient line shows mailing address;
  paragraph 2 is omitted (the server's email is not relevant).

`\posblock` is intended for either:

- a standalone POS document (set `paper_title: "PROOF OF ELECTRONIC
  SERVICE"` and place `\posblock` as the entire body); or
- inline at the end of another pleading (preface with a heading like
  `# PROOF OF ELECTRONIC SERVICE` if the surrounding pleading does not
  already announce one).

Example standalone POS source file:

```yaml
---
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "jane.roe@example.com"
filer_role: "Petitioner, In Pro Per"

court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "COUNTY OF EXAMPLE"
petitioner: "JANE ROE"
respondent: "BAYSIDE MUNICIPAL TRANSIT DISTRICT"
case_number: "26CV00123"
paper_title: "PROOF OF ELECTRONIC SERVICE"

proof_of_service:
  method: email
  documents:
    - "CIV-110 Request for Dismissal"
    - "Stipulation for Dismissal With Prejudice"
  recipients:
    - name: "Alex Fenwick"
      role: "General Manager, Bayside Municipal Transit District"
      email: "afenwick@example.org"
  server:
    city_state: "San Francisco, California"
---
\posblock
```

### Build commands

From the case directory (where `envelopes.yaml` lives):

```bash
make <envelope_name>                                    # build one envelope if stale/missing
make <envelope_name> NAME="Jane Roe" DATE=2026-03-16 # signed + dated
make <envelope_name> VARIANT=public                     # build public variant to out/<envelope>/public/ if stale/missing
make <envelope_name> VARIANT=sealed                     # build sealed variant to out/<envelope>/sealed/ if stale/missing
make all NAME="Jane Roe" DATE=2026-03-16             # build all draft envelopes if stale/missing
make all VARIANT=public                                 # build all public variants if stale/missing
make all VARIANT=sealed                                 # build all sealed variants if stale/missing
make both                                               # run both of the above (public then sealed)
make list                                               # show available envelopes
make check-stale VARIANT=public                         # fail if any public output is stale
make check-stale VARIANT=sealed                         # fail if any sealed output is stale
make <envelope_name> FORCE=1                            # force rebuild and allow sent envelope rebuild
make all FORCE=1                                        # include sent envelopes and force rebuild
make clean                                              # delete out/
```

If `VARIANT` is omitted, the build emits a warning and writes to the legacy
unscoped output directory `out/<envelope>/`.

### Incremental rebuilds

Normal build commands are dependency-aware. Before rebuilding a source, the
driver checks whether its outputs are missing or older than any dependency.

For each source, the dependency set includes:

- the markdown source itself
- all attached exhibit files selected for the current variant
- any `exhibit_source` markdown file used for cross-file exhibit-letter mapping

Behavior:

- if outputs are current, the source is skipped as up to date
- if any output is missing, the source is rebuilt
- if any dependency is newer than an output, the source is rebuilt
- `FORCE=1` bypasses the mtime check and rebuilds everything in scope

This means plain build commands such as `make initial_complaint VARIANT=public`
should normally be enough after source edits or exhibit redactions; the driver
will notice stale outputs and regenerate them automatically.

### Staleness checks

The build driver can verify that generated outputs are not older than the files
they depend on.

Command:

```bash
make check-stale VARIANT=public
make check-stale VARIANT=sealed
```

What it checks for each rendered source:

- the output PDF exists
- the output `.docx` exists for any `docx: true` source
- the output file is newer than:
  - the source markdown file itself
  - all attached exhibit files selected for that variant
  - any `exhibit_source` markdown file used for external exhibit-letter mapping

If any output is missing or older than one of those dependencies, the command
fails and prints the stale file and the dependency that is newer.

This is especially useful after:

- hand-redacting an exhibit PDF
- refreshing Gmail-exported exhibit sources
- changing a canonical exhibit symlink target

### Makefile

Each case directory should symlink to the shared Makefile in `pleading_gen/`:

```bash
ln -sf ../pleading_gen/Makefile .    # from a case dir like roe-v-bayside/
```

The Makefile auto-detects the relative path to `build_envelope.py`.

### Gmail export helper

The shared Makefile also exposes a `gmail` target for case directories that
define `gmail_addresses:` in `envelopes.yaml`.

Expected repository layout:

```text
lawyering/
  pleading_gen/
  gmail-mcp-server/
  some-case/
```

By default, the Makefile resolves the Gmail export script relative to
`pleading_gen/`:

- script: `../gmail-mcp-server/gmail_to_pdf.js`
- `NODE_PATH`: `../gmail-mcp-server/node_modules`

From a case directory:

```bash
make gmail
make gmail GMAIL_FLAGS="--dry-run"
make gmail GMAIL_FLAGS="--force"
```

You can override the server location if needed:

```bash
make gmail GMAIL_SERVER_DIR="/custom/path/to/gmail-mcp-server"
```

The Gmail exporter reads `gmail_addresses:` from the current case's
`envelopes.yaml` and writes PDFs into `assets/gmail/`.

## Known limits

- The script does not yet build tables of authorities, TOCs, bookmarks, Bates numbering, OCR, or embedded text extraction from image exhibits.
- The script assumes all exhibit attachments are already in final visual form.
- It does not validate county-specific exhibit tab color rules or divider-stock practices; it generates printable paper tab sheets, not physical tabs.
- It does not inspect the substantive admissibility of the attached documents.

## Practical recommendation

This format is a solid engineer-friendly way to draft and produce a filing PDF from Markdown while keeping line numbers, line spacing, caption layout, and exhibit assembly deterministic.

For ordinary California trial-court pleadings and declarations, it is a sensible starting point.
