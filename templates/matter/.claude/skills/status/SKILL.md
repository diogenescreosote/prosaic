---
name: status
description: Where this matter stands right now, from the deterministic brief, git status and the stale-output report.
allowed-tools: Bash("@@PROSAIC@@/cli/sc" brief *) Bash("@@PROSAIC@@/cli/sc" clean *) Bash(git status *)
model: claude-haiku-4-5
effort: low
---

## Brief

!`"@@PROSAIC@@/cli/sc" brief . 2>&1 || true`

## Working tree

!`git status --short 2>&1 | head -60 || true`

## Stale output

!`"@@PROSAIC@@/cli/sc" clean . 2>&1 | tail -5 || true`

## Instructions

Present the three sections above compactly. Do not read KNOWLEDGE.md or
any other file; this command is a snapshot, not an investigation.
