# Matter layout

A *matter* is one case (or pre-litigation dispute) in one directory.
The layout is deliberately opinionated: humans, scripts, and AI agents
all navigate the same structure, and the conventions in
[conventions.md](conventions.md) assume it.

```
smith-v-smith/
├── matter.yaml            # case metadata + connector config
├── envelopes.yaml         # filing envelope definitions (build config)
├── CLAUDE.md              # the matter-level AI agent contract
├── KNOWLEDGE.md           # durable case knowledge (posture, people, timeline)
├── TODO.md                # live task list (delete resolved items)
├── QUESTIONS.md           # open interview prompts
├── README.md              # human orientation
├── Makefile → prosaic/pleading/Makefile
│
├── inbox/                 # drop zone; unprocessed by definition
├── processed_files/       # canonical raw bytes of triaged inbox material
│                          #   (see its MANIFEST.md)
├── assets/                # evidence, organized by topic
│   ├── INDEX.md           # AUTHORITATIVE description of every asset
│   ├── gmail/             # connector output: thread PDFs + CATALOG.md
│   ├── audio/             # recordings + transcript sidecars
│   └── <topic>/...        # correspondence/, court_filings/, exhibits/, …
├── pleadings/             # filed/court documents:
│                          #   YYYY-MM-DD_description.pdf (+ _ocr siblings)
├── discovery/             # records produced under subpoena/discovery
├── lawyer_drafts/         # drafts exchanged with counsel
├── unfiled/               # lodged-but-returned / otherwise unfiled
├── memos/                 # analysis & strategy memos (work product)
├── src/                   # pleading Markdown sources
├── out/                   # build output (generated; per envelope)
└── .state/                # connector + sync state (gitignored)
```

## The load-bearing pieces

**`assets/INDEX.md`** is the heart of the system: one row per asset
saying what it is, its date, who made it, and why it matters — with
per-directory sections. The rule is absolute: *any* change under
`assets/` updates INDEX.md in the same change. This is what makes the
matter navigable by an agent that has never seen it before, and
auditable by a human who wants to know what the AI did.

**`KNOWLEDGE.md`** is durable case knowledge — procedural posture,
key people, a dated timeline, established facts with sources. It is a
living document that new facts are *integrated into*, not a log that
gets appended to. When it gets long, sections keep it navigable; when
facts are superseded, they're corrected, with git holding history.

**`pleadings/`** holds the court record: file-stamped or conformed
documents only, named `YYYY-MM-DD_snake_case_description.pdf` so they
sort chronologically. Drafts never live here — that's what
`lawyer_drafts/` and `src/` are for. Scanned filings get `_ocr`
siblings like any asset.

**`inbox/` → `processed_files/` + `assets/`** is the triage pipeline:
material arrives in `inbox/` (by hand or by connector), gets a
literate snake_case name, OCR supplement, text sidecar, and INDEX row,
and its original bytes are preserved in `processed_files/`. An empty
inbox means everything is processed ("inbox zero" is a meaningful,
checkable state).

## Naming

- Dated documents: `YYYY-MM-DD_what_it_is.pdf` (ISO dates sort).
- Undated evidence: literate snake_case that a stranger could
  understand — `sms_apology_demand_jul8_jul13.pdf`, not `IMG_4021.pdf`.
- Derived artifacts: `<stem>_ocr.pdf`, `<stem>.txt`, `<stem>.srt`
  siblings of the original stem.
- Fix misspellings in *names* freely; never alter *contents*.

## Git

Matters work well as git repositories (history = provenance), with
`.state/`, `out/`, and bulky regenerable connector output (e.g.
`assets/gmail/*.pdf`) in `.gitignore`. `sc init --git` sets this up.
