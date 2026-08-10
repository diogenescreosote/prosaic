# 0009 — Tiered nonblocking testing with delegated cheap-model runs

**Status:** accepted (2026-08)

## Context
Development here is agent-driven and fast; a full suite (with AI
judgments) takes minutes and real tokens. Serializing every change
behind a full run would halve throughput; skipping runs would let
agents build on broken layers — the most expensive failure mode there
is, because everything above the break is suspect.

## Decision
Three tiers with distinct blocking semantics: Tier 0 (narrowest
affected tests, inline, always blocking, seconds), Tier 1 (generous
component+scenario sweep, forked to a background `tester` subagent on
a cheaper model, blocking only when the next task depends on the
change), Tier 2 (full suite incl. AI judgments, background, gating
feature-closing checkpoints only). Back-pressure: ≤2 unresolved sweeps
outstanding; any red preempts new feature work. Test execution is
delegated to `.claude/agents/tester.md` (Sonnet, read-only + Bash),
which triages failures and reports in a fixed compact format. The
contract binds agents via the repo CLAUDE.md.

## Consequences
Development pipelines stay full while regressions surface within one
or two work units of their cause; frontier-model tokens go to
authoring and diagnosis, not routine execution. Costs: occasional
rework when a background sweep reddens work built meanwhile (bounded
by the two-sweep cap and the dependency-blocks rule), and triage
quality limited by the cheaper model (mitigated: testers quote judge
rationales verbatim and never rerun-until-green; the primary agent
owns diagnosis).
Alternatives: block-on-everything (rejected: throughput); CI-only
testing (rejected: agents need signals mid-session, not post-hoc).
