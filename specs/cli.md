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
  manifest-backed staleness, variant, signing, and sent-envelope
  semantics (see [pleading/generator.md](pleading/generator.md)). Every
  build is DRAFT-bannered unless `--final` is passed — suppression is a
  per-invocation act, never a property of the source. `sc build --all`
  builds every envelope not marked sent; `--check-stale` builds nothing
  and fails when any output in scope is missing or stale. `sc` is the
  only build interface — there is no Makefile (ADR-0038). *(tested:
  pleading/tests/test_draft_banner.py; --all, --check-stale and the
  sent-envelope guard in tests/scenarios/pleading_exhibits)*
- **`sc build-doc <source.md>`** builds exactly one envelope-owned
  Markdown source: its PDF and, when the envelope entry declares
  `docx: true`, its DOCX. The output location and available options come
  from `envelopes.yaml`; a source owned by zero or multiple envelopes is
  an error. Freshness is mode-aware: a draft output is stale for
  `--final`, and signer, date, or variant changes also rebuild
  (ADR-0038). *(tested:
  tests/scenarios/pleading_exhibits/test_single_document_build.py)*
- **`sc ocr <pdf> <outdir>`** OCR-supplements one PDF under the
  originals-are-sacred rules (adds text only to pages lacking it,
  never modifies the input, skips already-searchable files).
  *(untested)*
- **`sc form …`** exposes the JC form engine: list registered forms,
  fill one, dump its fields — and `sc form info <id>` prints enough
  (the descriptor's fields, checkboxes, and agent guide) for an
  agent that has never seen the form to fill it correctly without
  reading the registry source. *(untested)* `sc form preview <id> -o
  out.pdf` renders the blank with a translucent labeled box over every
  fillable and e-sign area (party-colored, type-labeled, with a
  legend) — the geometry sanity check that precedes trusting a new
  descriptor (ADR-0033). *(tested:
  pleading/tests/test_overlay_forms.test_geometry_preview_draws_clean,
  via the engine function the subcommand wraps)* `sc form check [ids…]`
  fills every registered descriptor twice (auto bindings only, then
  every field and checkbox populated), renders its geometry preview,
  and prints one row per form with its layer (built-in, `modules/<name>`,
  `local`), technology, page count and warning counts; any exception is
  a failure and the exit status is 1. `PROSAIC_LAYERS_ROOT=<checkout>`
  scans that checkout's `local/` and `modules/` instead of this one's,
  which is how a candidate engine is checked against a deployment's
  descriptors before a merge. *(tested: pleading/tests/test_form_check)*
- **`sc attest ...`** passes through to the attestation engine
  (`crypto/attest.py`): dual hashes, detached signatures, pinned-key
  verification, the signed manifest, timestamps. The real promises
  live in [attest.md](attest.md). *(tested: tests/test_attest.py)*
- **`sc flow ...`** passes through to the flow runner
  (`flows/run.py`): judgment work as a files-first graph with agent,
  command, judge, and gate steps. The real promises live in
  [flows.md](flows.md). *(tested: tests/test_flows.py)*
- **`sc sign ...`** passes through to the local signing engine
  (`signing/sign.py`): list the signature blanks a built document
  offers, list available signature marks, apply a mark and attest the
  resulting bytes, and re-verify a recorded signing event. Signing is a
  separate step from building, and the artifact it produces is what the
  attestation covers (ADR-0036). The real promises live in
  [signing.md](signing.md). *(tested: signing/tests/test_signing.py)*
- **`sc docuseal ...`** passes through to the e-signature client
  (`docuseal-client/client.py`): send for signature, poll, fetch the signed
  originals and audit log. The real promises live in
  [docuseal.md](docuseal.md). *(tested: tests/test_docuseal.py)*
- **`sc proof ...`** passes through to the remote-online-notarization
  client (`proof-client/client.py`). The real promises live in
  [proof.md](proof.md). *(tested: tests/test_proof.py)*
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
- **`sc brief [matter]`** prints a one-page orientation from matter.yaml,
  envelopes.yaml, the calendar headings of KNOWLEDGE.md, the top of
  TODO.md, recent `docket` commits, sync and inbox state, and the routine
  commands --- the SessionStart hook installed by the harness bundle runs
  it, so a session begins from the brief rather than the knowledge file
  (ADR-0039). *(tested: tests/test_harness_bundle)*
- **`sc open <envelope|path…> [--variant V] [--print-only]`** opens an
  envelope's built PDFs in the system viewer (newest variant plus the
  envelope root when variants exist) and prints the paths; a missing
  build is a clear error, not an empty viewer. *(tested)*
- **`sc find <term…> [-F] [--per-file N] [--ensure]`** greps every text
  file and sidecar in the matter (never out/, .state/, .git/) for each
  term and prints hits grouped by file. Every document the coverage
  audit calls not searchable is listed as UNSEARCHED with its reason,
  the coverage line is printed, a hit under `derived/text/` is shown as
  the original document and page, and the exit status is 2 whenever such a
  document exists (hits or not); 1 means searched everything and found
  nothing; 0 means hits and full coverage. `--ensure` runs
  `sc text ensure` first. A document that was not searched is reported,
  never silently skipped (ADR-0040). *(tested)*
- **`sc text audit|ensure|migrate [matter] [--json] [--include-inbox] [--dry-run] [--redo-ocr] [--jobs N] [--include-legacy-ocr]`**
  writes under `derived/text/` and `derived/ocr/` (ADR-0041), reads legacy
  siblings, and `migrate` moves the tool's own siblings into the tree;
  classifies every PDF, image, DOCX and audio file as searchable,
  unverified-sidecar, needs-sidecar, stale-sidecar, needs-ocr,
  transcript-needed, unsupported, unreadable or untriaged; `ensure`
  OCR-supplements and writes page-marked sidecars with a provenance
  header, never touching an original or a sidecar it did not write.
  Exit 1 while anything triaged is not searchable. Results are cached
  in `.state/text_coverage.json` by path, size and mtime. *(tested:
  tests/test_text_coverage)*
- **`sc harness install [matter]`** installs or refreshes the coding-agent
  harness bundle (`templates/matter/.claude`: the SessionStart hook and
  the build, build-doc, open, clean, status, commit and find commands),
  resolving the checkout placeholder to a real path; `sc init` does the
  same at scaffold time. A matter's own settings.local.json is never
  touched. *(tested)*
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
