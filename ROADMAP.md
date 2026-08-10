# Roadmap

prosaic today is a set of tools you drive from a terminal under
Claude Code, on a Mac. The goal of this roadmap is to make it
something a litigant or a paralegal can install and use — on macOS or
Linux — without giving up the property that makes it trustworthy:
**everything is plain files on your own machine, readable and
portable, with git as the history.**

Three commitments shape everything below.

**Local-first, and local-only for now.** The whole system runs on the
user's own computer. Privileged material does not leave it, except
where the user deliberately shares it with a collaborator. A hosted
option is a real future product, but it changes the security and
professional-responsibility posture enough that it is out of scope
here — see [design/hosted-deployment-notes.md](design/hosted-deployment-notes.md).

**Platform-independent by default.** Anything that works on POSIX
should be written for POSIX. Platform-specific code is confined to
where it is genuinely apropos — secret storage, OS scheduling — and
even there it sits behind an interface with more than one
implementation. New code is written this way from the start rather
than ported later.

**Developer tooling is a temporary prerequisite, not a permanent
one.** Requiring Docker or a package manager today is acceptable.
Requiring a compiler forever is not. The endpoint is an idiomatic
install on each platform.

---

## Phase 0 — where we are

Working today, driven from the CLI:

- Pleading generator (markdown → filed-quality PDF/DOCX), envelopes,
  exhibits, proofs of service
- Judicial Council form filling — descriptor-driven, six forms
  registered, MC-025 overflow, per-recipient companion notices
- Connectors for Gmail and MyCase, with scheduled catch-up-once sync
  and headless AI triage
- Matter conventions: `inbox/` → `assets/` with an authoritative
  INDEX, OCR-on-triage, local-only transcription
- The `prosaic` library: statutory deadline computation, a typed case
  model with per-fact provenance, the typed civil form pack, record
  ingestion, and the LLM operator that can reach them only through
  typed tools
- Test harness (pytest + LLM judge), `specs/`, ADRs

What's *duplicated* is the other half of Phase 0. The library and the
`pleading/` tree arrived from different directions and overlap: two
form-filling systems (typed pack modules under `prosaic/packs/civil/`
versus YAML descriptors under `pleading/forms/registry/`, both filling
MC-030), two pleading-paper generators, two CLIs (`prosaic` and `sc`).
Both are tested and both are used; neither has been retired. Unifying
them is real work with a real design question inside it — which of the
two form representations survives — and it wants an ADR before code.

What's missing is not capability. It's that using any of it requires
comfort with a terminal, on a Mac.

---

## Phase 1 — platform-independence discipline

**The near-term work continues on the macOS system that exists.** This
phase is not a porting sprint delivered before anything user-visible;
there is no Linux user waiting, and abstracting for its own sake buys
nothing today.

What it *is*: new code gets written POSIX-first, and two abstractions
land just before the phases that follow would otherwise author fresh
macOS-bound code. The expensive mistake is not failing to abstract
early — it is threading platform assumptions through a web app, a job
system, and an agent pane, then trying to unpick them.

**Posixify what already exists, now — but only to the seam.** Two
reasons it does not wait:

- **Existing code is the reference implementation.** Whatever
  `matter_sync.sh` and the connectors do is what the next thing
  written copies, by a person or an agent reading the repo to learn
  its conventions. A tree that states this commitment and then
  hardcodes `~/Library/Logs` teaches the hardcoding. It is the same
  reasoning as the hygiene sweep — mechanical beats intentional — and
  the sweep cannot forbid Apple-specific paths until there is a
  resolver to use instead.
- **The config schema has lock-in.** `keychain_service:` appears in
  every matter's `matter.yaml`. Neutralizing that key costs three
  files today and a migration path later. Accept the old name as a
  deprecated alias so nothing breaks mid-flight.

**Build the seams, not the second backends.** Untested backends are
worse than absent ones, and there is no Linux machine to test on:

- A **path resolver** replacing `~/Library/Logs` and friends
- A **secrets provider** with `keychain` and `env` backends — `env` is
  independently useful for headless and CI runs, so it earns its place
  today
- A **scheduler dispatcher**, with the launchd plist and the FDA shim
  moved behind a macOS backend rather than constituting the whole file

