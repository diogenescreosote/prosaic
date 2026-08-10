# 0003 — Connectors as processes with a NEW-line protocol

**Status:** accepted (2026-08)

## Context
Sources differ per case and will be written by strangers. The
orchestrator must run connectors it has never heard of, and a broken
connector must not corrupt a matter or block the others.

## Decision
A connector is a directory with a manifest and an executable entry
invoked as `node pull.js <matter_dir>`. Its whole output contract is
textual: `NEW <absolute path>` per new file on stdout, diagnostics on
stderr, nonzero exit on failure. State lives in
`<matter>/.state/<name>.json`; pulls must be idempotent.

## Consequences
Connectors are swappable ad libitum and testable in isolation; the
orchestrator needs no per-connector knowledge; a crash costs one
source, one cycle. The protocol can't express richer results
(progress, partial success) — deliberately: anything richer becomes a
private API that resists third-party connectors.
Alternatives: in-process plugin API (rejected: language lock-in,
crash blast radius); message queue (rejected: infrastructure for a
laptop tool).
