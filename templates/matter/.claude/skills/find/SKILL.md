---
name: find
description: Exhaustive search of the record for a name, phrase or pattern. Deterministic ripgrep pass first, then read the hits; reports what could not be searched.
argument-hint: <term> [more terms...]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" find *) Bash("@@PROSAIC@@/cli/sc" text *) Read Grep
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
   hit counts, no snippets. Narrow it --- add a second term, a date, a
   first name --- and run `sc find` again until the hits are readable,
   then read every hit in context. Answer with citations: file, page or
   line, and the quoted passage.
2. Treat the UNSEARCHED list as unsearched, not absent. `--ensure`
   already OCR'd and dumped what tools can; what remains is unreadable,
   unsupported, or needs a human (a transcript, a conversion). Say
   exactly which documents remain unsearched and why.
3. Also search variants: initials, surname alone, likely OCR
   misspellings, and the other party's name for the same event. Run
   `sc find` again for each variant.
4. Only say something is not in the record after steps 1 to 3, and
   then say what was searched: the file counts and the unsearched list.
Never answer from memory.
