# 0006 — JC forms as YAML descriptors, one engine

**Status:** accepted (2026-08); supersedes the per-form Python fillers

## Context
Five hand-written fillers duplicated caption logic and buried
hard-won, empirically verified field knowledge in code. The ambition
is every JC form, then other jurisdictions — hundreds of forms.
Field names lie; forms revise silently; fillable layers break.

## Decision
A form is a YAML descriptor (field maps with verified meanings, fit
strategies, checkbox on-states, chrome list, revision, agent_guide);
one engine executes descriptors (acroform fill + overlay escape
hatch + fit/overflow machinery). Adding a form = authoring + verifying
a descriptor; no engine changes.

## Consequences
Registry growth is data work agents can do (with mandatory
render-and-inspect verification); descriptors double as machine-
readable documentation; revision drift is testable mechanically.
Bespoke dynamic behavior (a cover form's attached-page count) still needs code —
kept as thin adapters rather than complicating the schema for one
form. Legacy fillers remain until fully re-verified, then retire.