All three are testable on macOS: a resolver with a platform override
and an `env`-backed secrets path can be exercised now, so the seams
are verified rather than aspirational.

**Defer until a Linux user exists:** the systemd and Secret Service
backends themselves, the CI matrix, and the transcription-backend
split.

### What each abstraction means, when its turn comes

- **Secrets behind an interface**
  ([ADR 0012](design/adr/0012-credential-reference-not-store.md)).
  `matter.yaml` already names a
  keychain service per connector; the lookup should go through a
  provider rather than straight to macOS. Backends: macOS Keychain,
  Secret Service (`libsecret`/`secret-tool`, covering GNOME Keyring
  and KWallet), `pass`, an encrypted file (age/sops), and environment
  variables for headless use. Given the Python/Node split, the natural
  shape is a single `sc secret get <name>` the CLI already knows how
  to expose, so both runtimes call one implementation.
- **Scheduling behind an interface.** launchd on macOS, **systemd
  timers on Linux** — where `Persistent=true` gives catch-up-once
  semantics natively, more cleanly than the current arrangement — with
  plain cron as a fallback. The 11-hour guard inside `matter_sync.sh`
  already makes the catch-up behavior correct independent of the
  scheduler, so the backend is genuinely swappable. The Full Disk
  Access shim is a macOS TCC artifact with no Linux counterpart and
  stays behind the macOS backend.
- **Paths**
  ([ADR 0011](design/adr/0011-directory-policy-single-owner.md)).
  Replace `~/Library/Logs`, `~/Library/Application Support`
  and friends with a resolver that returns XDG locations on Linux
  (`$XDG_STATE_HOME`, `$XDG_CONFIG_HOME`) and Apple locations on
  macOS. No absolute paths in committed code.
- **Toolchain discovery instead of assumption.** No hardcoded
  Homebrew or user-specific interpreter paths; probe, and fail loudly
  with an actionable message when a dependency is missing.
- **Transcription backend behind an interface.** whisper.cpp builds on
  both platforms; `mlx-whisper` is Apple Silicon only;
  `faster-whisper` covers CUDA. Pick per host, same interface.
- **A CI matrix that actually runs both**, so drift is caught by the
  suite rather than by a Linux user.
- **A hygiene sweep in the suite** (`tests/test_repo_hygiene.py`,
  done) — no absolute paths into a user's home directory, no
  machine-specific strings, no credential shapes, enforced over
  `git ls-files`. Hardcoded home paths are simultaneously a privacy
  leak and a portability bug, so one check covers both. A matching
  `.githooks/pre-push` runs it at the moment a leak would stop being
  local; enable per clone with
  `git config core.hooksPath .githooks`.

**Windows is explicitly out of scope.** It isn't POSIX, and
maintaining a native port would add complexity out of proportion to
the benefit. The likely long-term answer for Windows users is the web
client against a hosted deployment — which is another reason to keep
the server/UI boundary honest even when both ends are local.

## Phase 2 — make builds fast

**Goal: a build fast enough to be interactive.** Today the
markdown → PDF/DOCX pipeline is often slow, and nobody knows why. That
is tolerable from a terminal where you expect to wait; it is not
tolerable behind a button in the web UI, where a thirty-second build
reads as a hang. Fixing it before Phase 3 also means the reader is
built against a pipeline whose costs are understood.

**Measure before changing anything.** The pipeline has at least five
distinct stages — interpreter startup, markdown parse, PDF drawing,
exhibit merge, DOCX generation, plus form filling on envelopes that
use it — and the intuition that "Python is slow" is not evidence about
which of them dominates. The first deliverable is a per-stage,
per-document timing breakdown, not a patch.

### Measured, 2026-08-09

Per document — one declaration, 60 exhibit pages, wall clock, no
profiler:

| Phase | Time | Share of render |
|---|---|---|
| interpreter import | 158 ms | — |
| `merge_outputs` (pypdf) | 315 ms | 62% |
| ↳ `scale_and_center_page` | 138 ms | 27% |
| reportlab layout + draw | 190 ms | 38% |
| **render total** | **504 ms** | |

