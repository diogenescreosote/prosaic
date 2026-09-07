# ADR-0043: Knowledge is a vault of notes, not one file

**Status:** Accepted (September 7, 2026)

## Context

The matter template gave durable knowledge one file, `KNOWLEDGE.md`,
with a rule: integrate new facts into sections, never append a log. On
the largest live matter the file reached 3,556 lines, about 82,000
tokens, with fourteen date-titled sections appended as a diary, two
"as of" snapshots superseded by later entries, and no cross-links. Every
session that consulted it paid for the whole file on every call, and the
model doing the consulting was the most expensive one available. When
asked whether a particular interaction was in the record, an agent read
the file several times and answered wrongly.

The rule failed because nothing enforced it and because one file gives
a fact no address. A person, an event and an issue all live in the same
scroll; the only way to find one is to read, and the only reader that
can is a model.

## Decision

1. **Knowledge is a directory of notes**, `knowledge/`, one note per
   person, organization, event, topic, issue or filing, in a folder per
   type. `KNOWLEDGE.md` at the matter root becomes the index,
   regenerated between two markers by `sc knowledge index`.
2. **Front matter is the graph and the grep surface.** Every note
   carries `title`, `type`, `aliases` (every name variant the record
   uses, OCR misspellings included), `tags`, `related` (wikilinks),
   `sources` (path, pages, note), `updated` (an absolute date) and
   `verified` (machine or human). Events carry `date`; issues carry
   `status`. Bodies are keyword-dense prose with absolute dates and no
   dated headings.
3. **The vault is Obsidian-compatible and Obsidian is optional.**
   Wikilinks resolve by filename stem; `aliases` and `tags` are
   Obsidian's own keys; the matter directory opens as a vault with
   backlinks and a graph for a human reader, and `.obsidian/` is
   ignored. Nothing an agent or a tool does depends on Obsidian, and no
   fact may live only in a view that renders inside it. Opening the
   vault in Obsidian and finding useful backlinks is an acceptance
   check, not a dependency.
4. **A linter enforces the rules.** `sc knowledge check` fails on a
   missing title, type or absolute `updated` date, a dated heading, an
   unresolved link, a source path that does not exist, an alias claimed
   by two notes, or a note absent from the index; it warns on orphans,
   relative dates, and staging notes.
5. **Search consults the vault first.** `sc knowledge index` also
   writes `derived/knowledge/entities.json`, an alias index; `sc find`
   prints matching notes before the ripgrep pass, and `sc brief` draws
   upcoming events and open issues from event and issue notes.
6. **Migration is staged and never destructive.** `sc knowledge migrate`
   copies a single-file KNOWLEDGE.md whole into
   `knowledge/_migration/KNOWLEDGE.legacy.md`, splits it by H2 into
   staging notes with front matter, and turns KNOWLEDGE.md into the
   index. The `migrate-knowledge` skill then has an agent fold staging
   into real notes, gated by a human reading the result; staging is a
   warning until it is gone and a human removes it.
7. **Fable writes, cheap models read.** Extraction and integration of
   new documents into notes is Fable-class work at write time. Reading
   back is ripgrep, the alias index, and a Sonnet-class reader
   following links; the vault is what makes that cheap.

## Consequences

- A fact has an address: a note, a heading, a source with a page. Recall
  becomes a lookup, and "everything about X" is the backlinks of X.
- Sessions load the brief and the notes they need, not the whole
  history. The cost profile of every routine session drops.
- The triage prompt and the workspace contract stop saying "update
  KNOWLEDGE.md" and say "create or update the note"; the `record`
  commit type is unchanged.
- Existing matters carry a staging directory until an agent and a human
  finish the migration; `sc upgrade` starts it and the skill documents
  it. The legacy file is never deleted by a tool.
- Human editing in Obsidian is the cheapest review there is; the daily
  standup can happen there. Corrections made in Obsidian are ordinary
  file edits and commit as `record`.
- Two notes about the same person under different names are the new
  failure mode; the alias check and the migration skill's merge step
  exist for it.
