# 0001 — Plain files over a database

**Status:** accepted (2026-08)

## Context
A matter accumulates thousands of heterogeneous artifacts (PDFs,
audio, transcripts, notes) that humans, shell tools, git, cloud sync,
and AI agents all need to read. Litigation lasts years; tools rot.

## Decision
A matter is a directory of ordinary files. All metadata lives in
Markdown (INDEX.md, KNOWLEDGE.md, CATALOG.md) and YAML (matter.yaml).
No database, no sidecar store, no bespoke container formats.

## Consequences
Everything greps; git gives history/provenance/rollback for free; any
agent harness can navigate a matter with Read+Glob; nothing can hold
the case file hostage. We give up transactional integrity and query
speed — acceptable at matter scale (thousands, not millions, of
files) — and take on the discipline cost of keeping indexes in sync,
which the conventions (and triage prompts) carry.
Alternatives: SQLite catalog (rejected: second source of truth that
drifts from disk); document DB (rejected: everything above, worse).
