---
name: preflight
description: Run all four preflight reviews (citecheck, clerkreview, judgereview, oppo) on a draft envelope and collate their reports into one page. Optional; never a gate. Use before signing when time allows.
argument-hint: <envelope|src/path.md>
allowed-tools: Bash("@@PROSAIC@@/cli/sc" review *) Read Skill
model: claude-sonnet-5
effort: medium
---

## Target and existing reports

!`"@@PROSAIC@@/cli/sc" review status $ARGUMENTS --tidy 2>&1; echo; "@@PROSAIC@@/cli/sc" review paths $ARGUMENTS 2>&1`

## Collated report file (header already written)

!`"@@PROSAIC@@/cli/sc" review report $ARGUMENTS --check preflight 2>&1`

## Instructions

Stale reports were just moved to superseded/. For each of the four
checks that has no current report for this target, invoke its skill
now with the same argument: /citecheck, /clerkreview, /judgereview,
/oppo, in that order; each reads the sources cold and writes its own
report. Then read the four current reports and write the collated page
into the preflight report file: one section per check with its top
findings verbatim, then a single ranked list across all four of what
must change before signing, what should, and what may. Name every
report you drew from with its path. Do not add findings of your own;
this page collates. Rules for every review: read the sources named above in full before writing
a word; cite the source by file and line for every point; never edit a
source, a build output or a note; write only the report file; a report
whose sources changed after review is stale and must not be quoted as
current (the CHECK line above says which are stale). The report is a
derived artifact under derived/review/, and the header `sc review report`
wrote carries the source hashes that make staleness detectable. Nothing
here blocks a build or a signature; the drafter decides what to do with it.