Envelope of 13 renders: **3.34 s sequential**.

### Done: parallel renders

`build_envelope.py` shelled out once per document per format and
waited for each. Planning (staleness checks, log lines) is cheap and
order-dependent; rendering is expensive and embarrassingly parallel —
each job reads shared inputs read-only and writes one output nobody
else touches. Splitting those two phases and running the second on a
thread pool took the envelope from **3.34 s to 0.99 s (3.4×, 506%
CPU)**, with byte-identical output verified against the sequential
build. `-j N` / `PROSAIC_BUILD_JOBS` controls it; `-j1` serializes
for bisecting a failure.

Child output is captured and printed per job rather than interleaved,
which is more readable than the sequential version was.

### Deferred: pikepdf on the merge path

Measured rather than assumed. Read + scale-and-center + write, 51-page
exhibit, identical transform math:

| | Total | Per page |
|---|---|---|
| pypdf | 94 ms | 1.8 ms |
| pikepdf (qpdf, C++) | 33 ms | 0.6 ms |

**2.8× on the hot path.** Projected across `merge_outputs`: 315 → ~112
ms, render 504 → ~300 ms, per-document total 662 → ~460 ms — about
**1.7× per document**, and roughly 0.99 s → 0.7 s on the envelope,
since a parallel build is bounded by its slowest single document
either way.

Deferred because the ratio of risk to remaining benefit is wrong right
now. Parallelization already captured the large win; `merge_outputs`
also carries exhibit tab sheets, link annotations, and the
annotation-transform logic that keeps redaction labels aligned, so
converting it means reimplementing annotation transforms against
pikepdf. A subtly misplaced redaction label is a far worse outcome
than a slow build.

Worth doing when it comes up again, because 1.7× lands squarely on the
interactive single-document rebuild — the loop a web UI button puts
you in. Scope it as: convert `append_pdf_scaled` /
`scale_and_center_page` and the PDF read/write; leave tab sheets and
link annotations on the existing path if entangled; gate on
rasterizing every page of a real envelope before and after and
comparing images, not page counts.

### Untested

- **Repeated work across builds.** Exhibits are re-merged and fonts
  re-registered every run even when unchanged. Content-hash caching of
  merged exhibit blocks may be the cheapest remaining win.
- **Interpreter import, 158 ms/document.** Parallelism hides it in
  envelope builds but not in single-document rebuilds. A warm worker
  would recover it.
- **`redact_pdf.py` still runs sequentially**, one subprocess per
  entry — the same `RenderJob` treatment applies directly.

**"Rewrite it in a lower-level language" has not earned its place.**
The hot paths are reportlab and pypdf, and the fast replacements are
already native underneath; the ceiling is which library does the work
and how often the process starts, not the interpreter. A rewrite would
mean reimplementing the pleading layout engine, where all the domain
knowledge and all the tests live.

**Guardrail:** a build benchmark in the suite, so a fix that lands
does not silently regress.

## Phase 3 — the local reader

**Goal: replace "open Finder and run `make`" for everything that only
reads.** The vertical slice that proves the architecture.

- A local HTTP server bound to `127.0.0.1`, serving a browser UI
- Matter overview: chronology, parties, posture, open items — rendered
  from `KNOWLEDGE.md`, `TODO.md`, and `matter.yaml`
- Document browser with inline PDF viewing, backed by `assets/INDEX.md`
- Full-text search over the OCR text sidecars via ripgrep, **streamed
  to the browser as results arrive**, so first hits render in
  milliseconds regardless of corpus size
- File watching → Server-Sent Events, so the page updates when
  anything on disk changes (debounced; cloud-sync daemons generate a
  lot of spurious events)
- Read-only. No mutations in this phase.

**Why this first among the user-facing phases:** largest usability
gain per unit of risk, and it forces the read path — parsing, caching,
invalidation — to be correct before anything writes.

## Phase 4 — jobs and actions

**Goal: run the slow things from the UI without a job queue server.**

- **Jobs are directories.** `.state/jobs/<id>/` holds `status.json`
  (state, pid, started, finished, exit code, description) and a `log`
  the process appends to. Start detached, return the ID immediately,
  tail the log over SSE. On server start, any job marked running whose
  PID is dead becomes failed. This replaces Celery and Redis entirely,
  and it is portable by construction.
