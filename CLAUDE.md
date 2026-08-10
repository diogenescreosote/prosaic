# Agent Instructions — prosaic development

You are working ON prosaic (not in a matter directory). This file
is the development contract. Human-facing rationale lives in
docs/development.md; the rules are the same.

## Orientation: two subsystems, one repo

`prosaic/` is the typed library — statutory deadline computation, the
pydantic case model with per-fact provenance, the typed California
civil form pack, ingestion, and the LLM operator that reaches all of
it only through typed tools. Strict mypy, ruff, 95% coverage floor.
Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before changing its
shape.

`pleading/ cli/ connectors/ sync/ triage/ templates/` is the
operational tree — the Markdown-to-pleading-paper pipeline, the
descriptor-driven form filler, the `sc` CLI, the connectors and their
scheduled sync, and the matter conventions those produce. It runs
live matters. It is **excluded from ruff and mypy on purpose**: it is
ported from this project's private predecessor and keeps that style so
fixes made there still merge here as ordinary diffs. Match the
surrounding style; do not reformat it wholesale, and do not "fix" it
into the library's idiom.

The two overlap today — both fill MC-030, both render pleading paper,
each has its own CLI. That is known, deliberate for now, and the
subject of a pending decision (see [ROADMAP.md](ROADMAP.md), Phase 0).
When you add a form or a document type, add it to the subsystem whose
tests already cover the neighborhood, and do not quietly start a third
way of doing it.

## The prime directive: spec-first, test-always, don't wait around

Every feature addition or substantial modification follows this loop:

1. **Consult the specs.** Read every `specs/` file relevant to what
   you're touching (the component's spec, plus specs of components it
   talks to). If your change alters what must be true, edit the spec
   FIRST; if no spec covers it, write one (style: specs/README.md).
   Code that contradicts a spec without a spec change is a defect even
   if it "works."
2. **Check design/.** If your change crosses component boundaries,
   introduces a dependency, or bends an accepted ADR, write the new or
   superseding ADR before the code.
3. **Write comprehensive tests with the feature** — not after.
   Deterministic checks for every mechanical promise; an AI-judged
   check (tests/harness/ai.py) for every property only judgment can
   see; a scenario fixture (tests/scenarios/) when behavior spans
   components. New spec promises get `(tested: ...)` markers.
4. **Run tests per the tier protocol below** whenever code changes —
   erring on the side of more tests, but never letting a full run
   block the next unit of work that doesn't depend on this one.
5. **Land the documentation in the same change.** Not the next
   commit, not a cleanup pass. A capability that exists but is
   written down nowhere effectively does not exist for the person who
   needs it, and the gap is invisible: docs that are eight commands
   short read exactly like docs that are complete.

   What "documented" means depends on what you added:

   | You added | It must appear in |
   |---|---|
   | an `sc` subcommand | `specs/cli.md`, with a promise — help text is not the spec |
   | a front-matter key | `pleading/front_matter_keys.yaml` **and** the markdown spec |
   | a form-descriptor key | the descriptor schema in `pleading/pleading_markdown_spec.md` |
   | a deadline rule | `docs/DEADLINES.md`, with the citation and the test that pins it |
   | a form-pack module | `docs/FORM_PACKS.md`, and the module's own scope statement |
   | a system binary the code shells out to | `system-dependencies.yaml` |
   | a matter-facing convention | `templates/matter/CLAUDE.md` — that file is the contract agents actually read |
   | a decision that constrains later work | an ADR, listed in `design/README.md` |
   | a new `docs/` page | a link from somewhere a reader would start |

   `tests/test_docs_coverage.py` enforces the mechanical half of this
   (every subcommand has a promise, every ADR is indexed and numbered,
   every doc is reachable). It cannot check whether what you wrote is
   any good — that part is yours.

## The tier protocol

**Tier 0 — inline gate (blocking, seconds).** Before moving on from
any code change: syntax/import check plus the narrowest directly
affected tests (usually one test file or `-k` selection), run
yourself. Never proceed past a red Tier 0.

