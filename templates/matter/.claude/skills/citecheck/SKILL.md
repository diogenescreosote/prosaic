---
name: citecheck
description: Verify every citation in a draft envelope or source. Deterministic extraction first, then a model pass on each cite's existence, form and the proposition it is cited for. Optional preflight; never a gate. Use before signing or when asked to check cites.
argument-hint: <envelope|src/path.md>
allowed-tools: Bash("@@PROSAIC@@/cli/sc" review *) Bash("@@PROSAIC@@/cli/sc" find *) Read Grep WebSearch WebFetch
model: claude-opus-5
effort: high
---

## Target

!`"@@PROSAIC@@/cli/sc" review paths $ARGUMENTS 2>&1`

## Citations the extractor found

!`"@@PROSAIC@@/cli/sc" review cites $ARGUMENTS 2>&1`

## Report file (header already written)

!`"@@PROSAIC@@/cli/sc" review report $ARGUMENTS --check citecheck 2>&1`

## Instructions

For every row in the table, and for any citation the extractor missed
that you find while reading the sources, decide three things and write
them into the report as one table row each: (1) does the authority
exist as cited (statute or rule section present, case name, year,
reporter and page consistent), (2) is the form correct for a California
filing, (3) does the authority say what the draft uses it for --- quote
the draft's sentence and the authority's operative words. Status per
row: ok, form, wrong-proposition, not-found, or unverified. The
authority cache at knowledge/authorities.yaml lists cites a human has
already verified; treat its entries as verified for existence but still
check the proposition. Where you cannot verify existence offline, say
unverified rather than guessing; WebSearch is allowed for public law.
End with a list of rows needing the human, worst first. Rules for every review: read the sources named above in full before writing
a word; cite the source by file and line for every point; never edit a
source, a build output or a note; write only the report file; a report
whose sources changed after review is stale and must not be quoted as
current (the CHECK line above says which are stale). The report is a
derived artifact under derived/review/, and the header `sc review report`
wrote carries the source hashes that make staleness detectable. Nothing
here blocks a build or a signature; the drafter decides what to do with it.
