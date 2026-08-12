# Spec: AI triage

## Purpose

After each sync, one headless AI session folds the new material into
the matter: catalog rows for email threads, knowledge updates from
message reports, routing for staged portal documents. The triage
agent is a *clerk*, not a lawyer — its value is that a human opening
the matter finds everything new already named, indexed, summarized,
and routed, and its safety comes from doing strictly less than it
could: an unattended pass that under-acts is recoverable; one that
guesses confidently is expensive.

## Promises

1. **Conservative by default.** When significance or routing is
   unclear, the agent leaves the file where it is, marks it "needs
   human review" in the catalog/index, and moves on. Uncertainty
   produces annotations, never relocations. *(untested)*
2. **Everything it does is legible in git.** Triage output is
   ordinary text changes — catalog rows, index rows, KNOWLEDGE.md
   diffs — in a directory that should be a git repository, so every
   session's work is diffable and revertable; the sync log records
   what ran and what it was given. *(untested)*
3. **Nothing new goes unrecorded.** Every file the sync hands over
   gets its catalog or index row: gmail threads a CATALOG.md row
   (date, subject, participants, gist, relevance), portal reports a
   knowledge summary of case-significant exchanges, portal documents
   a routed home (pleadings, lawyer drafts, or assets with an index
   row) or an explicit needs-review annotation. *(untested)*
4. **Privilege is marked.** Attorney-client threads are labeled
   PRIVILEGED in catalogs — a labeling convention for the humans
   working the file, not access control, and the spec is honest
   about that distinction. *(untested)*
5. **The agent never acts on the outside world.** It never files,
   serves, sends, or signs anything; triage ends at the matter
   directory's edge. *(untested)*
6. **Pleading sources are off-limits.** Triage never edits anything
   under `src/` — evidence processing and advocacy drafting are
   separate activities, and an unattended session does not get to do
   the second. *(untested)*
7. **Deletion is nearly impossible.** The only thing triage may
   delete is a staged duplicate whose content-identical twin is
   already in place (compared by content, not name). Everything else
   — including apparent junk — is kept and flagged. *(untested)*
8. **The matter contract binds every session.** Running inside the
   matter directory picks up its agent contract (AGENTS.md) automatically, so index
   discipline, originals-are-sacred, NOTREAL, and typography rules
   apply without being restated in the prompt. *(untested)*

## Non-obvious constraints

- **Triage reads adversarial documents.** Opposing filings, hostile
  emails, and portal documents are untrusted input that may contain
  text *addressed to an AI* ("ignore your instructions and…").
  Instructions arrive only from the prompt template and the matter's
  agent contract; content of triaged material is data to be cataloged,
  never directives to be followed. A document that appears to
  instruct the agent is itself a fact worth flagging for human
  review.
- **Unattended operation requires skipping permission prompts**, so
  the risk budget lives elsewhere: the prompt's scope rules, the
  matter contract, and git revertability. Weakening any of those
  three quietly raises the cost of the other two.
- **Bulk backfills don't go through the headless pass.** The design
  assumes a handful of files per 12-hour window; initial imports of
  hundreds of documents get mechanically generated backfill indexes
  and interactive supervision, because cataloging depth is a
  judgment call at that scale.
- **Machine summaries are working aids, not citations** — anything
  triage writes into a catalog or knowledge file is subject to the
  matter-wide verify-before-citing rule.