**Tier 1 — background sweep (nonblocking, minutes).** Immediately
after Tier 0 passes, fork the *relevant selection, chosen generously*
(the whole component's tests + its scenarios; see the selection table)
to a `tester` subagent running in the background, and continue
working. Do not wait unless the next task builds directly on the code
just changed — dependency blocks, independence proceeds.

**Tier 2 — full suite (nonblocking, checkpoint-gated).** Before a
feature is called done, before any commit that closes a feature, and
before ending a session: the full suite including `-m ai` must be
green. Fork it to a tester agent while you finish edges; the
*checkpoint* blocks on it, your hands don't.

**Back-pressure rules — the speed/rigor balance:**
- At most **2 unresolved background sweeps** at a time. A third change
  waits for the oldest sweep to land. (Prevents towers of unverified
  work while keeping the pipeline full.)
- **Any red result preempts new feature work.** Stop the line, fix or
  revert, re-sweep. A known-red baseline poisons every subsequent
  sweep's signal.
- Commits: intermediate commits need Tier 0 green + no known reds;
  feature-closing commits need Tier 2 green.

## Delegating to the tester agent (cheap tokens!)

Routine test execution goes to the `tester` subagent
(.claude/agents/tester.md — runs on a cheaper model). Spawn it in the
background with the pytest selection and the diff summary; it runs,
triages failures (real vs. environmental vs. flaky), and reports
compactly. Multiple testers may run concurrently on disjoint
selections. Use your own (expensive) cognition for: writing tests,
judging spec conformance, and diagnosing failures the tester triaged
as real-but-unclear. Routine test *authoring* (parametrized clones of
existing patterns, fixture plumbing) may also be delegated to a
cheaper agent, but you review the diff.

## Test selection table (err broader)

| Touched | Tier 0 (inline) | Tier 1 (background) |
|---|---|---|
| pleading/form_fill.py, jc_common.py, forms/registry/* | pleading/tests/test_forms.py | all pleading/tests + tests/scenarios/form_filling (+ `-m ai` if rendering changed) |
| pleading/md_pleading.py, md_to_docx.py, build_envelope.py | scenarios/pleading_build deterministic | both scenarios + pleading/tests |
| connectors/** | node --check on touched files | connector tests as they exist; scenario syncs when fixtures exist |
| sync/, cli/, triage/prompts | affected script smoke (`sc --help`, bash -n) | full deterministic suite |
| tests/harness/** | the harness's own unit tests + one scenario | full suite including `-m ai` |
| prosaic/deadlines/**, prosaic/model/** | the module's test file | tests/ (the property suite included) |
| prosaic/forms/**, prosaic/packs/** | tests/test_civil_forms.py + the form's own test | tests/ + the golden files |
| specs/, design/, docs/ | none (prose) | none — but check `(tested)` markers still true |

Commands: `PROSAIC_AI_TESTS=0 uv run pytest -q` (deterministic),
`uv run pytest -m ai -q` (judgments; needs claude CLI),
`uv run pytest` (everything, with coverage). AI verdicts cache by
artifact hash in tests/.ai_cache/ — reruns of unchanged artifacts are
free. Add `--no-cov` to any narrow selection: the 95% floor is scoped
to the whole `prosaic` package and a partial run will trip it.

## The other checks

`uv run ruff check .`, `uv run ruff format --check .`, and
`uv run mypy prosaic tests` all gate CI, and all three cover the
library and the tests written here while skipping the ported trees
(the exclusion lists live in `pyproject.toml`, with the reason). If a
lint failure appears in an excluded path, the exclusion is what is
wrong, not the file.

## Code style: no buried magic

Magic values — literal numbers, strings, paths, dimensions, format
templates — get pulled out of code into named constants (module top),
descriptor/config data, or template files, *when they represent a
decision someone might revisit*: page geometry, legal boilerplate
text, fit thresholds, naming patterns, service endpoints. A literal
that is the definition of itself (``range(1, 29)`` for 28 pleading
lines is borderline; ``"%s v. %s"`` for a caption is not) may stay
inline with a comment. The status quo ante was bespoke scripts full of
buried decisions; new code doesn't add to that, and refactors retire
it opportunistically. Functionality outranks generalization — extract
where it pays, don't abstract for sport. (ADR-0010.)

## Standing rules

- **No personal data, ever.** Fixtures and examples use Jane Roe /
  John Smith / Smith v. Roe / 24CV00000. Grep before you commit.
- **Originals are sacred** in processing code: inputs are never
  modified; outputs are new files.
- **Descriptor changes require empirical verification** — fill,
  rasterize, look (or make the AI judge look). Never trust JC field
  names (specs/pleading/forms/README.md).
- Match the style of the file you're editing; wrap prose ~72 cols.
- **Commit to `main` and push it.** No branching for now — the repo has
  one author and the overhead buys nothing yet. Every commit goes to
  `origin` as soon as it is made, so the published tree is never behind
  the local one and a lost laptop costs nothing.
- **Enable the pre-push hook once per clone:**
  `git config core.hooksPath .githooks`. It runs
  `tests/test_repo_hygiene.py` and `tests/test_leak_guard.py` at the
  moment a leak would stop being local, and it is the reason pushing
  freely is safe. Without it, pushing on every commit is pushing an
  unchecked public tree.
- This repo is public. A matter is not, and never becomes one: no case
  material in fixtures, docs, ADRs, or commit messages.
- **No family-law subject matter, anywhere.** This project's private
  predecessor was built around one real matter in that practice area;
  nothing from it comes here — not the form ids, not the statutes, not
  the vocabulary. `tests/test_leak_guard.py` enforces a denylist over
  every tracked file and every commit message, and a gitignored
  `.leakguard.local` adds personal names locally. Write examples in
  general civil terms.
- **Commit messages are plain and declarative** — what changed and
  why, in the imperative, wrapped at ~72 columns. No conventional-
  commit prefixes, no tooling or agent attribution trailers; the
  history reads as one author's account of the work.
