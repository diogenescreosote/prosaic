# Spec: the pleading generator and envelope system

## Purpose

A person with a case and a text editor should be able to write a
pleading as plain Markdown and get back a PDF a California clerk
accepts and an opposing counsel cannot mock — correct pleading-paper
anatomy, correct caption, professional typography — without owning
Word, counting lines, or hand-assembling exhibit packets. The
envelope system extends that promise from one document to one
*filing*: a named group of sources (motion, declaration, proposed
order, exhibits, JC cover forms) that builds as a unit, rebuilds
only what changed, and refuses to quietly overwrite what was already
sent to a court.

## Promises

1. **Real pleading paper.** Output is U.S. Letter with numbered
   lines 1–28 in the left margin, a vertical rule, 12 pt body type,
   body text aligned to the line grid, and a footer (rule, page
   number, uppercased paper title) — tracking Cal. Rules of Court
   2.103–2.111. *(tested: line-number, pagination, and AI
   filing-readiness checks in the pleading_build scenario; 28-line
   grid alignment (pypdf baseline coordinates), per-page line numbers,
   consecutive footer page numbers, and footer titles on every page of
   multi-page documents in the pleading_typography scenario)*
2. **A correct first-page caption** built from front matter alone:
   filer block upper-left, stamp space clear upper-right, court
   title, two-column party table with case number, paper title, and
   hearing information, then the body on the grid. *(tested: caption
   and perjury-clause assertions; AI judgment)*
