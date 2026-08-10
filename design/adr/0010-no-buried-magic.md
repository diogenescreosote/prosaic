# 0010 — No buried magic; extraction where it pays

**Status:** accepted (2026-08)

## Context
The codebase was extracted from bespoke personal scripts where page
geometry, legal boilerplate, thresholds, and paths live as inline
literals. That was fine for one user's cases; it resists
generalization (other courts, other states) and hides decisions from
review. But total configurability is its own disease.

## Decision
Literals representing revisable decisions move to named constants,
descriptors/config, or templates. Litmus test: would a contributor
adapting prosaic to another jurisdiction (or a reviewer checking
legal correctness) need to FIND this value? Then it must be findable —
named, grouped, documented. Self-defining literals may stay inline
with a comment. Applies strictly to new code; existing code migrates
during refactors (the pleading-generator grand refactor is the first).

## Consequences
Jurisdiction-dependent behavior becomes visible surface area; the
grand refactor has a stated target; some ceremony added to quick
scripts (accepted). The refactor audit (design/refactor-audit/) is the
running inventory of existing violations.
