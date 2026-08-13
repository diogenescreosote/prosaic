# 0024 — Judgment work as files-first flows; build work stays in Make

**Status:** accepted (2026-08)

## Context
prosaic has two kinds of multi-step work. Deterministic build DAGs
(render, assemble, stamp) belong to Make: correct dependency
semantics, universally understood, nothing to invent. Judgment work
— drafting loops, adversarial review, research passes — has a
different shape: steps are agent invocations, edges include "try
again until the judge is satisfied," and a human decision belongs in
the middle. Encoding that in Make means fake targets and hidden
state; adopting an orchestration framework (LangGraph and kin) means
a heavy dependency, provider SDK coupling that ADR-0020 just removed,
and control flow living in a library instead of in a file someone
can read (against ADR-0010).

## Decision
A flow is a YAML file: ordered steps of four kinds (`agent`,
`command`, `judge`, `gate`), where a judge's `on_fail` back-edge is
the loop construct, bounded by `max_rounds`. `flows/run.py`
(surfaced as `sc flow`) executes one: every step's product is a file
in a run directory, state is a JSON file beside them, a `gate` stops
the run (exit 3) until a human renames the approval file, and
`--resume` continues from disk. Agent steps go through
`cli/agent-run`, so flows are harness-agnostic and the tests script
the agent with `PROSAIC_AGENT_CMD`.

Templates substitute the *paths* of prior outputs, not their
contents: agents read files, and a run directory a human can inspect
and edit mid-flight is the point of the design.

## Consequences
Drafting and research loops become reviewable artifacts (the flow
file) instead of session lore, and an interrupted loop costs nothing.
The runner is deliberately small — sequential, one back-edge kind, no
parallelism — and should grow features only when a real flow needs
them. Make keeps the build DAGs; nothing in a flow should shell out
to work Make already owns except by calling Make.
