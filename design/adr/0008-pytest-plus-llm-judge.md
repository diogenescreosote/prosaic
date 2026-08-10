# 0008 — pytest + in-house LLM judge for the test harness

**Status:** accepted (2026-08)

## Context
Correctness here is two-natured: mechanical invariants (a field is
blank; a page exists) and judgments (this render is court-ready; this
declaration reads professionally). We want scenario tests — whole
fixture matters operated on by the real system — with both kinds of
checks, in a framework contributors already know.

## Decision
pytest is the harness; scenarios are fixture matters under
tests/scenarios/ copied to tmp and operated on for real. AI checks are
a ~150-line judge (tests/harness/ai.py) that shells out to the claude
CLI the project already requires, returns {score 0-10, hard_failures,
rationale}, passes on threshold+no-hard-fail, caches verdicts by
artifact hash, and is marked `@pytest.mark.ai` (skipped when
unavailable, so CI without AI still runs every deterministic check).

## Consequences
No new dependencies or API keys; judged tests degrade gracefully;
rationales make flaky verdicts diagnosable; caching makes reruns
cheap. We forgo the metric libraries of DeepEval/inspect-ai — worth
revisiting if evals grow past a handful of rubrics; the judge's
interface (task/rubric/hard_failures/threshold) was chosen to map
cleanly onto them.
