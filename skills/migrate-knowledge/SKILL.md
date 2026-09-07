---
name: migrate-knowledge
description: Fold a legacy single-file KNOWLEDGE.md into the vault of typed notes (ADR-0043). Use when a matter has knowledge/_migration staging notes after `sc upgrade` or `sc knowledge migrate`. Fable-class work, gated by a human before staging is removed.
---

# Migrate a matter's knowledge into the vault

Run this after `sc upgrade <matter>` or `sc knowledge migrate <matter>`
has created `knowledge/_migration/`. The legacy file is preserved there
as `KNOWLEDGE.legacy.md`; never delete it yourself.

## Rules

- Read every staging note whole before writing anything. Staging notes
  are sections of the old file; a fact often sits in a section named for
  something else.
- Every fact you move keeps its date (absolute) and gains a source: the
  document path and page, verified against `derived/text/` with
  `sc find`, never from memory. A fact you cannot source stays in the
  note marked `(source: legacy KNOWLEDGE.md, unverified)`.
- Never invent a name. Aliases are the variants the record actually
  uses; grep the record for each person's surname to collect them.
- Never delete a fact you cannot place. If it fits no note, it goes in a
  `topic` note named for its subject.

## Steps

1. `sc knowledge check <matter>` --- confirm only staging warnings.
2. Inventory: from the staging notes, list every person, organization,
   recurring event type, dispute (issue) and distinct topic. Merge
   duplicates now (one person, one note).
3. Create notes: `sc knowledge new <matter> --type person --title "..."
   --alias "..."` for each entity; `event` notes for hearings, filings,
   service, orders (with `date:`); `issue` notes for disputes
   (`status: open|resolved`); `topic` notes for analysis.
4. Move content section by section. Dated diary sections become event
   notes plus updates to the entity notes they mention; "as of" snapshots
   become the current text of the relevant note with `updated:` set to
   the snapshot date.
5. Link: every note's `related:` names the notes it depends on; bodies
   use `[[stem]]` wikilinks. Set `verified: human` only on notes a human
   has read.
6. `sc knowledge index <matter>` then `sc knowledge check <matter>`:
   zero errors; warnings only for staging.
7. Stop. Report: notes created by type, facts left unsourced, staging
   notes not yet emptied. The human reviews in Obsidian (open the matter
   directory as a vault; check backlinks on the parties) and removes
   `knowledge/_migration/*.md` except the legacy copy when satisfied.
8. Commit as `record(knowledge): ...` with `Drafted-by: agent`.

## What to expect

A 3,500-line file yields roughly 60 to 120 notes. Budget one session per
matter; do not split the work across sessions without recording in the
staging notes which sections are done.
