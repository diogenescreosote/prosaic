# The knowledge vault

Durable case knowledge is a directory of notes, `knowledge/`, one per
person, organization, event, topic, issue or filing, with `KNOWLEDGE.md`
as its generated index (ADR-0043). It replaces the single file that grew
past 3,500 lines on a live matter and could only be read by a model.

## A note

```
knowledge/people/jane-roe.md
---
title: Jane Roe
type: person
aliases: [J. Roe, Roe, "Jane Rowe"]      # every variant the record uses, OCR errors included
tags: [counsel, opposing]
related: ["[[smith-v-roe]]", "[[2026-09-18-motion-hearing]]"]
sources:
  - path: assets/gmail/2026-01-02_letter.pdf
    pages: "3-4"
    note: the retainer date
updated: 2026-09-07
verified: machine          # human once a person has read it
---

# Jane Roe

Prose with absolute dates, the names the record actually uses, and a
source for each fact. No dated headings; an event gets its own note.
```

Events add `date: YYYY-MM-DD`; issues add `status: open | resolved`.
Wikilinks are `[[stem]]`, the filename without `.md`, or a matter path
such as `[[assets/gmail/2026-01-02_letter.pdf]]`.

## Commands

```
sc knowledge init .                         # scaffold the vault
sc knowledge new . --type person --title "Jane Roe" --alias "J. Roe"
sc knowledge check .                        # lint; exit 1 on any error
sc knowledge index .                        # regenerate KNOWLEDGE.md and derived/knowledge/entities.json
sc knowledge migrate .                      # split a legacy single-file KNOWLEDGE.md into staging
```

The linter fails on a missing title, type or absolute `updated`, a
dated heading (the diary pattern), an unresolved link, a source path
that does not exist, an alias two notes claim, or a note missing from
the index. It warns on orphans, relative dates, and staging notes.

## Obsidian

The matter directory opens as an Obsidian vault: wikilinks resolve by
filename, `aliases` and `tags` are Obsidian's own keys, and the
backlinks pane on a person is "everything about X" with no model
involved. `.obsidian/` is ignored. Obsidian is optional and nothing
depends on it; a fact that only exists in a view rendered inside
Obsidian does not exist. Opening the vault and finding useful backlinks
on the parties is the acceptance check for a migration.

## How search uses it

`sc knowledge index` writes `derived/knowledge/entities.json`. `sc find`
prints the notes whose aliases match a term before the ripgrep pass;
`sc brief` lists upcoming `event` notes and open `issue` notes. Fable
writes notes at triage; ripgrep, the alias index and a Sonnet-class
reader read them back.

## Migrating an existing matter

`sc upgrade <matter>` (or `sc knowledge migrate`) preserves the single
file as `knowledge/_migration/KNOWLEDGE.legacy.md`, splits it by H2 into
staging notes with front matter, and turns `KNOWLEDGE.md` into the
index. The `migrate-knowledge` skill then has an agent fold staging into
real notes, and a human reviews the result in Obsidian before removing
staging. A tool never deletes the legacy file. See `upgrade.md`.
