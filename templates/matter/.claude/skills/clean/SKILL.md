---
name: clean
description: Report stale files in out/ that the current configuration can no longer produce. Report only; never deletes.
allowed-tools: Bash("@@PROSAIC@@/cli/sc" clean *)
model: claude-haiku-4-5
effort: low
---

## Stale output report

!`"@@PROSAIC@@/cli/sc" clean . 2>&1; echo "[exit $?]"`

## Instructions

Relay the report verbatim, tracked and untracked files separately. Do
not delete anything: `sc clean --apply` is the user's own command, run
by them, after reading this. Remind them that a hand-assembled packet
or a timestamp token in out/ can be listed as stale and must not be
deleted.
