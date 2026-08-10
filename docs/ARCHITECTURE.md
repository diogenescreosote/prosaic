# Architecture

## The split that matters

prosaic is organized around one boundary: **the model classifies, extracts,
and drafts prose; the engine computes, validates, and renders.** Everything
below `prosaic/agent/` is deterministic: same inputs, same bytes out. The
agent layer can act on the engine only through typed tools, and no tool
exists that accepts model-generated dates as authority for anything.

## Layers

```
prosaic/
  deadlines/    statutory date computation. Pure functions over dates, a
                service-method enum, and a court calendar. Stdlib only:
                no pydantic, no I/O except loading packaged holiday data.
  model/        the case model: matter, parties, counsel, court, documents,
                exhibits, service events, docket entries. Pydantic v2.
                Extracted values are Fact[T]: value + provenance to a
                source document and page, or to the user.
  forms/        AcroForm reading/filling and the form-pack interface.
                Jurisdiction-agnostic: it knows how to fill fields, not
                what any field means.
  packs/civil/  the California general civil pack: six Judicial Council
                form modules, the shared caption builders, and the official
                blank PDFs. All jurisdiction knowledge lives here.
  documents/    court paper that isn't a JC form: pleading paper per
                CRC 2.100-2.119 and exhibit assembly.
  ingest/       record sources behind one protocol (filesystem, IMAP) and
                content-hash deduplication into the matter.
  agent/        the LLM operator: system prompt, typed toolkit, tool loop.
  cli/          typer entry points; thin shells over the library.
```

Dependencies point downward only. `deadlines` imports nothing from the
project; `model` imports the `ServiceMethod` enum from `deadlines` (service
facts drive deadline computation, so the pure layer owns the vocabulary);
`packs` import `forms`, `model`, and `deadlines`; `agent` imports everything
below it and adds no computation of its own.

## Data flow

1. **Ingest.** A `RecordSource` yields `FetchedDocument`s: raw bytes plus a
   locator. `ingest()` hashes each one; the SHA-256 is the identity, so the
   same PDF arriving from two sources joins the matter once. Original bytes
   are never modified.
2. **Model.** `Matter` validates referential integrity on construction:
   service events must point at known documents and parties, counsel at
   known parties, exhibits at known documents. A `Matter` that exists is
   internally consistent. Values that flow into filings or deadline
   computation are `Fact[T]` with provenance.
3. **Compute.** Deadline rules take facts (a date, a method) and a
   `CourtCalendar`, and return a `Deadline`: date, citation, description.
   Calendars carry an explicit coverage window and raise on dates outside
   it. See [DEADLINES.md](DEADLINES.md).
4. **Render.** A pack's form module turns `(Matter, context)` into exact
   AcroForm field values, validated and raised as `FormValidationError`
   when the matter lacks something the form needs. The filler rejects
   unknown field names and ill-fitting values rather than producing a
   silently incomplete form. Golden tests pin the values and read them back
   out of the produced PDFs.
5. **Operate.** The `Operator` runs a Messages-API tool loop with three
   tools: `matter_summary` (read the model), `compute_deadline` (the only
   source of dates), `list_forms` (the pack catalog). Tool handlers parse
   the model's JSON with pydantic before touching the engine and return
   error results rather than raising, so a malformed call is a correctable
   turn, not a crash. A refusal from the model's safety layer raises to the
   human operator; nothing is silently rerouted.

## Testing posture

- The engine's golden dates were hand-computed against the holiday
  calendar, then a Hypothesis suite asserts the invariants over the whole
  coverage window (never-on-a-holiday, extensions never shorten,
  monotonicity, backward/forward round-trip).
- Form modules have golden-file tests: exact expected field values
  committed as JSON, plus read-back from the rendered PDF.
- The operator loop is tested against a scripted client (malformed tool
  input, unknown tools, refusals, the turn budget)
  so no test depends on the network.
- A leak guard walks every tracked file and every commit message for
  content that must not appear in this repository, and runs in CI.

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
                                               │ Claude Code pass per sync)
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
   [Claude Code](https://claude.com/claude-code) session, running
   inside the matter directory under the matter's `CLAUDE.md`
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