- Trigger sync, envelope builds, and form fills from the UI
- Progress and failure as first-class UI state, not log archaeology
- Git commit per mutation, taken while the operation still holds its
  lock — undo becomes `git revert`, and history is the audit trail

## Phase 5 — the agent pane

**Goal: ask questions and draft in place, with the agent operating on
verified operations rather than improvised shell.**

- An **MCP server exposing prosaic's operations as typed tools** —
  `build_envelope`, `fill_form`, `triage_file`, `search_matter`,
  `run_sync`. This is the important piece: the agent calls checked
  operations with typed arguments instead of guessing at the Makefile,
  and permission hooks can gate the destructive ones.
- An interactive session built on the **Claude Agent SDK**
  (`@anthropic-ai/claude-agent-sdk`), which supplies the agent loop,
  context management, built-in file tools, hooks, permissions, and
  session continuity, while running entirely on the user's machine.
- Existing headless triage (`claude -p`) stays as-is — it is batch
  work and slots into the Phase 4 job model unchanged.

## Phase 6 — inbox and collaborator sharing

**Goal: the user never drags a file anywhere, and a collaborator who
has never heard of prosaic can still contribute documents.**

### The user's own inbox

A **review step**, not a magic folder: "14 new documents since
yesterday — which belong to this matter?" One click per document, then
normal triage runs. Sources are browser drag-and-drop, a dedicated
watched folder (`~/prosaic-inbox/`, never `~/Downloads` itself),
and the existing connectors. Review is not overhead — the triage
conventions already want a human deciding what is evidence before
anything lands in `assets/`.

### The matter in Google Drive

Two requirements, and they pull in different directions:

- **The tree must be browsable in Drive.** Not just a shared drop
  folder — the documents themselves, visible in the Drive web UI, on
  mobile, and in Gmail's "attach from Drive" picker, so a user can mail
  an exhibit to opposing counsel without going near a filesystem.
  Subfolders can be shared with collaborators independently.
- **The tools need a fast, real, local POSIX filesystem.** ripgrep,
  git, ocrmypdf and the agent all do many small reads and writes.

The naive way to satisfy the first is to put the working tree inside a
synced Drive folder — which is how it works today on macOS, on one
machine. That does not generalize:

1. **Google Drive for Desktop has no Linux client**, and never has.
   Any design that requires the tree to live in a Drive-synced folder
   is macOS-only by construction.
2. **`rclone bisync` is still documented as beta**, described as an
   advanced command where "data loss can result." That is not a thing
   to put underneath privileged client files.
3. **`.git` inside a cloud-synced folder is a corruption hazard** once
   a second machine is involved — partial index writes and packfile
   races.
4. **On macOS, streamed file content is an evictable cache.** Drive
   uses Apple's File Provider API; a full-tree grep is local until one
   day it isn't, and the failure mode is a search that silently takes
   minutes. (Mirror mode avoids this; streaming mode does not.)

**The resolution: one-way sync in each direction, over disjoint
paths.** Bidirectional sync is only dangerous when both ends can
modify the same file. Split by direction and that never happens:

- `inbox/` — collaborators write, we consume and move files out.
  **Pull only**, and *additive* (`rclone copy`, never `sync`): the
  local inbox is deliberately drained by triage, so mirroring would
  fight it.
- Everything humans need to see (`assets/`, `pleadings/`,
  `discovery/`, built output). We write, they read. **Push only**, and
  here mirroring (`rclone sync`) is correct — a local rename should
  show up in Drive.
- Machinery — `.git`, `.state/`, caches, build intermediates — is
  **excluded from both** and never leaves the local disk.

No reconciliation, no conflict resolution, no beta code path. It works
identically on macOS and Linux, needs no Drive desktop client on
either — the browse surface is Drive itself, which is the point — and
it eliminates the `.git` hazard by construction rather than managing
it.

