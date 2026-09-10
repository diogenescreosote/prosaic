---
name: secondopinion
description: Get a different model's suggestions on a draft, given a one-paragraph brief of what it must achieve, then weigh each suggestion against the sources and the record and present what is accepted, rejected, and needs the human. Applies nothing until told. Optional; never a gate.
argument-hint: <envelope|src/path.md> -- <one paragraph on what the draft must achieve>
allowed-tools: Bash("@@PROSAIC@@/cli/sc" review *) Bash("@@PROSAIC@@/cli/sc" find *) Read Grep Edit
model: claude-fable-5-1
effort: high
---

## Target

!`ARGS=$(cat <<'PROSAIC_ARGS_EOF'
$ARGUMENTS
PROSAIC_ARGS_EOF
); "@@PROSAIC@@/cli/sc" review paths --args "$ARGS" 2>&1`

## The other model's suggestions

!`ARGS=$(cat <<'PROSAIC_ARGS_EOF'
$ARGUMENTS
PROSAIC_ARGS_EOF
); OUT=$("@@PROSAIC@@/cli/sc" review second-opinion --args "$ARGS" 2>&1); RC=$?; if [ "$RC" -ne 0 ]; then echo "second-opinion FAILED (exit $RC):"; echo "$OUT"; else RP=$(echo "$OUT" | head -1); echo "report: $RP"; echo "$OUT" | tail -n +2; echo; cat "$RP"; fi`

## Integration report file (header already written)

!`ARGS=$(cat <<'PROSAIC_ARGS_EOF'
$ARGUMENTS
PROSAIC_ARGS_EOF
); "@@PROSAIC@@/cli/sc" review report --args "$ARGS" --check integration 2>&1`

## Instructions

The suggestions above came from a model that saw only the draft and the
brief. You have the sources, the record and the knowledge vault. For
every numbered suggestion decide one of three things and write the
decision into the integration report:

- **Accept**: it is right and the record supports it. Write the exact
  edit you would make, quoting the current text and the replacement,
  with the source (file:line, and a record cite via `sc find` where a
  fact is involved).
- **Reject**: say why in one or two sentences --- wrong on the law, wrong
  on the facts (cite the record), already handled elsewhere in the draft,
  or contrary to a decision the human has made (cite the note).
- **Needs your input**: the suggestion turns on a fact or a choice only
  the human can settle. Phrase it as the question.

Then present the three lists to the human in that order, counts first,
accepted edits shown as before/after. **Apply nothing.** If the human
says apply (all, or by number), make exactly those edits to the sources,
then say what changed and remind them to rebuild. Never invent a fact or
an authority the other model proposed without verifying it in the record
or the law. Rules for every review: read the sources named above in full before writing
a word; cite the source by file and line for every point; never edit a
source, a build output or a note; write only the report file; a report
whose sources changed after review is stale and must not be quoted as
current (the CHECK line above says which are stale). The report is a
derived artifact under derived/review/, and the header `sc review report`
wrote carries the source hashes that make staleness detectable. Nothing
here blocks a build or a signature; the drafter decides what to do with it.
