# Spec: files-first flows (`sc flow`)

## Purpose

Give judgment work — drafting loops, adversarial review, research
passes — the same reviewability a Makefile gives builds: the graph is
a YAML file, every intermediate is a file, and a human gate is a
first-class step (ADR-0024).

## Promises

- **`sc flow run.py <flow.yaml> [--input k=v]...`** validates the
  flow before anything runs (unknown step kinds, duplicate ids, an
  `on_fail` naming no step, and missing declared inputs are errors),
  then executes steps in order into a fresh `.flow/<name>-<stamp>/`
  run directory. *(tested: tests/test_flows.py)*
- **Every step's product is a file** in the run directory (default
  `<id>.md`), and prompt templates substitute input values and the
  PATHS of prior outputs — `{review}` is where the review lives, not
  its text. An unknown placeholder is a clear error.
  *(tested: tests/test_flows.py)*
- **`judge` steps loop**: a score below `threshold` jumps back to
  `on_fail` and re-runs everything from there, at most `max_rounds`
  times, then fails the run; a passing score continues. The verdict
  (score + rationale) lands in the step's file either way.
  *(tested: tests/test_flows.py)*
- **`gate` steps stop the run** (exit 3) with an
  `APPROVAL-<id>.pending` file saying how to approve; nothing past
  the gate runs. After the human renames it `.approved`,
  `--resume <rundir>` continues exactly where the run stopped —
  which also holds for any interrupted run. *(tested:
  tests/test_flows.py)*
- **Agent and judge steps go through `cli/agent-run`** (ADR-0020),
  granted read access to the run directory; no other provider
  coupling exists, and `PROSAIC_AGENT_CMD` substitutes a scripted
  agent in tests. *(tested: tests/test_flows.py)*

## Non-obvious constraints

- **Flows never edit matter sources.** A flow writes into its run
  directory; adopting a revision into `src/` is a human act (the
  draft-review flow's gate says exactly this). This is the
  change-authority rule from the matter contract, enforced by shape.
- The runner is sequential on purpose. Parallel fan-out, sub-flows,
  and richer routing are features a real flow has to justify first.