**Clearing the Drive inbox: move, never delete.** Processed items get
reparented into `inbox/_processed/` rather than removed. A plain
delete opens a real race — a collaborator re-uploads a corrected
`scan.pdf` between the pull and the delete, and the correction is
destroyed unseen. In a legal matter that is a silently lost exhibit,
and re-uploading a bad scan is precisely what people do. Moving also
gives the collaborator feedback that their file was received. Leave
Drive's trash enabled regardless, so even a mistake is recoverable.

**Idempotency comes from the manifest, not from the move.** What
prevents reprocessing is the record of Drive file IDs already pulled —
which is the existing connector contract (`.state/<connector>.json`),
not new machinery. The archive move is then pure housekeeping: a
failed move causes untidiness rather than a duplicate or a loss.

**Remove immediately, guarded by a revision check.** The lossy case is
narrow: a *new revision of the same Drive object* landing between the
pull and the removal. A new upload is a new object and gets pulled
normally; a retention window does not help either way, since the
manifest already marks the ID processed and nothing looks again. So
record `headRevisionId` at pull time and verify it is unchanged before
removing — if it moved, re-pull instead of archiving. With that check,
clearing on completion is safe and nothing accumulates. Drive's trash
supplies 30 days of recovery without a sweep job.

**The remaining question is collaborator confirmation, not storage.**
A non-technical person who drops a file in and watches it vanish reads
that as failure. Options, cheapest first: keep `inbox/_processed/` but
sweep in hours rather than weeks; surface receipts in the web UI and
delete immediately; or leave a Drive shortcut in place of the archived
file once the push lands — confirmation that persists at no storage
cost. Decide this on the collaborator experience; the duplication
argument does not settle it.

The local tree stays the source of truth; Drive holds a published view
of it. A collaborator's experience is exactly what was asked for: an
ordinary Drive folder they drop a PDF into, and shared folders they can
browse and attach from.

**What this gives up:** editing a document in Drive will not round-trip
back into the matter. Drive is a publication and intake surface, not a
second writable copy. That is a deliberate trade — it is what keeps a
single writer, and therefore what keeps the concurrency work deferred.
If in-place editing in Drive ever becomes a requirement, it brings the
whole locking design back with it.

Two details the implementation has to get right: **partial transfers**
(wait for size and mtime to be stable before ingesting from `inbox/`)
and **name collisions** (Drive permits duplicate filenames in a folder,
so two collaborators can both upload `scan.pdf`; disambiguate on
ingest rather than assuming uniqueness).

macOS users who prefer the native client can still run Drive for
Desktop over the published folder — in **mirror** mode, not streaming,
so nothing is evictable. That is a preference, not a dependency.

## Phase 7 — single-writer document owners

**Goal: make concurrent work safe without merge UX, and without
littering the tree with metadata files.**

`assets/INDEX.md`, `KNOWLEDGE.md`, and `TODO.md` are the contended
files — every asset change touches the first, and the conventions
require it. Rather than locking them or decomposing them into
per-asset sidecars (which would double the file count and make the
tree worse to browse), **give each one a dedicated owner process.**
Everyone else sends it requests; it applies them in order.

Single writer per file means no lock contention, the file stays a
single human-readable document, and the owner becomes the natural home
for the conventions that already exist — renumber TODO items, integrate
into the right KNOWLEDGE section rather than appending a log, keep
INDEX rows sorted and never drifting from disk.

## Phase 8 — idiomatic packaging

**Goal: install the way software installs on your platform.** Until
this lands, Docker and a package manager are acceptable prerequisites.

- **Linux:** a `curl … | sh` installer first, then real packages
  (`.deb`/`.rpm`, or Homebrew-on-Linux) once the layout is stable.
- **macOS:** a signed and notarized app bundle with embedded runtimes.
  This is where the "no compiler required" commitment actually gets
  discharged — see below.
- **Docker** stays the answer for CI, the development environment, and
  any future hosted deployment. It is a reasonable stopgap for local
  use today, with one caveat worth knowing early: a Linux container on
  macOS runs in a VM and **cannot reach Metal**, so GPU-accelerated
  transcription has to run on the host regardless.
  **Done** ([ADR 0013](design/adr/0013-system-dependencies-declared-once.md)):
  `system-dependencies.yaml` declares every system binary, `sc deps`
  reports and emits package lists, and the `Dockerfile` installs from
  that manifest rather than a transcribed copy. Building it found two
  dependencies nothing declared — Debian packages `npm` apart from
  `nodejs`, and reading the AES-encrypted JC forms needs
  `pypdf[crypto]`, which had been arriving transitively via ocrmypdf's
  pdfminer. An envelope built in the container is byte-identical to
  the same envelope built on macOS.
