<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wordmark-dark.svg">
  <img src="assets/wordmark.svg" alt="prosaic." width="330">
</picture>

**AI-native litigation tooling for the small practice and the serious
self-represented litigant.**

[![ci](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml/badge.svg)](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml)

prosaic runs a civil matter out of a folder of ordinary files, with an
AI model as the associate and a precise, predictable engine as the
paralegal. Mail and client-portal documents arrive on a schedule and are
catalogued into the case's knowledge as they land. You write in plain
text; the engine lays it out on 28-line pleading paper, fills the
Judicial Council forms, letters the exhibits, produces the public and
sealed versions, and assembles the filing packet, identically every
time. Four independent reviews read the packet the way the clerk, the
judge and opposing counsel will before you sign it. Everything that
happens to the case is recorded as it happens, so the record is
auditable and any change can be undone.

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

- **Your files stay on your computer.** Nothing is uploaded anywhere
  except to the AI service you choose to use, under your own terms with
  it. Recordings never leave the machine at all: transcription runs
  locally, always ([docs/security.md](docs/security.md)).
- **Passwords live in your computer's keychain**, never in a settings
  file. Email access is read-only, and you can revoke it for one account
  without touching the others.
- **Originals are never altered.** A document you received stays
  exactly as received. Searchable text, transcripts and summaries are
  kept beside it and marked as machine-made until a person has checked
  them.
- **The court's copy is the court's copy.** The filed version of every
  paper is kept apart from drafts and working copies, labeled with how
  it was obtained (conformed, e-filed, signed order), and never guessed
  at from a look-alike file.
- **A draft says it is a draft.** Until you clear it, every page of an
  unfiled document, forms and exhibits included, carries a red banner.
- **Sealing is no longer a painful, error-prone process.** Mark a
  passage `\redact{...}` and the public and sealed versions of the
  filing are produced together, automatically, with the redaction log.
  Before a public version reaches anyone, it is checked against your
  list of protected terms, and the protected text is removed from the
  file, not covered with a box that can be lifted off.
- **No more e-filing rejections.** Before you file, a review reads the
  packet the way the clerk's window will, against the rules of court and
  the local rules of the court in question: a missing date, an unchecked
  box, a signature or proof of service that is not there, a caption that
  does not match the case. prosaic catches these so the clerk does not
  have to. The purely mechanical mistakes, an attachment captioned as if
  it were a separate pleading, a case name not in italics, a Bates cite
  that leads nowhere, never get out at all: the document is not produced
  until they are fixed.
- **The software can never carry your case.** The program and your
  matters are kept entirely apart, and a guard on the program's own
  source rejects anything that looks like case material.

## What it does for a practice

**It keeps you from missing a deadline.** Every session opens with a
brief: what came in, what is due, what you owe a response to, which
letters from opposing counsel are still unanswered, and which reply you
wrote but never sent. Hearings and due dates are part of the case
record, so the brief knows that a subpoena you served has a production
date and that a demand you received has a response date. Calendar
integration is pending; today the brief itself is the reminder to serve,
respond and file.

**Clients can just hand you things.** A client drops documents into a
shared folder, or emails them to an address set up for their matter
(`inbox+24CV00000@example.com`). Either way, attachments are collected,
made searchable, sorted, filed, indexed and folded into what the case
knows about itself, on a schedule, with no one forwarding anything by
hand ([docs/connectors.md](docs/connectors.md),
[docs/triage.md](docs/triage.md)).

**It turns an hour-long call into evidence.** A recorded client
interview is transcribed on your own machine, with each speaker
identified, and becomes a source you can cite, marked "verify against
the recording" until you have. It will also draft a structured interview
guide from the questions the case file still cannot answer, so the next
call covers what the record lacks ([docs/stt.md](docs/stt.md)). This
matters most in abuse and trauma cases, where the person being
interviewed is hard to follow, the account is disorganized, and the
facts that decide the case are buried in an emotionally laden hour that
no one can take notes on fast enough.

**It runs your opposition for you.** Four reviews read a draft the way
the people who will decide it will read it: the clerk (captions, boxes,
signatures, service, page limits), the judge (assertions without
support, relief without authority, what will not be believed), opposing
counsel, briefed on how your actual opponent has argued in this matter,
and a citation check of every authority for whether it exists, is cited
correctly, and says what you say it says. A second opinion from a
different AI model is weighed against the sources and the record, and
you are told what to accept, what to reject, and what needs your
judgment ([docs/review.md](docs/review.md)).

**Everything known about the case is one place.** Emails, meeting
notes, pleadings, recordings, memos and productions are woven into a
single knowledge graph for the matter: one note per person,
organization, event, topic, issue and filing, each linked to the others
and to the documents it rests on. It uses the Obsidian note convention,
so the whole case opens in Obsidian with backlinks and a graph view, and
nothing about it is proprietary. Each night the system proposes
corrections and questions; each morning it puts them to you; your
answers are recorded as verified. Keeping the case knowledge current
becomes cheap, fast and consistent, and every draft is written from it
([docs/knowledge.md](docs/knowledge.md)).

**Privilege is handled.** Everything stays on your machine; recordings
never leave it; attorney-client correspondence is labeled as such;
nothing is forwarded anywhere on its own. Under development: choosing
which AI model may see which material, so that using AI does not itself
raise a waiver question.

**And underneath.** You write in plain text; the system lays out the
28-line pleading paper, letters the exhibits, numbers the headings and
fills the Judicial Council forms, the same way every time
([docs/writing-style.md](docs/writing-style.md)). A filing packet is the
pleading, its exhibits with slip sheets, the cover forms, consumer and
employee notices and proofs of service, in public and sealed versions
([docs/forms.md](docs/forms.md)). Thirteen forms are supported today
(CIV-110, EFS-020, EFS-050, FW-001, MC-025, MC-030, MC-040, MC-050,
SUBP-001, SUBP-002, SUBP-010, SUBP-015, SUBP-025), with family-law forms
as an add-on. Documents go out for e-signature through DocuSeal and come
back signed with their audit log, or to a remote online notary through
Proof, and can be fingerprinted and time-stamped so their integrity can
be proved later. Everything that happens to the case is recorded as it
happens, what arrived, what was drafted, what was filed, what was served,
and any of it can be put back the way it was
([docs/commits.md](docs/commits.md), [docs/backup.md](docs/backup.md)).

## A working day

Overnight, the system pulled two threads from opposing counsel, a
filing acceptance from the e-filing vendor, and a client's photos of a
text exchange sent to the matter's intake address. It filed them, made
the photographed pages searchable, and the morning agenda asks you three
questions about what changed. You answer; the case record updates. The
brief notes that counsel's letter of Tuesday is unanswered and that the
response to a records subpoena is due in nine days.

You open the matter in Claude Code and ask for a reply to counsel's
letter. It reads the relevant notes and the cited production, drafts the
letter with every Bates number as a link to the attached page, and lays
it out. You read the PDF, ask for changes in a sentence, and read it
again. `/preflight` reviews it as the clerk, the judge and opposing
counsel would. You clear the draft banner and sign, and the record shows
what went out and when.

---

*The rest of this page is for whoever sets it up and keeps it running.*

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
[design/](design/); 885 tests, with `ruff` and `mypy --strict` clean.

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
