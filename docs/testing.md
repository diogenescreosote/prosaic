# Testing

prosaic's harness has three layers, all run by pytest:

```bash
uv run pytest                       # everything (AI checks included if claude CLI present)
PROSAIC_AI_TESTS=0 uv run pytest    # deterministic only
uv run pytest -m ai                 # only the AI-judged checks
uv run pytest -q --no-cov <path>    # a narrow selection; --no-cov spares the 95% floor
```

## 1. Unit/component tests (`pleading/tests/`)

Fast, deterministic: fit math, caption parsing, descriptor↔blank
consistency for every registered form (the revision-drift alarm),
smoke fills, overflow plumbing.

## 2. Scenario tests (`tests/scenarios/<name>/`)

The heart of the harness. A scenario is an **entire fictional matter**
checked in as a fixture (`matter/` — sources, config, front matter) in
a fixed starting state. The test copies it to a temp dir, performs
real operations through the system (engine fills, envelope builds;
syncs and triage as those grow fixtures), and then makes **many
independent checks** on the results. Each scenario names the spec it
executes; when a spec promise gains a test, the spec's *(untested)*
marker comes off.

Current scenarios:
- `form_filling` — a motion matter; checks field placement, caption
  repetition, mandatory blanks, overflow → MC-025, checkbox linkage,
  cover-sheet assembly, registry-wide invariants; plus AI visual QA.
- `pleading_build` — a declaration matter; checks pleading-paper
  anatomy (28 line numbers, caption, perjury clause), typography
  conventions (em/en dashes, no spaced dashes), annotation leakage;
  plus an AI filing-readiness judgment.

## 3. AI-judged checks (`@pytest.mark.ai`)

For properties that are judgments rather than mechanics ("this
rendered form is court-ready"), tests call the judge in
`tests/harness/ai.py`: a headless Claude Code invocation that inspects
artifacts (rendered page images, extracted text) against a **rubric**
and **hard-failure conditions**, returning
`{score: 0–10, hard_failures, rationale}`. A check passes at
`score >= threshold` with no hard failure. Verdicts are cached by
artifact hash under `tests/.ai_cache/` (delete to re-judge); failures
print the judge's rationale so a disagreement is arguable, not
mystical. See design/adr/0008 for why this is in-house rather than an
eval framework.

Writing a good AI check:
- The **rubric** describes a 10/10 concretely and says what costs
  points. Vague rubrics produce vague scores.
- **Hard failures** are for properties that must never ship regardless
  of overall quality (a pre-filled signature line, clipped text).
  Deterministic checks should *also* cover them where mechanically
  possible — the judge is defense in depth, not the only defense.
- Judge **rendered images** for visual properties, extracted text for
  textual ones; pre-render PDFs with `scenario.rasterize`.

## 4. Repository checks (`tests/test_*.py`)

Suites that test the tree rather than the product. They exist because
each one covers a failure that is *silent* — nothing breaks, nothing
warns, and the gap looks identical to correctness from the inside.

- **`test_repo_hygiene.py`** — no absolute paths into a user's home
  directory, no credential shapes. A leak and a portability bug are
  the same defect here. `.githooks/pre-push` runs it at the moment a
  leak would stop being local.
- **`test_docs_coverage.py`** — every `sc` subcommand has a promise in
  `specs/cli.md`, no promise outlives its command, ADRs are uniquely
  numbered and indexed, every `docs/` page is linked from somewhere.
- **`test_system_dependencies.py`** — every program the code invokes
  by name is declared in `system-dependencies.yaml`, and every entry
  still has a call site. Checked in both directions.
- **`test_platform_seams.py`** — directory and credential policy stay
  behind their single owners (ADRs 0011, 0012).

Two of these walk `git ls-files`, so they run in a clone and not in
the container image, where `.git` is deliberately absent.

## Adding a scenario

1. Read the spec you're executing (or write it first — specs/README.md).
2. `tests/scenarios/<name>/matter/` — build the smallest fictional
   matter that makes the operations real. Fictional data only
   (Jane Roe / John Smith / 24CV00000); mark sources `notreal:`.
3. `test_<name>.py` — operations via `tests/harness/scenario.py`
   helpers, then independent checks: deterministic asserts first, AI
   judgments for the properties only judgment can see.
4. Reference the spec in the module docstring, and update the spec's
   *(tested)* markers.
