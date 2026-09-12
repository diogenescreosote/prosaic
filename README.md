<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wordmark-dark.svg">
  <img src="assets/wordmark.svg" alt="prosaic." width="330">
</picture>

**AI-native litigation tooling for the small practice and the serious
self-represented litigant.**

[![ci](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml/badge.svg)](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml)

prosaic runs a civil matter out of a directory of files, with a language
model as the associate and a deterministic engine as the paralegal. Mail
and client-portal documents arrive on a schedule and are catalogued into
a knowledge vault as they land. Drafts are Markdown. The engine renders
them onto 28-line pleading paper, fills the Judicial Council forms,
letters the exhibits, proves the redactions, and assembles the filing
packet, byte-for-byte the same every time. Four independent review
passes read the packet the way the clerk, the judge, and opposing
counsel will before you sign it. Every event in the life of the case is a
typed git commit, so the record is auditable and reversible without an
audit log.

> **Today prosaic runs inside [Claude Code](https://claude.com/claude-code)**
> (and any agent CLI that reads the open skills convention: Codex, Gemini
> CLI). You open the matter directory, and the skills below are the
> commands. **An enterprise-grade user interface is under development.**
> The engine, the conventions and the matter format are what the UI will
> sit on; nothing you build in a matter today has to be redone for it.

> **Not legal advice.** prosaic is a drafting and document-assembly tool.
> Using it creates no attorney-client relationship. Every date and every
> document it produces must be reviewed by a human before it is relied on
> or filed. Its author is a law-office-study student, not an attorney.

## Not a toy

This is battle-tested drafting tooling. It runs live California civil
matters every day: contested family-law and civil litigation with
subpoenas, protective orders, records fights and a trial calendar. Packets
built by this engine have been accepted for filing by a superior court
clerk, served on opposing counsel, and executed through e-signature. Its
rules exist because a real filing was once wrong without them.

**Security and privilege were design constraints, not features.**

- **Local by default.** Matter content lives on your disk. No component
  transmits it anywhere except the AI harness you deliberately configure,
  under your terms with that provider. Audio never leaves the machine:
  transcription is local, always
  ([docs/security.md](docs/security.md), [docs/stt.md](docs/stt.md)).
- **Credentials in the OS keychain**, never in config or logs. Gmail is
  OAuth, read-only, one token per mailbox. Portal sessions live outside
  any synced folder.
- **Originals are sacred.** Received bytes are never modified. OCR,
  transcripts and summaries are siblings and sidecars, marked as machine
  output until a human verifies them.
- **Provenance is recorded, never inferred.** `pleadings/` holds only the
  court's copy, each declared `conformed`, `efiled`, `signed_order` or a
  named substitute in a manifest the build checks. Two byte-identical
  files prove only that they are the same file.
- **Unfiled means it says so.** A draft carries a red banner on every page
  of the packet, forms and exhibits included, until a human clears it.
- **Redaction is declared, built, proved.** A JSON schedule, a build, then
  a verifier that greps the output for every term on a written list before
  anyone sees it. Redacted content is removed, not covered.
- **The build refuses what a clerk or a judge would refuse.** A form
  attachment captioned as a standalone pleading, a case name set roman, a
  Bates cite that does not land on an attached page: hard errors, not
  warnings.
- **The code repository cannot leak the matter.** A pre-push guard rejects
  any commit carrying case material, and the matter format keeps the case
  out of the code tree by construction.

## What it does

**Intake.** Connectors pull Gmail threads and law-firm client portals
into the matter on a schedule; a headless triage pass OCRs what needs it,
files each document under the conventions, updates the evidence index and
folds what matters into the knowledge vault. A watched `inbox/` does the
same for anything you drop in by hand
([docs/connectors.md](docs/connectors.md),
[docs/triage.md](docs/triage.md)).

**Knowledge.** One Markdown note per person, organization, event, topic,
issue and filing, with front matter, sources and wikilinks; a nightly
refinement pass proposes corrections and questions and a morning standup
puts them to you, so the vault is human-verified rather than
model-asserted ([docs/knowledge.md](docs/knowledge.md)). Every draft
reads from it.

**Drafting.** Sources are Markdown with YAML front matter: caption,
parties, exhibits, cover forms, service. The model drafts prose; it never
lays out a page, letters an exhibit, numbers a heading or fills a form
field. Everything between the source and the PDF is deterministic code
([docs/writing-style.md](docs/writing-style.md),
[pleading/pleading_markdown_spec.md](pleading/pleading_markdown_spec.md)).

**Building.** An envelope is a filing packet: pleading PDF and DOCX,
exhibits with slip sheets, filled Judicial Council cover forms, consumer
and employee notices, proofs of service, in public and sealed variants
([docs/forms.md](docs/forms.md)). Thirteen forms are registered on the
overlay engine (CIV-110, EFS-020, EFS-050, FW-001, MC-025, MC-030,
MC-040, MC-050, SUBP-001, SUBP-002, SUBP-010, SUBP-015, SUBP-025);
family-law forms ship as a separate module.

**Review.** Four preflight passes, each optional and none a gate: a
citation check, a clerk's-window check, a skeptical bench officer, and
opposing counsel briefed from how your actual opponent has argued.
A second-opinion pass puts a different model's suggestions against the
sources and the record ([docs/review.md](docs/review.md)).

**Execution.** E-signature through DocuSeal with the signed original and
audit log brought back into the matter; remote online notarization
through Proof; cryptographic hashing, signing and timestamping of matter
documents against a paper-anchored key.

**The record.** Every event lands as a typed commit: `intake`, `triage`,
`draft`, `build`, `docket`, `discovery`, `record`, `config`. A hook
enforces the shape and pushes to a private backup remote. Undo is `git
checkout` ([docs/commits.md](docs/commits.md),
[docs/backup.md](docs/backup.md)).

## A working day

The standby supervisor pulled overnight: two threads from opposing
counsel, a filing acceptance from the e-filing vendor, a client-portal
invoice. Triage filed them, OCR'd the image-only pages, and the standup
agenda asks you three questions about what changed. You answer; the vault
updates and commits.

You open the matter in Claude Code and ask for a reply to counsel's
letter. The agent reads the relevant notes and the cited production,
drafts the letter with every Bates cite as a link into the attached
pages, and builds it. You read the PDF in Preview, mark it up in a
sentence, rebuild. `/preflight` reads it as the clerk, the judge and
opposing counsel. You clear the draft banner, sign, and the `docket`
commit records what went out and when.

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
[design/](design/); 876 tests, with `ruff` and `mypy --strict` clean.

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
