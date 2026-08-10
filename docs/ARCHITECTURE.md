# Architecture

## The split that matters

prosaic is organized around one boundary: **the model classifies, extracts,
and drafts prose; the engine computes, validates, and renders.** Everything
below `prosaic/agent/` is deterministic — same inputs, same bytes out. The
agent layer can act on the engine only through typed tools, and no tool
exists that accepts model-generated dates as authority for anything.

## Layers

```
prosaic/
  deadlines/    statutory date computation. Pure functions over dates, a
                service-method enum, and a court calendar. Stdlib only —
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

1. **Ingest.** A `RecordSource` yields `FetchedDocument`s — raw bytes plus a
   locator. `ingest()` hashes each one; the SHA-256 is the identity, so the
   same PDF arriving from two sources joins the matter once. Original bytes
   are never modified.
2. **Model.** `Matter` validates referential integrity on construction:
   service events must point at known documents and parties, counsel at
   known parties, exhibits at known documents. A `Matter` that exists is
   internally consistent. Values that flow into filings or deadline
   computation are `Fact[T]` with provenance.
3. **Compute.** Deadline rules take facts (a date, a method) and a
   `CourtCalendar`, and return a `Deadline` — date, citation, description.
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
- The operator loop is tested against a scripted client — including
  malformed tool input, unknown tools, refusals, and the turn budget —
  so no test depends on the network.
- A leak guard walks every tracked file and every commit message for
  content that must not appear in this repository, and runs in CI.
