---
name: standup
description: The daily thirty-minute knowledge standup. Walk the human through today's agenda (questions, refinement proposals, corrections), write the answers into the knowledge vault as human-verified, and commit. Use when the standup agenda notification arrives or the user says standup.
argument-hint: [YYYY-MM-DD]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" standup *) Bash("@@PROSAIC@@/cli/sc" knowledge *) Bash("@@PROSAIC@@/cli/sc" find *) Read Edit Write Bash(git status *) Bash(git diff *) Bash(git add *) Bash(git commit *) Bash(git log *)
model: claude-opus-5
effort: medium
---

## Today's agenda

!`"@@PROSAIC@@/cli/sc" standup agenda . 2>/dev/null >/dev/null; f=$(ls -1 derived/standup/*.md 2>/dev/null | tail -1); [ -n "$f" ] && cat "$f" || echo "(no agenda; run sc standup agenda .)"`

## Latest refinement proposal

!`f=$(ls -1 derived/refine/????-??-??.md 2>/dev/null | tail -1); [ -n "$f" ] && sed -n '1,220p' "$f" || echo "(no proposal yet)"`

## How to run it

You are the scribe for a thirty-minute standup; the human decides. Work
the agenda top to bottom, one item at a time, in this order: failed
sync or coverage gaps first (they hide facts), then open questions, then
the refinement proposal's items, then note corrections the human
volunteers.

For each item, ask one question or present one proposal, wait for the
answer, then act:

- An answered question: write the fact into the note for its subject
  (`knowledge/<type>/<stem>.md`) with the absolute date and a source
  line `(source: <who said it>, standup <date>)`, set that note's
  `verified: human`, and remove the question from QUESTIONS.md.
- An accepted proposal: apply exactly the proposed text; a source is
  required; an amended proposal gets the human's wording.
- A rejected proposal: leave the note alone; record the reason in one
  line at the end of the proposal file.
- A new fact volunteered: same as an answered question. A new subject:
  `sc knowledge new . --type T --title "..."`.

Never invent, never paraphrase a quotation, never delete a fact you
cannot replace. Stop at thirty minutes or when the agenda is done and
say what is left.

Finish: `sc knowledge index .` then `sc knowledge check .` (zero errors),
then commit only the files you touched, by explicit path:
`record(standup): <date>` with a body listing questions answered,
proposals accepted and rejected, notes changed. Never `git add -A`,
never amend, never push.
