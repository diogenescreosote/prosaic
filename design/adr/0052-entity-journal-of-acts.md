# 0052 — The entity journal of acts: append-only, checked at commit

**Status:** accepted (2026-11)

## Context
An organization's record book (ADR-0051) holds its documents by
section, but the question a director, auditor or successor secretary
most often asks is chronological: what did we do, when, who decided,
on what vote, and where is the paper? The answer was scattered across
INDEX rows, minutes, and commit messages. Commit messages come closest,
but they are not read by anyone without git, they mix acts with
housekeeping, and they record when a file changed rather than when
the organization acted.

Corporate practice has long kept such a record (a minute book's
register of resolutions, a register of directors). Its worth rests on
one property: an entry, once written, does not silently change. A
journal that can be quietly rewritten is a narrative, not a record.

## Decision
An entity matter keeps **`JOURNAL.md`** at its root, scaffolded by
`sc init --type entity` from `templates/entity/JOURNAL.md`.

- **What it holds.** One entry per institutionally or legally
  memorializable act: formation and agency filings, adoption or
  amendment of articles, bylaws and policies, board votes and written
  consents, elections, appointments, resignations and removals, hiring
  and firing, authorized contracts and commitments, delegations,
  exercises of approval or veto rights by a body that has them,
  determinations received. Not drafts, plans or discussions.
- **Entry format.** `## J-0001 · YYYY-MM-DD · title` (the date of the
  act), then six bullets: `Act`, `By` (who, in what capacity), `Vote`,
  `Authority`, `Record` (a path under `assets/`, or `pending: <what>`),
  `Entered` (`YYYY-MM-DD by <name>`, the date of writing). Numbering
  is contiguous in order of entry.
- **Append-only.** Nothing is deleted. A correction is a new entry
  ("Correction to J-0007: ..."), or rarely an in-place edit carrying
  `> **Amended YYYY-MM-DD by <name>:** what --- why.` directly under
  the changed text, with the old wording kept readable (struck
  through).
- **Checked, not trusted.** `sc journal check` validates the form and
  compares the journal to HEAD: HEAD's text must survive as a prefix,
  except where a change is covered by a newly added Amended line in
  the same entry; removed text fails even when annotated. The matter's
  `commit-msg` hook (`sc commit-check`) runs the same check on a staged
  journal and refuses the commit.
- **The human's override.** A `Journal-Override: <reason>` footer
  lets an unannotated change through (the failures print as warnings).
  It exists because the human said edits may be made unannotated when
  they explicitly say so; the contract forbids an agent to add it.
- **Journal and commit messages both.** They will often say the same
  thing. The commit message serves the repository's history; the
  journal serves the reader who never opens it.

## Consequences
- The entity contract (`templates/entity/AGENTS.entity.md`) makes
  appending the entry part of the same commit as the triage or report
  of the act; `START HERE.md` points lay readers at the journal.
- The gate runs in any repository whose root has a staged
  `JOURNAL.md`, not only entity matters: the file name is the
  convention, and nothing else in prosaic uses it.
- Format errors are not overridable by the footer; they cost a line
  to fix. `git commit --no-verify` still bypasses the hook entirely,
  as with every commit-msg check (docs/commits.md).
- An existing entity matter gains the template by rerunning
  `sc init --type entity <dir>`, which keeps existing files.
- What the check cannot see: whether an entry is true, whether an act
  went unrecorded, or whether struck-through wording is faithful to
  what was there. Those remain the human's and the contract's.
