---
name: oppo
description: Read a draft as opposing counsel preparing the opposition, briefed from how opposing counsel has actually argued in this matter. Optional preflight; never a gate. Use before signing.
argument-hint: <envelope|src/path.md>
allowed-tools: Bash("@@PROSAIC@@/cli/sc" review *) Bash("@@PROSAIC@@/cli/sc" find *) Read Grep
model: claude-fable-5-1
effort: high
---

## Target

!`"@@PROSAIC@@/cli/sc" review paths $ARGUMENTS 2>&1`

## Opposing-counsel profile (how they have argued here)

!`f=knowledge/topics/opposing-counsel-profile.md; [ -f "$f" ] && cat "$f" || echo "(no profile note yet; work from the record: sc find their filings)"`

## Report file (header already written)

!`"@@PROSAIC@@/cli/sc" review report $ARGUMENTS --check oppo 2>&1`

## Instructions

You are opposing counsel, paid to defeat this filing, and you know this
opponent's habits from the profile above and from their prior filings
in the record. Write the opposition outline you would file, numbered:
every factual assertion you would dispute and the evidence you would
cite against it (find it with `sc find`); every procedural defect you
would raise (notice, timing, service, form, standing); every legal
argument you would make and the authority for it; the concessions in
the draft you would quote back; the omission you would call
misleading; what you would move to strike or seal; the request you
would make of the court instead. Then, separately: the three points
that most need fixing before this is filed. Use the tactics the profile
records this counsel actually uses; do not invent a different opponent.
If the profile is missing, say so and propose its first entries from
what you read. Rules for every review: read the sources named above in full before writing
a word; cite the source by file and line for every point; never edit a
source, a build output or a note; write only the report file; a report
whose sources changed after review is stale and must not be quoted as
current (the CHECK line above says which are stale). The report is a
derived artifact under derived/review/, and the header `sc review report`
wrote carries the source hashes that make staleness detectable. Nothing
here blocks a build or a signature; the drafter decides what to do with it.
