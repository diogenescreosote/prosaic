# Matter layout

A *matter* is one case (or pre-litigation dispute) in one directory.
The layout is deliberately opinionated: humans, scripts, and AI agents
all navigate the same structure, and the conventions in
[conventions.md](conventions.md) assume it.

```
smith-v-smith/
├── matter.yaml            # case metadata + connector config
├── envelopes.yaml         # filing envelope definitions (build config)
├── AGENTS.md              # the matter-level AI agent contract (CLAUDE.md points here)
├── KNOWLEDGE.md           # durable case knowledge (posture, people, timeline)
├── TODO.md                # live task list (delete resolved items)
├── QUESTIONS.md           # open interview prompts
├── README.md              # human orientation
│
├── inbox/                 # drop zone; unprocessed by definition
├── processed_files/       # canonical raw bytes of triaged inbox material
│                          #   (see its MANIFEST.md)
├── assets/                # evidence, organized by topic
│   ├── INDEX.md           # AUTHORITATIVE description of every asset
│   ├── gmail/             # connector output: thread PDFs + CATALOG.md
│   ├── audio/             # recordings (transcripts under derived/text/)
│   └── <topic>/...        # correspondence/, court_filings/, exhibits/, …
├── pleadings/             # filed/court documents:
│                          #   YYYY-MM-DD_description.pdf (OCR copies under derived/ocr/)
├── discovery/             # discovery instruments as served (subpoenas, notices,
│                          #   requests), their signed proofs of service, and
│                          #   records produced under them
├── staging/               # signed sets on their way out: YYYY-MM-DD_topic/
│                          #   with a README.md inventory (signed-unfiled papers,
│                          #   signed proofs, e-signature returns + audit logs)
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

## Where proofs of service live

A proof of service passes through up to four places, and a search for
one covers all of them --- never conclude a proof is missing from one
directory:

| Stage | Where |
|---|---|
| Source | `src/<dir>/`, beside the served document's source (`<served_stem>.efs050.md` for electronic service; a pleading-paper proof of personal service by any name). A form-only proof filled from data, such as a subpoena's page 2, keeps its data under `staging/<date>_<topic>/data/` |
| Build | `out/<envelope>/` --- unsigned and regenerable, never the record. A filled form may also leave an unsigned cache copy under `assets/decl_cover_sheets/`; that is a cache, not a proof |
| Signed | `staging/<YYYY-MM-DD>_<topic>/`, with the e-signature audit log and a `README.md` that lists each proof, what it proves and whether it is signed. The signed copy carries `_SIGNED` (or `_SIGNED_UNFILED`), never the build's bare name |
| Triaged | **filed** with the court: `pleadings/` with its MANIFEST row. **Served and held** (discovery instruments, notices): `discovery/`, beside the instrument it proves, original bytes in `processed_files/`. A third party's proof (a process server's) arrives through triage and lands the same way |

Proofs the other side serves on you are received material: they
arrive through the mail connector (`assets/gmail/`) and, once
triaged, sit in `pleadings/` as `as-served` when they accompany a
filing.

## Naming

- Dated documents: `YYYY-MM-DD_what_it_is.pdf` (ISO dates sort).
- Undated evidence: literate snake_case that a stranger could
  understand — `sms_apology_demand_jul8_jul13.pdf`, not `IMG_4021.pdf`.
- Derived artifacts live in `derived/<kind>/<same relative path>` (ADR-0042):
  `derived/mail/messages.{tsv,md}` the per-message mail index (regenerated by `sc mail-index`),
  `derived/text/<path>.txt` page-marked text (tracked), `derived/ocr/<path>` the
  OCR'd copy (ignored, regenerable). Legacy `<stem>_ocr.pdf` / `<stem>.txt`
  siblings are still read; `sc text migrate` moves the tool's own into the tree.
  Older wording below refers to those legacy siblings
  siblings of the original stem.
- Fix misspellings in *names* freely; never alter *contents*.

## Git

Matters work well as git repositories (history = provenance), with
`.state/`, `out/`, and bulky regenerable connector output (e.g.
`assets/gmail/*.pdf`) in `.gitignore`. `sc init --git` sets this up.

Note which side of that line the mail sits on. `assets/gmail/*.pdf` is
a *rendering* and can be regenerated from `assets/gmail/mbox/` at any
time (`sc mail-render`), so ignoring it costs nothing.
`assets/gmail/mbox/` is the record and cannot be regenerated from
anything the matter holds --- commit it (ADR-0038).
