<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/wordmark-dark.svg">
  <img src="assets/wordmark.svg" alt="prosaic." width="330">
</picture>

**Matter-of-fact tooling for self-represented civil litigants.**

[![ci](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml/badge.svg)](https://github.com/diogenescreosote/prosaic/actions/workflows/ci.yml)

The name works twice: "pro se" sits inside it, and *prosaic* — plain,
unadorned, matter-of-fact — is the right aspiration for legal drafting and
for the software that produces it.

prosaic is a document-assembly engine for civil litigation, driven by an
LLM operator. It ingests records from mail and filesystem sources into a
structured case model built around fact-level provenance — a value that
flows onto a filing or into a deadline carries a pointer to its source
document and page — computes filing deadlines from statutory rules, and
renders California court documents from the official forms. Form knowledge
lives in pluggable packs, so the engine itself is jurisdiction-agnostic.
It is built by a law-office-study student for use on one's own case — not
a practice tool for lawyers, and not a substitute for one.

> **This is a document-assembly utility, not legal advice.** Using it creates
> no attorney-client relationship. Every date it computes and every document
> it renders must be reviewed by you before you rely on it or file it. The
> author is a law-office-study-program student, not an attorney. If you can
> get a lawyer, get a lawyer.

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

With `ANTHROPIC_API_KEY` set, `uv run prosaic ask matter.json "..."` runs
the LLM operator against a serialized matter.

## What is implemented today

- **Deadline engine** — CCP §§ 12–12c day arithmetic, the CCP § 1005(b)
  motion-notice schedule, § 430.40(a) demurrers, the § 1013 / § 1010.6
  service extensions, CRC 3.110(b) and 3.725(a). Court days and calendar
  days are distinct types; holiday calendars are data (2025–2028 packaged,
  cross-checked against published court schedules); each rule is covered in
  [docs/DEADLINES.md](docs/DEADLINES.md) with the test that pins it, plus a
  property-based suite (Hypothesis) asserting the invariants examples can't.
- **California civil form pack** — CM-010, CM-110, SUM-100, POS-010,
  MC-030, MC-031, filled into the official Judicial Council AcroForms and
  verified by golden-file tests that read the values back out of the
  produced PDFs. Scope is stated per module: CM-110 completes the caption
  and the core items (1a, 2a, 3a, 4a, 5, mediation willingness, signature),
  and POS-010 covers personal service. Other forms are not yet implemented.
- **Pleading paper and exhibits** — 28-line numbered pleading paper per
  CRC 2.100–2.119, and exhibit assembly with slip sheets and a table of
  exhibits.
- **Ingestion** — local filesystem and IMAP mailboxes (Gmail works with an
  app password), deduplicated by content hash.
- **Operator** — a tool loop giving the model exactly three capabilities:
  read the case model, compute a deadline through the engine, list the
  pack's forms.
- **The matter directory** — a plain-files convention for a live case
  (evidence, work product, knowledge notes) that the rest of the system
  reads and writes: [docs/matter-layout.md](docs/matter-layout.md).
- **Connectors and scheduled sync** — Gmail and law-firm client portals
  pulled into the matter on a schedule, then catalogued by a headless
  triage pass: [docs/connectors.md](docs/connectors.md),
  [docs/scheduling.md](docs/scheduling.md), [docs/triage.md](docs/triage.md).
- **Envelope builds** — Markdown sources with YAML front matter rendered
  to 28-line pleading PDFs and DOCX, assembled with their exhibits and
  cover forms into the filing packets named in `envelopes.yaml`, in
  public and sealed variants: [docs/forms.md](docs/forms.md).

368 tests, 97% line coverage on the `prosaic` package, `mypy --strict`
clean.

**Status:** 0.1.0. Young code: the engine and the six forms are tested
against the statutes and the official blanks, but no filing produced by this
codebase has been through a clerk's window yet. Treat it accordingly.

## Documentation

Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the layers and
how they fit — or [docs/technical-overview.md](docs/technical-overview.md)
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
the numbered ADRs for choices inside it. Component contracts — what each
piece must accomplish, independent of how — live in [specs/](specs/).

## License

MIT. The Judicial Council form PDFs in `prosaic/packs/civil/blanks/` are
the official published forms, included unmodified.