3. **Typography is enforced, not requested.** `---` renders as an em
   dash and `--` as an en dash with surrounding whitespace preserved
   literally — which is precisely why sources must never space
   them; straight quotes become smart quotes; heading numbering
   (I., II., …) is automatic and unconditional, so hand-typed
   numerals stack rather than replace. The rendered artifact, not
   the source, is the compliance surface. *(tested: em/en dash and
   no-spaced-dash assertions in both scenarios; dash edges adjacent to
   quotes/numbers, nested smart quotes, possessives (including after an
   abbreviation's period), section symbols, heading nesting/restarts,
   hand-numbered-heading stacking, and a spaced-dash negative control
   in the pleading_typography scenario — which also pins that a
   spaced-dash source renders wrong (with a stderr warning) rather
   than failing the build, and that a clean source builds without the
   warning)*
4. **Block quotes are blocks, not lines.** Consecutive `>` lines merge
   into one block and are rewrapped to the indented measure, so source
   line breaks never survive into the artifact. The block renders 36 pt
   from the left margin on consecutive grid lines — the same leading as
   body text, never looser — with no bullet, no `>` glyph, and no
   quotation marks added. *(tested: indent measured against the body
   margin, absence of `>` and of added quote marks, and a merge check
   that fails if the renderer honors source line breaks, in the
   pleading_typography scenario)*
5. **Exhibits are symbolic.** Body text references exhibits as
   `\exhibit{shortname}` / `\attachment{shortname}`; letters are
   assigned at render time, so reordering exhibits never orphans a
   reference, and the macro expands to the full label ("Exhibit A")
   so doubled labels are a detectable bug. Exhibit appendixes get an
   exhibit list, tab sheets, and images/PDFs scaled onto Letter
   pages. A `pages:` spec that references a page the PDF does not
   have — or a reversed range — fails the build; exhibits are never
   silently truncated. *(tested: lettering/list-order, re-reference,
   pages-spec, tab-sheet, link-annotation, exhibit_source, and
   out-of-range/reversed pages-spec failure checks in the
   pleading_exhibits scenario)*
6. **Cover forms are part of the build.** A `cover_sheet:` key on a
   source prepends the named JC form (MC-030, CIV-110, EFS-020),
   filled from the same front matter the pleading
   uses — one set of case facts, two renderings. *(tested: envelope
   scenario asserts the cover form precedes the declaration body)*
7. **No drafting history leaks into a filing.** Sources carry no
   revision narration (the matter conventions forbid it), and the
   rendered output contains no NOTREAL markers, TODO/FIXME tokens,
   or draft annotations. *(tested: leak-scan in the pleading_build
   scenario)*
8. **Rebuilds are deterministic and dependency-aware.** A build
   regenerates a source when the source, any selected exhibit, or
   any exhibit-letter mapping file is newer than the output —
   otherwise it skips; `check-stale` fails loudly when outputs lag
   dependencies; a forced rebuild is always available. *(tested:
   up-to-date skip, exhibit/exhibit_source/variant-companion staleness,
   and check-stale checks in the pleading_exhibits scenario)*
9. **Sent envelopes are protected.** Marking an envelope with the
   date it was sent or filed makes routine rebuilds skip it and
   explicit rebuilds require force — the on-disk output of a mailed
   packet is a record, not a build artifact. *(tested: refusal,
   --all skip, and --force override in the pleading_exhibits
   scenario)*
10. **Sealed/public variants from one source.** `\redact{}` macros
   render the sealed text in the sealed variant and the public
   substitute in the public one, with justifications collected into
   a redaction log — one source of truth for two filings. The
   `.redactions.json` sidecar quotes the verbatim sealed text, so it
   is written only alongside the sealed variant: every file in a
   public output directory is free of sealed bytes, because that
   directory ships as "the public packet". A `\redactionlog` source
   file that is missing or unparseable fails the build — the log
   exists to demonstrate completeness, so it must never silently
   shorten. *(tested: pleading_exhibits scenario proves sealed
   strings absent from the public PDF's text, raw bytes, and decoded
   streams AND from every file in the public output directory, plus
   sealed-side sidecar contents, redaction-log rendering, and
   missing-log-source failure)*
11. **Proposed orders ship editable.** A source flagged for it emits
    a `.docx` alongside the PDF, satisfying the editable-copy
    obligation that travels with e-filed proposed orders.
    *(tested: docx: true emission and content checks in the
    pleading_exhibits scenario; the pleading_typography scenario opens
    the emitted .docx with python-docx and verifies dash conversion,
    Word-native multilevel heading numbering, real footnotes.xml
    footnotes, and a kept-together signature block)*
12. **Companion documents that must be served separately are built
    with the document that requires them.** A source declares its
    consumer/employee notices as data (`consumer_notices:`, one entry
    per person whose records a subpoena reaches) and the build emits
    one filled SUBP-025 per recipient beside the source's own PDF,
    named `<stem>.subp025.<slug>.pdf`, captioned from the same front
    matter. The notices are separate files, never merged into the
    document: each is served on a different person, with a copy of the
    subpoena, on its own statutory clock (Code Civ. Proc. §§ 1985.3,
    1985.6). A malformed or colliding entry fails the build rather
    than producing a packet with a missing notice. *(tested: envelope
    build in the form_filling scenario asserts two correctly addressed,
    correctly captioned notices and that neither was merged into the
    subpoena; unit coverage of naming, shared/per-entry precedence,
    mandatory blanks, and every failure path in
    pleading/tests/test_forms_adversarial.py)*

- **An envelope renders its documents in parallel.** Planning
  (staleness checks, ordering, log lines) is cheap and
  order-dependent; rendering is expensive and embarrassingly parallel,
  since each job reads shared inputs read-only and writes one output
  nobody else touches. `-j N` / `PROSAIC_BUILD_JOBS` sets the pool;
  `-j1` serializes for bisecting a failure. Output is byte-identical
  to a sequential build — that is the promise, not merely the
  intent — and child output is captured and printed per job rather
  than interleaved. *(tested: envelope build scenarios; parity against
  a sequential build was verified when the change landed)*
- **An unfiled document announces itself on every page.** A source
  carrying `notreal:` renders that marker as a red banner in the top
  margin of every page of the assembled packet — including filled
  Judicial Council forms and merged exhibits — in the DOCX page
  header, and atop the TXT. The band is reclaimed by scaling page
  content, never overlaid, so it cannot collide with a form's own
  header; pagination is unchanged, so a page-and-line citation taken
  against the draft still holds. Removing `notreal:` is what clears
  it. See [ADR 0015](../../design/adr/0015-unfiled-documents-announce-themselves.md),
  [ADR 0017](../../design/adr/0017-banner-stamps-the-whole-packet.md).
  *(tested: pleading/tests/test_draft_banner.py)*
- **A Judicial Council form attachment is never captioned as a
  standalone pleading**, and the build fails rather than producing
  one. A source whose `paper_title` begins `ATTACHMENT`, or which
  declares a subpoena cover sheet, must set `no_caption: true`; the
  form carried the attorney block, court name and party caption one
  page earlier. A declaration behind a motion's cover form is deliberately not
  caught — it is a distinct document and is captioned normally. See
  [ADR 0018](../../design/adr/0018-form-attachments-are-not-pleadings.md).
  *(tested: pleading/tests/test_form_attachment_caption.py)*
- **Front-matter keys nothing reads produce a warning, never an
  error.** Recognized keys are enumerated in
  `pleading/front_matter_keys.yaml`; anything else warns at build
  time, naming the key and saying it has no effect. An unrecognized
  key means the author expected something that will not happen —
  worth saying out loud, not worth refusing to build a filing over.
  *(untested)*

## Non-obvious constraints

- **The substitution layer preserves whitespace literally**, so
  style violations become *subtly wrong output*, not build errors.
  This is a deliberate trade (the generator never rewrites an
  author's spacing) and the reason the writing-style checks are
  phrased as verify-in-the-artifact greps. The build does, however,
  emit a stderr warning for each spaced-dash (`' --- '` / `' -- '`)
  source line so the authoring error is caught at build time.
- **Heading auto-numbering has no opt-out** — lead-in and closing
  prose sit unheaded rather than consuming outline positions. An
  opt-out would reintroduce the hand-numbering drift the rule
  exists to kill.
- **A companion notice is not a cover sheet.** `cover_sheet:` fills
  one form and prepends it to the document; `consumer_notices:` fills
  N forms and leaves them beside it. The difference is a service fact,
  not a layout preference: a Notice to Consumer travels to the
  consumer, addressed individually, while the subpoena travels to the
  custodian, so merging them would both misdirect the notice and
  disclose one consumer's identity to another.
- **Statewide rules are the target, not local ones.** The defaults
  satisfy CRC trial-court format; county-specific tab, color, and
  department preferences remain the filer's problem, and the
  generator must not pretend otherwise.
- **The unredacted source and sealed outputs never feed a public
  variant by accident** — public builds fail toward substitution, not
  passthrough, and *sealed output always requires an explicit
  `--variant sealed`*: a build with no `--variant` renders any
  redaction-bearing source as its PUBLIC variant, with a loud stderr
  warning. The least-careful invocation produces the least-sensitive
  artifact; only documents with no variant-sensitive content (for
  which the variants are identical) default to the sealed branch.
  *(tested: no-variant envelope build defaults-to-public check in the
  pleading_exhibits scenario)*
- Fonts are bundled (a metric-compatible Century Schoolbook clone)
  so output does not vary with the host machine's font library.
