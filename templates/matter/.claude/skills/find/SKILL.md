---
name: find
description: Exhaustive search of the record for a name, phrase or pattern. Deterministic ripgrep pass first, then read the hits; reports what could not be searched.
argument-hint: <term> [more terms...]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" find *) Read Grep Bash(python3 "@@PROSAIC@@/pleading/ocr_supplement.py" *)
model: claude-sonnet-5
effort: medium
---

## Search results

!`"@@PROSAIC@@/cli/sc" find $ARGUMENTS 2>&1 || true`

## Instructions

You are answering "is this in the record, and where?" The failure this
command exists to prevent is a confident "not found" after a partial
look. Rules:

1. Read every hit above in context (the file and lines named). Answer
   with citations: file, line or page, and the quoted passage.
2. Treat the UNSEARCHED list as unsearched, not absent. If it is
   short, OCR-supplement those PDFs now (the ocr_supplement tool, side
   by side, original untouched) and search the new sidecars; if it is
   long, say exactly which documents remain unsearched.
3. Also search variants: initials, surname alone, likely OCR
   misspellings, and the other party's name for the same event. Run
   `sc find` again for each variant.
4. Only say something is not in the record after steps 1 to 3, and
   then say what was searched: the file counts and the unsearched list.
Never answer from memory.
