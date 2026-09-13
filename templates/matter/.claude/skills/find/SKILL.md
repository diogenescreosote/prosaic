---
name: find
description: Exhaustive search of the record for a name, phrase or pattern. Deterministic ripgrep pass first, then read the hits; reports what could not be searched.
argument-hint: <term> [more terms...]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" find *) Bash("@@PROSAIC@@/cli/sc" text *) Bash("@@PROSAIC@@/cli/sc" mail-index *) Read Grep
model: claude-sonnet-5
effort: medium
---

## Search results

!`"@@PROSAIC@@/cli/sc" find --ensure $ARGUMENTS 2>&1 || true`

## Instructions

You are answering "is this in the record, and where?" The failure this
command exists to prevent is a confident "not found" after a partial
look. Rules:

0. Related matters (matter.yaml `related_matters:`) are searched too and
   their hits appear under their own heading. A document about a shared
   party may live in the other matter's record; cite it with its matter.
1. A broad term (a surname, a place) comes back as a summary: files with
   hit counts, no snippets. Any search hitting more than ten files also
   writes a CHECKLIST file under `derived/find/`.
   Narrow with `--all` and a second term until the hits are readable,
   then read every hit in context. Every file on the checklist must be
   marked `[read]` or `[skip: reason]` (a skip on filename alone must say
   "filename only"), and `sc find --verify <checklist>` must pass before
   you answer. Put the skips and their reasons in your report. Answer
   with citations: file, page or line, and the quoted passage.
2. Treat the UNSEARCHED list as unsearched, not absent. `--ensure`
   already OCR'd and dumped what tools can; what remains is unreadable,
   unsupported, or needs a human (a transcript, a conversion). Say
   exactly which documents remain unsearched and why.
3. Also search variants: initials, surname alone, likely OCR
   misspellings, and the other party's name for the same event. Run
   `sc find` again for each variant. Two words that belong together
   (`family` … `therapist`) go through `sc find --near A B`, which
   hits any line where they sit within six words of each other in
   either order. A question about who wrote what and when goes
   through the per-message mail index as well:
   `sc mail-index . --from <sender> --after YYYY-MM-DD --before YYYY-MM-DD [--grep RE]`
   prints every message from that sender in the window with its own
   date, snippet and thread pointer (`assets/gmail/<thread>.pdf`, text
   at `derived/text/assets/gmail/<thread>.pdf.txt`); a thread file is
   dated by its first message, which may be weeks before the message
   you want, so never guess at a filename by date.
4. Only say something is not in the record after steps 1 to 3, and
   then say what was searched: the file counts and the unsearched list.
Never answer from memory.
