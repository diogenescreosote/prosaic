# Spec: the `sc` command surface

## Purpose

One entry point for everything prosaic does, discoverable from
`--help` alone: a user (or agent) who knows only that `sc` exists
should be able to scaffold a matter, pull evidence, build a filing,
and fill a form without reading the repo. `sc` is a thin dispatcher
over the components — it adds no behavior of its own, so each
subcommand's real promises live in that component's spec.

## Promises

- **`sc init <dir>`** scaffolds a matter to the layout in
  [matter.md](matter.md). It is rerunnable: existing files are left
  alone unless `--force`, so `init` on a live matter refreshes what
  is missing without clobbering what has been written. `--git`
  initializes the repository with the standard ignores. *(untested)*
- **`sc sync <dir>`** runs configured connectors plus AI triage
  *now*, bypassing the scheduler's interval guard — a manual sync
  means now (see [sync.md](sync.md)). *(untested)*
- **`sc build <envelope>` / `sc list`** build and enumerate filing
  envelopes from a matter directory, honoring the generator's
  staleness, variant, signing, and sent-envelope semantics (see
  [pleading/generator.md](pleading/generator.md)). *(untested)*
- **`sc ocr <pdf> <outdir>`** OCR-supplements one PDF under the
  originals-are-sacred rules (adds text only to pages lacking it,
  never modifies the input, skips already-searchable files).
  *(untested)*
- **`sc form …`** exposes the JC form engine: list registered forms,
  fill one, dump its fields — and `sc form info <id>` prints enough
  (the descriptor's fields, checkboxes, and agent guide) for an
  agent that has never seen the form to fill it correctly without
  reading the registry source. *(untested)*
- **`sc connectors`** lists available connectors with their
  descriptions and auth requirements. *(untested)*
- **`sc schedule <dir> [times]`** installs the 12-hourly background
  sync (macOS), defaulting to 08:00/20:00. *(untested)*
- **`sc clean [dir]`** reports files under `out/` that the current
  envelope config can no longer produce. It **only reports** unless
  `--apply`, and it says of each whether git is tracking it, because
  the expected-output set is computed from config and a bug there
  would otherwise destroy work that nothing can regenerate (see
  [pleading/generator.md](pleading/generator.md)). *(untested)*
- **`sc deps [--format check|apt|brew]`** reports which of the system
  binaries in `system-dependencies.yaml` are present, with the install
  command for the host, and exits non-zero if a required one is
  missing. `--format apt|brew` emits a package list instead — the
  Dockerfile installs from `--format apt`, so the image cannot drift
  from the manifest ([docs/install.md](../docs/install.md)).
  *(untested)*
- **`sc paths <kind>`** prints one application directory (`log-dir`,
  `data-dir`, `cache-dir`). This is the *only* implementation of
  directory policy in the repo: the shell helpers and the Node
  connectors call it rather than reimplementing it
  ([ADR 0011](../design/adr/0011-directory-policy-single-owner.md)).
  *(tested: tests/test_platform_seams.py)*
- **`sc backup init|push|status [dir]`** manages a matter's backup
  upstream — a local bare repository by default, or a private GitHub
  repository. The GitHub backend asks the API whether the repo is
  private before **every** push and refuses otherwise
  ([docs/backup.md](../docs/backup.md)). *(untested)*
- **`sc hooks <dir>`** installs the matter-side git hooks
  (`commit-msg`, `post-commit`) and points `core.hooksPath` at them.
  `sc init` does this for new matters. *(untested)*
- **`sc commit-check [file]`** validates a matter commit message
  against the docket-shaped convention in
  [docs/commits.md](../docs/commits.md), reading the message from a
  file or stdin. `--list-types` prints the types and what they mean.
  Unknown or missing types are errors; missing footers warn.
  *(untested)*

## The agent seam: `cli/agent-run`

Not an `sc` subcommand — a sibling script that is the ONLY place an
agent CLI is named (ADR-0020). Its promises:

- **`agent-run --check`** prints the provider it would use (`claude`,
  `codex`, `gemini`, or `custom`) and exits 0, or exits 1 when no
  agent CLI is available. Callers gate optional AI behavior on this
  probe and degrade gracefully. *(tested: tests/test_agent_run.py)*
- **`agent-run [--dir DIR]... [--yolo]`** reads a prompt on stdin,
  runs it through the selected provider noninteractively, and writes
  the agent's output to stdout. `--dir` grants read access to a
  directory outside the working directory on harnesses that sandbox
  reads; `--yolo` skips permission prompts and is only for callers
  whose risk is bounded per ADR-0005. An empty prompt is an error,
  not an empty run. *(tested: tests/test_agent_run.py)*
- **Selection order**: `PROSAIC_AGENT_CMD` (custom command, prompt on
  stdin, `AGENT_RUN_DIRS`/`AGENT_RUN_YOLO` exported), else
  `PROSAIC_AGENT_CLI` (forced provider; not on PATH is an error),
  else the first of claude, codex, gemini on PATH.
  *(tested: tests/test_agent_run.py)*

## Non-obvious constraints

- **Matter-scoped commands take the matter as an argument or the
  working directory** (`build`/`list` run from the matter, like
  make); the CLI must keep which-is-which obvious in each
  subcommand's help, because agents script against it.
- **`sc form` is a pass-through** to the form engine's own CLI; its
  surface grows with the engine, not with the dispatcher — `sc`
  stays thin on purpose, so component behavior is testable without
  the wrapper.
- **Help is the contract.** Every subcommand answers `-h` with its
  arguments and defaults; a capability that exists but is absent
  from help effectively does not exist for the audience this CLI
  serves. The same goes for this file: `tests/test_docs_coverage.py`
  fails when a subcommand exists without a promise here, because six
  of them were added in one sitting and none of them landed in the
  spec.
- **Destructive subcommands report before they act.** `sc clean`
  lists and exits; deleting needs `--apply`. A matter holds work that
  cannot be regenerated — timestamp tokens, hand-assembled packets —
  and the CLI cannot tell those from build droppings, so the human
  decides.
