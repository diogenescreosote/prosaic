# prosaic: the technology

This page is for whoever sets prosaic up and keeps it running. What it
does for a practice, and why it is safe to use on a live matter, is on
the [front page](README.md).

## How it is built

**The filesystem is the backend.** A matter is an ordinary directory:
evidence in `assets/`, the court's copies in `pleadings/`, discovery in
`discovery/`, sources in `src/`, packets in `out/`, the vault in
`knowledge/`. Every file is one a person can open, a shell can grep, and an
agent can read without a connector or an export. Litigation lasts years
and tools rot; a case that is just files cannot be held hostage by either
([ADR-0001](design/adr/0001-plain-files-over-database.md),
[docs/matter-layout.md](docs/matter-layout.md)).

**Git is the version history and the undo.** Typed commits, enforced by
hook, pushed to a private backup. The whole matter, or one file, at any
point in its life, by tooling millions of people have already debugged.

**The model drafts prose; the engine renders it.** Same source, same
bytes out. A rendering defect is reproducible and fixable; a model that
formats prose is neither.

**Sharing costs the other person nothing.** A matter can live in a synced
Drive folder, so any subfolder can be shared with counsel, an expert or a
client, who install nothing and see the real documents in a viewer they
already have. The machinery stays local and is never shared.

**Spec-first, tested always.** Every component has a contract in
[specs/](specs/); every decision that constrains later work is an ADR in
[design/](design/); 907 tests, with `ruff` and `mypy --strict` clean.

## Security, in technical terms

- **Local by default.** No component transmits matter content anywhere
  except the AI harness selected by `cli/agent-run` (Claude Code, Codex,
  Gemini CLI), under the operator's terms with that provider. Audio is
  transcribed locally with whisper-cpp or WhisperX + pyannote and never
  uploaded ([docs/security.md](docs/security.md), [docs/stt.md](docs/stt.md)).
- **Credentials in the OS keychain**, read at runtime, never written to
  config or logs. Gmail is OAuth, read-only scope, one locally stored
  token per mailbox. Portal browser sessions persist on local disk
  outside any cloud-synced folder.
- **Originals are never modified.** OCR, transcripts and summaries are
  siblings and sidecars; machine output is banded as such until a human
  verifies it.
- **Provenance is declared, never inferred.** `pleadings/` holds only
  the court-filed version, each entry in `pleadings/MANIFEST.md` carrying
  a status (`conformed`, `efiled`, `signed_order`, or a named substitute),
  checked by `pleadings_manifest.py`.
- **Unfiled documents announce themselves.** A `notreal:` front-matter
  key renders a red banner on every page of the assembled packet, forms
  and exhibits included, in the DOCX header and atop the TXT
  ([ADR-0015](design/adr/0015-unfiled-documents-announce-themselves.md)).
- **Redaction is declared, built and proved.** `\redact{sealed}{public}
  {justification}` in the body yields public and sealed variants of the
  packet and an auto-generated redaction log; `verify_redactions.py`
  checks the public output against a written term list before it is
  handed over. Redacted content is removed from the file, not overlaid.
- **The build fails on what a clerk would reject.** A form attachment
  without `no_caption: true` ([ADR-0018](design/adr/0018-form-attachments-are-not-pleadings.md)),
  a case name set roman ([ADR-0047](design/adr/0047-case-names-are-italicized-or-the-build-fails.md)),
  a `\bates{}` cite that does not land on an attached page: hard errors.
- **The code repository cannot leak a matter.** `tests/test_leak_guard.py`
  runs on pre-push and rejects real-looking names, case numbers and
  addresses; matters live outside the tree by construction.

## Skills

Skills are the commands. In a matter, the harness bundle exposes them as
slash commands; in this repository they are the task-shaped instructions
an agent loads on demand ([skills/README.md](skills/README.md),
[docs/harness.md](docs/harness.md)).

**In a matter (`/command`)**

| Skill | What it does |
|---|---|
| `/status` | Where the matter stands: the brief, git status, stale output |
| `/find` | Exhaustive search of the record; reports what could not be searched |
| `/build`, `/build-doc` | Build a filing envelope, or one source, and relay the result verbatim |
| `/open` | Open the built PDFs in the system viewer |
| `/clean` | Report stale files in `out/` the configuration can no longer produce |
| `/citecheck` | Verify every citation: existence, form, and the proposition it is cited for |
| `/clerkreview` | Read the packet as the filing clerk: captions, boxes, signatures, service, page limits |
| `/judgereview` | Read the draft as the bench officer who will decide it, seeing only what the court sees |
| `/oppo` | Read the draft as opposing counsel preparing the opposition |
| `/preflight` | All four reviews, collated onto one page |
| `/secondopinion` | A different model's suggestions, weighed against the sources and the record |
| `/standup` | The daily knowledge standup: questions, proposals, corrections, committed as human-verified |
| `/commit` | A typed matter commit, staged by path |

**Repository skills**

