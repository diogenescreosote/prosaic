---
name: commit
description: Commit the current work as a typed matter commit, staging by explicit path. Never git add -A, never amend.
argument-hint: <type(scope): subject> [-- paths...]
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git add *) Bash(git commit *) Bash(git log *)
model: claude-sonnet-5
effort: medium
---

## Working tree

!`git status --short 2>&1 | head -80`

## Diff summary

!`git diff --stat 2>&1 | tail -30; git diff --cached --stat 2>&1 | tail -30`

## Instructions

The argument is the commit subject in the matter convention
`type(scope): subject` (types: intake, triage, draft, build, docket,
discovery, record, config, chore; `!` after the type marks a change to
the evidentiary record). Stage only the paths that belong to that
change, by explicit path; if paths were given after `--`, stage exactly
those. Write a body saying why and what a reader needs to know; add the
footers the convention requires (`Filed:`/`Served:`/`Received:` on
docket, `Drafted-by: agent` on draft touching src/, `Verified:` when
machine output is added). Dates absolute. Never `git add -A`, `-a`, or
a directory; never amend, rebase or push. If the subject's type is
`docket` and no date was supplied, stop and ask for it rather than
inventing one. Show the resulting `git log -1 --stat`.
