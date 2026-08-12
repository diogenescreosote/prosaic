# Architecture

## The split that matters

prosaic is organized around one boundary: **the model drafts prose; the
engine renders it.** A language model writes and revises Markdown. It never
lays out a page, assigns an exhibit letter, numbers a heading, or fills a
form field. Everything between a `.md` source and the PDF a clerk accepts is
deterministic: same source, same bytes out.

That boundary is what makes the output reviewable. A rendering defect is
reproducible, diagnosable from the artifact, and fixable once; a model that
formats prose is none of those things. It is also why the tests assert
against the produced PDF rather than the generator's own report of what it
did.

## Layers

```
pleading/       the renderer and the form filler.
  md_pleading.py      Markdown + YAML front matter -> 28-line California
                      pleading paper (CRC 2.100-2.119), exhibits, tab
                      sheets, footnotes, sealed/public variants.
  md_to_docx.py       the same source -> DOCX, for proposed orders that
                      must ship editable.
  md_to_txt.py        plain-text envelopes, for filings that take them.
  build_envelope.py   assembles the sources named in envelopes.yaml into
                      one filing packet, incrementally and dependency-aware.
  form_fill.py        one AcroForm engine, driven by the YAML descriptors
                      in forms/registry/. Jurisdiction knowledge lives in
                      the descriptors, never in the engine (ADR-0006).
  ocr_supplement.py   adds a text layer only to pages that lack one.
  redact_pdf.py       true redaction of received PDFs.
cli/sc          the entry point: init, sync, form, ocr, build, hooks.
connectors/     one process per source (gmail, mycase), each conforming to
                the NEW-line contract in ADR-0003.
sync/           runs every configured connector, then one AI triage pass.
triage/         the prompts that headless Claude Code runs inside a matter.
templates/      what `sc init` writes into a new matter, including the
                CLAUDE.md contract agents actually read.
```

There is no importable Python package. The scripts are run by path and the
CLI is a shell script, which is why a matter's `Makefile` includes
`pleading/Makefile` rather than depending on an installed distribution.

## Data flow

1. **A source is written.** Markdown with YAML front matter under a matter's
   `src/`. The front matter carries the caption, the exhibit list, the
   redaction map, and the flags that select a cover form or a DOCX
   companion. Recognized keys are enumerated in
   `pleading/front_matter_keys.yaml`; an unrecognized key warns rather than
   failing, because a silently ignored key would do nothing forever.
2. **The envelope is built.** `build_envelope.py` reads `envelopes.yaml`,
   resolves each source's exhibits and cover forms, and rebuilds only what
   is stale against its dependencies. An envelope marked with the date it
   was sent refuses to rebuild without force: the output of a mailed packet
   is a record, not a build artifact.
3. **The source is rendered.** `md_pleading.py` parses the Markdown into
   blocks, applies the typographic substitutions the house style depends
   on, auto-numbers headings in legal-outline style, resolves
   `\exhibit{}` macros to letters assigned at render time, and lays the
   result on the 28-line grid.
4. **Variants diverge from one source.** `\redact{sealed}{public}` and
   `public_disclosure:` on each exhibit produce the sealed and public
   packets from the same file, with a redaction log demonstrating
   completeness. The `.redactions.json` sidecar quotes sealed text, so it
   is written only beside the sealed variant.
5. **Companions are emitted, not merged.** Per-recipient notices are
   separate files served on different people on their own statutory clocks.

## Testing posture

- **Scenario suites** operate whole fictional matters for real: build the
  envelopes, then assert against the artifacts (pdftotext, pypdf baseline
  coordinates, python-docx) rather than the engine's self-report. Sentinel
  tokens planted in the fixture sources make truncation detectable.
- **Descriptor-drift alarms** check every registered form's descriptor
  against the blank PDF's actual field names, because Judicial Council
  revisions rename fields silently.
- **An LLM judge** covers the properties only judgment can see -- whether a
  render reads as court-ready -- with a calibration test that fails if the
  judge starts rubber-stamping, and a hard distinction between a bad verdict
  and an unreachable judge (ADR-0008).
- **A leak guard** walks every tracked file and commit message for content
  that must not appear in this repository, and runs at push time as well as
  in CI.

## The operational pipeline

Operationally, prosaic is a pipeline that turns the scattered raw material of a
legal case into an organized, searchable, AI-navigable matter
directory, and turns Markdown drafting into filing-ready documents.

```
 external sources                 the matter directory                    outputs
┌──────────────┐   connectors   ┌──────────────────────────────┐   build   ┌──────────────┐
│ Gmail        │ ─────────────▶ │ inbox/  → assets/ + INDEX.md │ ────────▶ │ out/<envelope>│
│ Portals      │   (scheduled   │ pleadings/   discovery/      │  (sc      │  pleading PDFs│
│ MyCase       │    12-hourly)  │ KNOWLEDGE.md TODO.md         │   build)  │  + DOCX       │
│ (yours here) │                │ QUESTIONS.md src/*.md        │           └──────────────┘
└──────────────┘                └──────────────┬───────────────┘
                                               │ AI triage (headless
                                               │ agent pass per sync)
                                               ▼
                                  catalogs, routing, knowledge updates
```

### The five layers

1. **Matter layout** ([matter-layout.md](matter-layout.md)). The
   directory convention every other layer assumes. Plain files,
   Markdown metadata, git-friendly.

2. **Connectors** ([connectors.md](connectors.md)). Small modules
   that pull external sources into the matter. Each conforms to a
   one-page contract (invoke with the matter dir; print `NEW <path>`
   lines; keep state in `.state/<name>.json`). Shipped: `gmail`,
   `mycase`.

3. **Sync + scheduling** ([scheduling.md](scheduling.md)).
   `sync/matter_sync.sh` runs every configured connector, then one AI
   triage pass over everything new. A launchd agent fires it every 12
   hours with catch-up-once semantics after downtime.

4. **AI triage** ([triage.md](triage.md)). A headless
   agent session (via `cli/agent-run`; Claude Code, Codex, or
   Gemini CLI), running
   inside the matter directory under the matter's `AGENTS.md`
   contract, catalogs each new file, routes staged documents to their
   homes, and folds case-significant facts into `KNOWLEDGE.md`.

5. **Pleading generation**
   ([../pleading/pleading_markdown_spec.md](../pleading/pleading_markdown_spec.md))
   converts Markdown + YAML front matter into California-style pleading
   PDF (and DOCX), assembled into filing "envelopes" defined in
   `envelopes.yaml`, plus Judicial Council form fillers and a PDF
   redactor.

### Data-flow invariants

- **Originals in, derivatives beside.** Nothing ever modifies received
  bytes; OCR layers, text sidecars, and transcripts are siblings.
- **Everything lands in the index.** A connector or triage pass that
  adds a file also adds the row describing it (INDEX.md, CATALOG.md).
- **State is per-matter and disposable.** Connector state lives in the
  matter's `.state/` (gitignored); deleting it means re-pulling, never
  data loss, because pulls are idempotent (existing exports are
  skipped by name or content hash).
- **Failure is quiet and retried.** A failed connector logs, exits
  nonzero, and leaves the sync guard un-advanced, so the next
  scheduled firing retries; nothing half-writes the matter.

### Repository ↔ matter separation

The repo (this code) contains no case data. A matter directory
contains no code, just config (`matter.yaml`, `envelopes.yaml`), a
symlinked `Makefile`, and content. Multiple matters share one repo
checkout; each schedules its own sync. This mirrors how the system is
actually run across several concurrent live matters.
