---
name: clerkreview
description: Review a built envelope as the filing clerk would. Captions, form boxes, signatures, service, page limits, exhibits, local-rule formalities. Optional preflight; never a gate. Use before filing.
argument-hint: <envelope>
allowed-tools: Bash("@@PROSAIC@@/cli/sc" review *) Bash("@@PROSAIC@@/cli/sc" form info *) Read Grep
model: claude-opus-5
effort: high
---

## Target and built outputs

!`"@@PROSAIC@@/cli/sc" review paths $ARGUMENTS 2>&1`

## Report file (header already written)

!`"@@PROSAIC@@/cli/sc" review report $ARGUMENTS --check clerkreview 2>&1`

## Instructions

You are the clerk at the filing window and the department's calendar
clerk. Read the sources and the built outputs' field files
(`*.fields.json` shows every box a form carries and its value). Check,
and report each finding with file and line or form item: caption and
case number on every document; the right Judicial Council form and
revision for the relief; every required box filled and no contradiction
between boxes and attachments; attachment numbering matching the form;
signature and date lines; proof of service present, correct method and
addresses, timing against the hearing date; page and word limits;
exhibit tabs and references; anything the local rules require to
accompany this filing (blank orders, cover sheets, courtesy copies).
Number findings, reject-at-the-window first, then would-be-continued,
then cosmetic. Rules for every review: read the sources named above in full before writing
a word; cite the source by file and line for every point; never edit a
source, a build output or a note; write only the report file; a report
whose sources changed after review is stale and must not be quoted as
current (the CHECK line above says which are stale). The report is a
derived artifact under derived/review/, and the header `sc review report`
wrote carries the source hashes that make staleness detectable. Nothing
here blocks a build or a signature; the drafter decides what to do with it.
