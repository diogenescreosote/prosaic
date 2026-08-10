# Development workflow

How prosaic gets built — by humans and by AI agents, who follow the
same rules (the agent-operative copy is the repo-root `CLAUDE.md`; this
page adds the rationale).

## Spec-first

Behavior changes start in `specs/` (what must be true) and, when a
choice crosses components, in `design/` (an ADR: what we decided and
why). This ordering is not ceremony: on a project built largely by
agents whose context evaporates between sessions, the spec is the only
durable statement of intent, and the test suite is the only durable
enforcement of it. Code ➜ spec drift gets caught because tests cite
specs and specs carry `(tested)` markers.

## Tests ride along, never trail

A feature lands *with* its tests: deterministic checks for mechanical
promises, AI-judged checks (docs/testing.md) for properties only
judgment can see, scenario fixtures when behavior spans components.
"I'll add tests later" is how a form filler ends up silently striking
text through a ruled line — the exact class of defect our AI judge
caught the day the harness went live.

## Documentation rides along too

The same rule, for the same reason. A capability nobody can find is a
capability nobody has, and the shortfall is invisible from the inside:
docs that are eight commands short read exactly like docs that are
complete. That is not hypothetical — six `sc` subcommands were added
across a single working session and none of them reached
`specs/cli.md`. Nothing failed, because nothing was checking.

Where a thing has to be written down depends on what it is:

| Added | Documented in |
|---|---|
| an `sc` subcommand | `specs/cli.md`, as a promise — help text is not the spec |
| a front-matter key | `pleading/front_matter_keys.yaml` and the markdown spec |
| a system binary the code invokes | `system-dependencies.yaml` |
| a matter-facing convention | `templates/matter/CLAUDE.md` |
| a decision that constrains later work | an ADR, indexed in `design/README.md` |
| a new `docs/` page | a link from wherever a reader would start |

`tests/test_docs_coverage.py` enforces the mechanical half: every
subcommand has a promise, no promise outlives its command, ADRs are
uniquely numbered and indexed, every doc is reachable. It says nothing
about whether the prose is any good, which is the half that matters
and the half only a person can supply.

The deeper principle is the one behind ADR-0018: **silence is the
enemy.** A key nothing reads, a command nothing documents, and a
dependency nothing declares all fail the same way — they look fine
until the day they don't, and then they look like someone's mistake
rather than a missing check.

## The tier protocol: rigor that doesn't block

The insight: *running* tests must not serialize development, but
*building on broken code* must be impossible. So testing is split into
tiers with different blocking semantics:

| Tier | What | Who runs it | Blocks? |
|---|---|---|---|
| 0 | Narrowest affected tests + syntax | the developing agent, inline | **Yes** — seconds, always |
| 1 | Component + scenario sweep (chosen generously) | `tester` subagent, background | Only if the next task depends on the changed code |
| 2 | Full suite incl. AI judgments | `tester` subagent(s), background | Feature-closing checkpoints only |

Back-pressure keeps this honest: at most two unresolved background
sweeps at a time (a third change waits for the oldest), and **any red
stops the line** — new feature work halts until the baseline is green
again, because a known-red baseline destroys the signal of every
subsequent sweep. Intermediate commits need Tier 0 green; a feature is
"done" only at Tier 2 green.

## Cheap tokens for routine work

Test execution is delegated to the `tester` subagent
(`.claude/agents/tester.md`), pinned to a cheaper model (Sonnet): it
runs the selection, triages failures (real / environmental / flaky,
with AI-judge rationales quoted verbatim), and reports in a fixed
~30-line format. Multiple testers run concurrently on disjoint
selections. Frontier-model attention is reserved for writing tests,
judging spec conformance, and diagnosing the failures a tester
triaged as real. Routine test *authoring* (parametrized clones,
fixture plumbing) may also go to a cheaper agent, with the primary
agent reviewing the diff.

Cost notes: AI-judged verdicts are cached by artifact hash
(`tests/.ai_cache/`), so repeat runs over unchanged artifacts are
free; `PROSAIC_AI_TESTS=0` gives a zero-token deterministic run.

## Selection heuristics

When in doubt, run more. The touched-path ➜ selection table lives in
`CLAUDE.md`; its spirit: Tier 0 is the narrowest thing that would
catch an obvious break; Tier 1 is everything that *could plausibly*
care, including the scenario suites, because scenario tests are where
cross-component regressions actually surface.
