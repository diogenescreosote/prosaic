# 0019 — One system, not two: the typed library is removed

**Status:** accepted (2026-08)

Supersedes the unrecorded arrangement described in ROADMAP Phase 0 under
"What's *duplicated* is the other half of Phase 0".

## Context

The repository carried two systems that did overlapping work.

The **operational tree** (`pleading/`, `cli/`, `connectors/`, `sync/`,
`triage/`, `templates/`) renders Markdown into filing-quality PDF and DOCX,
fills Judicial Council forms from YAML descriptors, pulls records from
connectors, and runs AI triage. It is what every live matter is built on.
Every spec in `specs/` describes some part of it, and every accepted ADR
from 0001 to 0018 is about it.

The **typed library** (`prosaic/`, 38 modules) held a pydantic case model
whose extracted values were `Fact[T]` — a value plus provenance — statutory
deadline computation, a second Judicial Council form system as typed Python
modules under `packs/civil/`, filesystem and IMAP ingestion, an LLM operator
exposing three typed tools, and a second CLI. It also held
`documents/pleading.py`: a 182-line pleading generator with no Markdown
parsing, beside the 3,392-line one the matters actually use.

Three facts settled this:

1. **Nothing imported it.** No file under `pleading/`, `cli/`,
   `connectors/`, `sync/`, `triage/` or `templates/` contained
   `import prosaic` or `from prosaic`. The library fed nothing.
2. **It was never specified or decided on.** `specs/` has no entry for it.
   No ADR proposes it. It accreted.
3. **Its form system contradicted an accepted ADR.** ADR-0006 is "JC forms
   as YAML descriptors, **one engine**". `packs/civil/` was a second engine,
   with its own blanks, for six overlapping forms.

The whole lint and coverage configuration existed to serve it: `ruff` and
`mypy --strict` excluded every operational tree by name so they could check
the library, and `--cov=prosaic` with a 95% floor measured only it. The
result read as rigour applied to the system, when it was rigour applied to
the part of the system nothing used.

## Decision

Delete the typed library, its 14 test modules, its two documentation pages
(`DEADLINES.md`, `FORM_PACKS.md`), its console script, its packaging, and
the coverage gate that measured only it. The repository ships no importable
Python package: the entry point is the `sc` shell CLI and the scripts under
`pleading/`, run by path, which is already how every matter invokes them.

The official blank AcroForms it carried are **kept**, moved to
`pleading/forms/`. They are government documents rather than part of the
design, and they are the raw material for descriptors.

## Consequences

**What gets easier.** One form system, one generator, one CLI, one place a
change to rendering can live. The test suite measures the code that runs.
Documentation stops describing two architectures as if both were load
bearing.

**What we gave up, concretely.** Statutory deadline computation is gone:
CCP §§ 12–12c arithmetic, the § 1005(b) motion-notice schedule,
§ 430.40(a), the § 1013 / § 1010.6 service extensions, CRC 3.110(b) and
3.725(a), the packaged 2025–2028 holiday calendars, and the Hypothesis
property suite over them. Nothing else in the tree computes a date. The
README's former "no date is ever produced by a language model" promise
described a `compute_deadline` tool that no longer exists; the durable half
of that rule — the model drafts prose, the engine renders it — is what the
README now states.

CM-010, CM-110, MC-031 and SUM-100 are no longer fillable. They existed
only as typed pack modules. Their blanks are in `pleading/forms/` and a
descriptor for each is ordinary work whenever one is needed. POS-010 is
less affected: proofs of service are generated as pleadings from Markdown,
which is the path the matters use.

Also gone: the typed case model and per-fact provenance, IMAP and
filesystem ingestion, and the LLM operator's tool loop.

**What gets harder.** Nothing is linted or type-checked but the handful of
tests written here directly, because every remaining tree is excluded by
design (ported style, kept mergeable with upstream). That was already true
of the code that does the work; it is now visible rather than masked by a
97% figure measured elsewhere. Reinstating a quality gate over `pleading/`
is a real option and a separate decision.

## Alternatives considered

**Converge the operational tree onto the library.** Rejected: it would mean
reimplementing 3,392 lines of load-bearing, exercised rendering inside a
model nothing had validated, while five matters filed off the original.

**Keep both and draw a boundary.** Rejected as the status quo that produced
the confusion — two form systems, two generators, two CLIs, and a coverage
number that flattered the wrong half.
