---
name: recall
description: Cheap search of what the humans already said (knowledge vault, KNOWLEDGE/TODO/QUESTIONS, mail index; optionally session transcripts). Use before asking the human any factual question, before stating what a document says or is, and before listing questions from a draft's placeholders.
argument-hint: <term> [more terms...]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" recall *) Bash("@@PROSAIC@@/cli/sc" open-questions *) Bash("@@PROSAIC@@/cli/sc" find *) Read Grep
model: claude-haiku-4-5
effort: low
---

## Recall

!`"@@PROSAIC@@/cli/sc" recall $ARGUMENTS 2>&1; echo "[exit $?]"`

## Instructions

Recall costs about a second and a few hundred tokens. Run it often:
it exists because agents re-asked the human questions he had answered
the day before, and repeated a note's description of a document that a
later note had corrected. A usage error above means no terms were
given; run the command yourself with the terms you need.

1. **Before asking the human a factual question**, run
   `sc recall <two or three distinctive terms>`: a name, a date, a
   quoted phrase. Several terms must all appear within three lines
   (`--window N` widens it); `--any` makes them alternatives. Terms
   are case-insensitive regexes. Exit 1 means nothing is recorded.
2. **Before listing questions from a draft**, run
   `sc open-questions <draft.md>`. Each placeholder (`[XX: ...]`,
   `[Confirm ...]`, `[Verify ...]`, `[TODO ...]`) is shown with the
   recorded lines that may answer it. A placeholder is not evidence
   that the question is open. Fill what the record answers, cite the
   note, and ask only what is left. A hit in QUESTIONS.md or TODO.md
   means the question is already asked: point at it, do not ask again.
3. **Read the source before relying on a hit.** A snippet is a lead.
   Open the note at the line given, and when a note describes a
   document, open the document itself: notes are sometimes wrong, and a
   later note may correct an earlier one. Search again for the
   correction (`sc recall <document name> wrong|corrected|not`).
4. **What the human said in a session** is searched only with
   `--transcripts` (user-typed text only, no tool output). Use it when
   the vault is silent and the human may have answered in chat. A fact
   found only there belongs in the vault: record it.
5. Recall searches the knowledge surfaces, not the evidence. A question
   about what the record contains goes to `sc find` (the `/find`
   command), which is exhaustive and reports what it could not search.

Report compactly: the answer with its `path:line`, or "nothing
recorded" with the terms searched. Never answer from memory.