| Skill | What it does |
|---|---|
| [new-matter](skills/new-matter/SKILL.md) | Scaffold a matter: layout, git, hooks, contracts, backup |
| [triage-inbox](skills/triage-inbox/SKILL.md) | Move new material from `inbox/` to `assets/` under the conventions |
| [build-envelope](skills/build-envelope/SKILL.md) | Build a filing packet from Markdown sources |
| [fill-form](skills/fill-form/SKILL.md) | Fill a Judicial Council form from its descriptor, with the verification discipline |
| [drafting-conventions](skills/drafting-conventions/SKILL.md) | Pagination and signature-block discipline: what the renderer enforces, what the drafter judges |
| [redact](skills/redact/SKILL.md) | Redact from a declared schedule, then prove the output |
| [prove-electronic-service](skills/prove-electronic-service/SKILL.md) | Paper an e-service with POS-050/EFS-050 |
| [docuseal](skills/docuseal/SKILL.md) | Send for e-signature; bring back the signed original and audit log |
| [proof](skills/proof/SKILL.md) | Remote online notarization: send, poll, fetch |
| [crypto-attest](skills/crypto-attest/SKILL.md) | Hash, sign, verify, manifest and timestamp matter documents |
| [phone-logs](skills/phone-logs/SKILL.md) | A citable call and message history with a number, from a phone backup |
| [run-flow](skills/run-flow/SKILL.md) | Files-first agent/judge/gate flows for drafting loops and review passes |
| [estate-plan](skills/estate-plan/SKILL.md) | Draft, execute and cryptographically bind a California estate plan |
| [migrate-knowledge](skills/migrate-knowledge/SKILL.md) | Fold a legacy single-file knowledge base into the vault |
| [deploy](skills/deploy/SKILL.md) | Assemble a deployment: engine, form module, local glue, verification |

## The `sc` command

`cli/sc` is the operations command line the skills call. Run
`sc <command> -h` for any of them; the contract for each is in
[specs/cli.md](specs/cli.md).

| Area | Commands |
|---|---|
| A matter | `init` scaffold · `upgrade` bring onto current conventions · `hooks` install the git hooks · `harness` install the agent bundle · `backup` init/push/status · `commit-check` validate a message · `brief` session-start summary · `open` built PDFs |
| Getting material in | `sync` run connectors and triage now · `connectors` list them · `schedule` install the standby supervisor · `mail-render` re-render a stored thread · `ocr` supplement a PDF · `text` audit or ensure every document is searchable · `find` grep the record |
| Knowledge | `knowledge` init, new, check, index, migrate · `refine` nightly proposals, never edits · `standup` the morning agenda |
| Building | `list` envelopes · `build` an envelope · `build-doc` one source · `clean` stale output · `form` list, info, fill, fields |
| Review | `review` preflight plumbing: paths, cites, report, status · `flow` run a files-first flow |
| Execution | `docuseal` send, status, fetch · `proof` send, status, fetch, poll · `sign` local signing slots, marks, apply, verify · `attest` hash, sign, verify, manifest, timestamp |
| The machine | `deps` which system dependencies are present · `paths` application directories |

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). The name
`prosaic` belongs to an unrelated PyPI project, so this installs from
source:

```sh
git clone https://github.com/diogenescreosote/prosaic.git
cd prosaic
uv sync
./cli/sc deps                              # which system tools are present
```

```sh
./cli/sc init ~/cases/smith-v-smith        # the directory, its git repo, its hooks
$EDITOR ~/cases/smith-v-smith/matter.yaml  # caption, connectors, backup
./cli/sc harness ~/cases/smith-v-smith     # the /commands for Claude Code
./cli/sc sync ~/cases/smith-v-smith        # pull sources, then triage what arrived
cd ~/cases/smith-v-smith && claude         # open the matter; ask for a draft
```

Full install notes, including the container, are in
[docs/install.md](docs/install.md); a working deployment with the form
module and local glue is described in [docs/deploy.md](docs/deploy.md).

## Status

0.1.0, in daily use on live matters. The engine and the registered forms
are tested against the statutes and the official blanks. What is not yet
here: the user interface (under development), jurisdictions other than
California, and a hosted service; the constraints a hosted deployment
would have to satisfy are written down in
[design/hosted-deployment-notes.md](design/hosted-deployment-notes.md)
so the local-first design does not foreclose it. Where it is going:
[ROADMAP.md](ROADMAP.md).

## Documentation

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the layers and
how they fit, or [docs/technical-overview.md](docs/technical-overview.md)
for the end-to-end tour.

| | |
|---|---|
| Running it | [install.md](docs/install.md) · [deploy.md](docs/deploy.md) · [matter-layout.md](docs/matter-layout.md) · [harness.md](docs/harness.md) · [knowledge.md](docs/knowledge.md) · [review.md](docs/review.md) · [upgrade.md](docs/upgrade.md) · [scheduling.md](docs/scheduling.md) · [backup.md](docs/backup.md) |
| Getting material in | [connectors.md](docs/connectors.md) · [triage.md](docs/triage.md) · [stt.md](docs/stt.md) |
| Getting documents out | [forms.md](docs/forms.md) |
| Writing for it | [conventions.md](docs/conventions.md) · [writing-style.md](docs/writing-style.md) · [commits.md](docs/commits.md) |
| Working on it | [skills/](skills/README.md) · [development.md](docs/development.md) · [testing.md](docs/testing.md) · [security.md](docs/security.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [AGENTS.md](AGENTS.md) |
| Estate planning | [templates/estate/](templates/estate/README.md) |
| Where it's going | [ROADMAP.md](ROADMAP.md) |

Decisions are recorded twice, by scope: [docs/DECISIONS.md](docs/DECISIONS.md)
holds the few that define what the engine is, and [design/](design/) holds
the numbered ADRs for choices inside it. Component contracts live in
[specs/](specs/): what each piece must accomplish, independent of how.

## License

MIT. The Judicial Council form PDFs in `pleading/forms/` are the official
published forms, included unmodified.
