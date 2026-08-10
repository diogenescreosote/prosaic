# 0014 — Docket-shaped commits, and what an agent may commit

**Status:** accepted (2026-08)

## Context
ADR-0001 makes git the audit trail of a matter, and the conventions
push work *into* it: pleadings may carry no drafting-history
annotations, so the reasoning for a change has nowhere else to live.
Meanwhile agents now make most of the changes. Commit messages across
the matters were freeform, and the working trees were accumulating
dozens of uncommitted files "for human review" — which is a worse
review surface than a series of commits, since it has no grouping, no
reasoning, and does not survive a clobbered tree.

Conventional Commits is the obvious import and the wrong one:
`feat`/`fix`/`chore` answers "what does this do to the product?" and a
matter has no product. There is no published prior art — git-for-law
writing covers branching and merging documents, and the legislative
work models bills as pull requests; none of it defines a type
vocabulary. The question a legal history actually has to answer is
*what happened, and did it happen in the world or only in this
folder?* — which is what a docket has recorded for centuries.

## Decision
Commits in a matter take the form `type(scope): subject` with nine
types drawn from the docket: `intake`, `triage`, `draft`, `build`,
`docket`, `discovery`, `record`, `config`, `chore`. `!` marks a change
to the evidentiary record, the legal analog of a breaking change.
Footers carry what prose cannot be trusted to: `Filed:`/`Served:`/
`Lodged:`/`Received:` on docket events, `Source:` for provenance,
`Verified:` for machine-generated content, `Exhibits:` when letters
shift, `Drafted-by:` for authorship of work product.

Agent commit authority is derived, not new: the commit inherits the
change's authority and never creates any. On top of that, an agent
stages by path (never `-A`), never asserts a real-world event it did
not witness, never pushes a matter or carries case material into
prosaic, never rewrites history, never modifies an original, and
commits at the natural seams of the work rather than hoarding a
working tree. `sc commit-check` validates a message; `sc hooks`
installs a `commit-msg` hook that runs it, and `sc init` installs it
for new matters.

## Consequences
`draft` and `docket` being different types is the payload: it makes
history state whether a document left the building, which no artifact
in `out/` can be inspected to determine. `Verified:` and `Drafted-by:`
answer, years later, whether a human checked a machine transcript
before it was quoted and who actually wrote a paragraph of a
declaration — questions with real professional consequences, whose
answers exist nowhere else once the session that produced them is
gone. `git log --oneline | grep '!'` becomes "what changed about what
this case says?"

The hook fails on an unknown type and only warns on a missing footer.
That asymmetry is deliberate: a wrong type is one word to fix, while
being blocked by a hook in the middle of a filing is how `--no-verify`
becomes habitual, and a bypassed check is worth less than no check.

Costs: nine types is more vocabulary than a small matter needs, and
some commits will sit on a boundary — a rebuilt envelope that also
fixes a typo in its source is two commits or a judgment call.
`Drafted-by:` records origin at write time and is deliberately not
maintained afterward, so it cannot be read as current workflow state;
that limit is written into docs/commits.md rather than left to be
discovered. And the convention binds agents far more than humans, who
can always `--no-verify` — which is the correct asymmetry, since the
agents are the ones generating the volume.
Alternatives: Conventional Commits unchanged (rejected — its
categories answer a question a matter does not ask); freeform messages
with a style guide (rejected — unenforceable, and the existing history
shows the drift); a separate changelog file (rejected — a second place
to keep in sync with git, and ADR-0001 already says the files are the
record).
