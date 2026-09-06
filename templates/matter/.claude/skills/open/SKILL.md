---
name: open
description: Open an envelope's built PDFs (or given paths) in the system viewer and list what opened.
argument-hint: <envelope|path> [...] [--variant V]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" open *)
model: claude-haiku-4-5
effort: low
---

## Opened

!`"@@PROSAIC@@/cli/sc" open $ARGUMENTS 2>&1; echo "[exit $?]"`

## Instructions

List the paths above, one per line. If nothing opened because the
envelope has not been built, say so and suggest `/build <envelope>`.
Nothing else.