- First-run model download with checksum verification; the ~1.5 GB
  speech model is never shipped in a package.

### Notes toward the macOS bundle

- **`mlx-whisper` may remove the whisper.cpp build problem entirely**
  on Apple Silicon: prebuilt wheels, GPU via Apple's MLX framework, no
  CMake and no Homebrew. Vendor the wheels against an embedded
  relocatable Python. Fall back to a prebuilt CPU binary on Intel.
- **WhisperX/pyannote diarization does not survive the no-dev-tools
  constraint** — a large ML stack, a HuggingFace account, and
  click-through model licenses. Multi-speaker diarization stays a
  documented power-user path, not a bundled feature.
- **`ocrmypdf` needs tesseract, ghostscript, qpdf, and unpaper** —
  four native dependencies to vendor and sign on macOS. Fine on Linux,
  where they are all packaged.

### Possible future direction: macOS Vision for OCR

macOS ships on-device text recognition in the Vision framework, with
no external dependencies, and it is competitive with or better than
tesseract on scanned documents. A small native helper could replace
the entire OCR toolchain on Mac.

Recording it as a direction, not a plan. It is platform-specific in a
way that cuts against the current posture, it would mean two OCR
implementations to keep behaviorally consistent, and it needs a
quality comparison on real scanned filings before it earns that cost —
OCR output feeds both search and citation.

---

## Explicitly deferred

- **Windows native support.** Likely never; web client against a
  hosted deployment instead.
- **Multi-user and concurrency beyond Phase 7.** The design sketch —
  coarse tree-level locks, per-envelope granularity, append-only
  inbox, leases with heartbeats, reads that never queue — is sound but
  premature. Revisit when two people actually need the same matter at
  once.
- **Hosted deployment.** See
  [design/hosted-deployment-notes.md](design/hosted-deployment-notes.md).
- **Search relevance ranking.** ripgrep over text sidecars is fast
  enough for realistic matter sizes; tens of thousands of documents is
  roughly a gigabyte of text, which greps in well under a second warm.
  The trigger for adding a derived SQLite FTS index is wanting
  **ranking and stemming** — "testified" matching "testimony" — not
  raw speed. When it comes, it is a cache rebuilt from the files,
  never a place where a fact lives.

## Decisions that will need ADRs

Recorded here so they aren't made by accident. Per
[design/README.md](design/README.md), the ADR gets written when the
decision is made, not after the code works.

- Scheduler abstraction (supersedes or amends
  [ADR 0004](design/adr/0004-launchd-with-fda-shim.md), which is
  macOS-specific by construction).
  [ADR 0011](design/adr/0011-directory-policy-single-owner.md) put the
  platform dispatch in `install_schedule.sh` but left the decision
  itself unrecorded.
- Drive as a published view maintained by one-way sync in each
  direction, rather than as the storage substrate
- Job-directory protocol as the single async mechanism
- MCP as the agent's interface to prosaic operations

## Known debt carried into this work

- **`sc clean` classifies by config, not by value.** It reports what
  the current envelope config cannot produce, which is not the same
  question as what is safe to delete. Its first run on a real matter
  flagged an RFC 3161 `.tsr` timestamp token — evidentiary, and
  impossible to regenerate once the moment it certifies has passed.
  That one is now expected output, but the general shape of the
  mistake remains: hand-assembled packets, zips and one-off artifacts
  live in `out/` and nothing regenerates them. Deleting stays opt-in,
  and tracked-vs-untracked is reported, for exactly this reason.
- Exhibit path resolution differs between the PDF and TXT renderers
  (logged in `design/refactor-audit/`)
- `sync/matter_sync.sh` has no automated test — the highest-value
  untested surface in the repo
- Platform-bound surfaces inventoried in Phase 1 above; the scheduler,
  the FDA shim, and log/state paths are the largest
