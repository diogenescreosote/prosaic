---
name: build-doc
description: Build one source document with sc build-doc and relay the result verbatim. Deterministic; never edits a source.
argument-hint: src/<source>.md [--variant V] [--final] [--force]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" build-doc *)
model: claude-haiku-4-5
effort: low
---

## Build output

!`"@@PROSAIC@@/cli/sc" build-doc $ARGUMENTS 2>&1; echo "[exit $?]"`

## Instructions

Relay the output above: exit status, output paths, every warning line
verbatim. Do not edit any source; if a warning needs a source edit,
name the file and line and stop.
