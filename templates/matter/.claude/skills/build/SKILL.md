---
name: build
description: Build a filing envelope with sc build and relay the result verbatim. Deterministic; never edits a source.
argument-hint: <envelope> [--variant V] [--final] [--force] [--date YYYY-MM-DD]
allowed-tools: Bash("@@PROSAIC@@/cli/sc" build *)
model: claude-haiku-4-5
effort: low
---

## Build output

!`"@@PROSAIC@@/cli/sc" build $ARGUMENTS 2>&1; echo "[exit $?]"`

## Instructions

Relay the output above: the exit status, every output path, and every
warning line verbatim (spaced dash, front-matter key not read by
anything, no --variant specified, stale). Do not edit any source. If a
warning needs a source edit, name the file and line and stop; that is a
separate decision for the user. Do not rebuild, do not run anything else.
