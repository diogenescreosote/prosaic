# 0051 — The entity matter type: an organization's record book

**Status:** accepted (2026-11)

## Context
prosaic knew two matter types: `litigation` and `estate`. An
organization's governance record (a nonprofit's or a company's
formation, bylaws, board minutes, officers, tax exemption, agency
filings) is neither, and the first one kept here was scaffolded as
litigation for want of anything else. The result was a folder with an
empty `pleadings/` and `discovery/`, a contract that had to explain
how each litigation rule did or did not apply, and the record itself
filed under `assets/` subdirectories its author invented.

The audience is also different. A lawsuit's record is read by its
lawyer and the agents working for that lawyer. A corporation's record
is read by whoever comes after: a new director, a successor
secretary, an auditor, a bank opening an account, an agency asking
for the bylaws. Most of them will never install anything. The estate
pack met the same problem with its `share/` folder (ADR-0028), but
there the human-facing tree is a copy of executed deliverables. For an
entity, the record *is* the thing people browse; a second, curated
copy would only drift from it.

## Decision
`sc init --type entity` scaffolds an entity matter.

- **The record book is `assets/`**, in ten numbered sections with
  plain names: Formation, Governing Documents, Board Minutes and
  Consents, Directors and Officers, Other Official Acts, Tax Status,
  Government Filings, Litigation, Finances, Correspondence. The
  sections are fixed, created empty with a `.gitkeep`, so an empty
  section reads as "none" rather than "never set up." Keeping the
  record under `assets/` means triage, OCR, text coverage, `sc find`
  and the mail connector work unchanged.
- **`START HERE.md` is the front page**, written for a reader without
  prosaic: what the folder is, a table of the sections, the status
  vocabulary, and "Where things stand": the entity's current facts,
  each naming the record that establishes it, updated in the same
  change as the triage that changes it.
- **Provenance moves from `pleadings/` to every INDEX row.** Each
  record carries a status (`filed`, `acknowledged`, `as-submitted`,
  `executed`, `copy`, `not-in-hand`) recorded by a human from the
  document's face, the `pleadings/MANIFEST.md` discipline applied to
  the whole book.
- **Litigation-only directories are not created** (`pleadings/`,
  `discovery/`, `lawyer_drafts/`, `unfiled/`). A suit involving the
  entity is its own litigation matter, linked by `related_matters:`.
- **The contract is one file.** `templates/entity/AGENTS.entity.md`
  is appended to the base matter `AGENTS.md` at init rather than
  replacing it, so the shared matter contract cannot drift between
  types.
- `matter.yaml` carries `case.type: entity`, and `jurisdiction` and
  `form` in place of `court`; `sc brief` prints them.

Inbox stays the only way in. Records are PDFs; a governance act
drafted in markdown enters the record as its executed PDF.

## Consequences
- Tooling that checks `case.type` must keep treating unknown types as
  litigation (specs/matter.md); `entity` gates conventions only.
- Folder names contain spaces. Every tool already quotes paths; the
  estate `share/` tree set the precedent.
- An existing matter converts by hand: set the type, create the
  sections, move records with their INDEX rows, append the addendum.
  There is no migration command; there is one such matter.
