<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wordmark-dark.svg">
  <img src="assets/wordmark.svg" alt="prosaic." width="330">
</picture>

**Matter-of-fact tooling for self-represented civil litigants.**

[![ci](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml/badge.svg)](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml)

prosaic runs a civil case out of a directory of files. It pulls records in
from mail and client portals, catalogues them as they arrive, computes
filing deadlines from the statutes, and assembles filing-ready packets:
28-line pleading paper, exhibits, and the official Judicial Council forms.
An LLM operator drives it; the engine does everything that has to be right.
It is built by a law-office-study student for use on one's own case, not as
a practice tool for lawyers and not as a substitute for one.

> **This is a document-assembly utility, not legal advice.** Using it creates
> no attorney-client relationship. Every date it computes and every document
> it renders must be reviewed by you before you rely on it or file it. The
> author is a law-office-study-program student, not an attorney. If you can
> get a lawyer, get a lawyer.

## The filesystem is the backend

There is no database. A matter (one case) is an ordinary directory:
evidence in `assets/`, work product in `pleadings/` and `discovery/`,
drafting sources in `src/`, knowledge notes in Markdown beside them.
Metadata is Markdown and YAML. Every file is one a person can open, a
shell tool can grep, and an AI agent can read without a connector or an
export step. Litigation lasts years and tools rot; a case file that is
just files cannot be held hostage by either.
([ADR-0001](design/adr/0001-plain-files-over-database.md).)

Three things follow from that, and they are the reasons for it.

**Git is the version history, and the undo.** A matter is a git
repository, and everything that happens to it lands as a commit: material
arriving from a connector, a triage pass moving a document into evidence,
a draft revision, a rebuilt packet, an order coming back from the court.
Commits are typed by what actually happened: `intake`, `triage`, `draft`,
`docket`, `discovery`. A `commit-msg` hook enforces the shape, and a
`post-commit` hook pushes to a backup remote so the record is never in one
place only ([docs/commits.md](docs/commits.md),
[docs/backup.md](docs/backup.md)).

Because the whole case is files under version control, "put it back the
way it was" is `git checkout`: the entire matter, or one file, at any
point in its life. An agent that reorganizes something it shouldn't have,
a build that went wrong, an exhibit deleted three days ago: all
recoverable, by tools that millions of people have already debugged rather
than by anything invented here. The same property makes the case
auditable without an audit log: what changed, when, and why is the history
itself, in a format anyone can read.

**Local by default; the cloud is a deployment choice, not a dependency.**
Everything runs on your own machine and privileged material never leaves
it. But nothing in the design assumes a laptop. The requirements are a
POSIX filesystem and git, so the same tree runs on a Linux box, in the
container this repo ships, or on a server you control, with no change to
how anything works. What is deliberately *not* shipped is a hosted
service, and the reason is confidentiality rather than engineering: the
constraints such a thing would have to satisfy are written down in
[design/hosted-deployment-notes.md](design/hosted-deployment-notes.md)
so the local-first design does not foreclose it by accident.

**Sharing costs the other person nothing.** Because a matter is only
files, the tree can live in a synced Google Drive folder, which is how it
runs today. The documents are then browsable in the Drive web UI, on a
phone, and in Gmail's "attach from Drive" picker, and any folder or
subfolder can be shared with counsel, an expert, a client, or a
co-litigant. They install nothing, sign up for nothing, and export
nothing: they are looking at the real documents, in a viewer they already
have. The machinery (`.git`, connector state, caches, build intermediates)
stays local and is never part of what you share. Today that means a Drive
desktop client, which exists only for macOS; replacing it with one-way sync
over disjoint paths would need no client at all and work the same on Linux.
That design is written up in [ROADMAP.md](ROADMAP.md).

## The one design rule

**The model classifies, extracts, and drafts prose. The engine computes,
validates, and renders. No date is ever produced by a language model.** This
is structural, not aspirational: the operator's only way to obtain a date is
a typed `compute_deadline` tool that accepts facts and returns the
deterministic engine's result, citation attached. If the model tried to
guess a deadline, there is no code path that would let the guess become one.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). The name
`prosaic` belongs to an unrelated PyPI project, so this installs from
source:

```sh
git clone https://github.com/diogenescreosote/prosaic.git
cd prosaic
uv sync
```

## Quickstart

```sh
# Last day to file a motion for an October 2, 2026 hearing, served electronically
uv run prosaic deadline motion_filing 2026-10-02 --method electronic
# 2026-09-04  CCP §§ 1005(b), 12c; CRC 3.1300(a)

# The six forms the California civil pack fills
uv run prosaic forms

# Statewide court holidays for a covered year (2025-2028 packaged)
uv run prosaic holidays 2026

# Run the test suite
uv run pytest
```

Scaffold a matter and build a filing packet from Markdown sources:

```sh
./cli/sc init ~/cases/smith-v-smith        # the directory, its git repo, its hooks
$EDITOR ~/cases/smith-v-smith/matter.yaml  # case caption, connectors, backup
./cli/sc sync ~/cases/smith-v-smith        # pull sources, then triage what arrived
cd ~/cases/smith-v-smith && make list      # the envelopes this matter defines
make responsive_declaration VARIANT=public
```

With `ANTHROPIC_API_KEY` set, `uv run prosaic ask matter.json "..."` runs
the LLM operator against a serialized matter.

## What is implemented today

- **The matter directory.** The plain-files convention above, with the
  conventions that keep it honest: originals are never modified, every
  document lands in an index, derived files sit beside their sources
  ([docs/matter-layout.md](docs/matter-layout.md),
  [docs/conventions.md](docs/conventions.md)).
- **Connectors and scheduled sync.** Gmail and law-firm client portals
  pulled into the matter on a schedule, then catalogued by a headless
  triage pass that files each new document and folds what matters into the
  case's knowledge notes: [docs/connectors.md](docs/connectors.md),
  [docs/scheduling.md](docs/scheduling.md), [docs/triage.md](docs/triage.md).
- **Envelope builds.** Markdown sources with YAML front matter rendered to
  28-line pleading PDFs and DOCX, assembled with their exhibits and cover
  forms into the filing packets named in `envelopes.yaml`, in public and
  sealed variants, with redaction and exhibit slip sheets:
  [docs/forms.md](docs/forms.md).
- **Judicial Council form filling.** Each form is a YAML descriptor
  recording where every field lives and how it breaks; one engine executes
  all of them, and overflow spills to an MC-025 attachment rather than
  truncating a filing.
- **Deadline engine.** CCP §§ 12–12c day arithmetic, the CCP § 1005(b)
  motion-notice schedule, § 430.40(a) demurrers, the § 1013 / § 1010.6
  service extensions, CRC 3.110(b) and 3.725(a). Court days and calendar
  days are distinct types; holiday calendars are data (2025–2028 packaged,
  cross-checked against published court schedules); each rule is covered in
  [docs/DEADLINES.md](docs/DEADLINES.md) with the test that pins it, plus a
  property-based suite (Hypothesis) asserting the invariants examples can't.
- **California civil form pack.** CM-010, CM-110, SUM-100, POS-010,
  MC-030, MC-031, filled into the official Judicial Council AcroForms and
  verified by golden-file tests that read the values back out of the
  produced PDFs. Scope is stated per module: CM-110 completes the caption
  and the core items (1a, 2a, 3a, 4a, 5, mediation willingness, signature),
  and POS-010 covers personal service. Other forms are not yet implemented.
- **A typed case model.** Parties, counsel, court, documents, exhibits,
  service events, docket entries, validated on construction. Extracted
  values carry provenance: a value that flows onto a filing or into a
  deadline points back at its source document and page.
- **Ingestion.** Local filesystem and IMAP mailboxes (Gmail works with an
  app password), deduplicated by content hash.
- **Operator.** A tool loop giving the model exactly three capabilities:
  read the case model, compute a deadline through the engine, list the
  pack's forms.

371 tests, 97% line coverage on the `prosaic` package, `mypy --strict`
clean.

**Status:** 0.1.0. Young code: the engine and the six forms are tested
against the statutes and the official blanks, but no filing produced by this
codebase has been through a clerk's window yet. Treat it accordingly.

## Documentation

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the layers and
how they fit, or [docs/technical-overview.md](docs/technical-overview.md)
for the end-to-end tour.

| | |
|---|---|
| Running it | [install.md](docs/install.md) · [matter-layout.md](docs/matter-layout.md) · [scheduling.md](docs/scheduling.md) · [backup.md](docs/backup.md) |
| Getting material in | [connectors.md](docs/connectors.md) · [triage.md](docs/triage.md) · [stt.md](docs/stt.md) |
| Getting documents out | [forms.md](docs/forms.md) · [FORM_PACKS.md](docs/FORM_PACKS.md) · [DEADLINES.md](docs/DEADLINES.md) |
| Writing for it | [conventions.md](docs/conventions.md) · [writing-style.md](docs/writing-style.md) · [commits.md](docs/commits.md) |
| Working on it | [development.md](docs/development.md) · [testing.md](docs/testing.md) · [security.md](docs/security.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [CLAUDE.md](CLAUDE.md) |
| Where it's going | [ROADMAP.md](ROADMAP.md) |

Decisions are recorded twice, by scope: [docs/DECISIONS.md](docs/DECISIONS.md)
holds the few that define what the engine is, and [design/](design/) holds
the numbered ADRs for choices inside it. Component contracts live in
[specs/](specs/): what each piece must accomplish, independent of how.

## License

MIT. The Judicial Council form PDFs in `prosaic/packs/civil/blanks/` are
the official published forms, included unmodified.
