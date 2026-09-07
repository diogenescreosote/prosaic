# ADR-0045: Preflight review is four optional checks, never a gate

**Status:** Accepted (September 7, 2026)

## Context

The v2 proposal first framed adversarial review as a gate: `--final`
and `sc sign` would refuse without an approval keyed to the source
hash. The owner rejected the gate and asked for optional checks a
drafter runs by choice, split by persona so each reads the draft cold.
Two facts shaped the design. First, a review is about one revision of a
source; once the source changes the report critiques something that no
longer exists, and a stale report quoted as current is worse than no
report. Second, the personas are worth more apart than together: a
judge who has read the opposing counsel's outline is no longer reading
cold.

## Decision

1. **Four commands, four skills, each runnable alone**: `/citecheck`
   (deterministic extraction of every statute, rule, local rule, federal
   and case citation, then a model pass on existence, form and the
   proposition), `/clerkreview` (the filing window and the calendar
   clerk, against the built outputs and their field files),
   `/judgereview` (the skeptical bench, numbered worst first), `/oppo`
   (opposing counsel, briefed from a profile note of how they have
   actually argued in this matter). `/preflight` runs the four that lack
   a current report and collates without adding findings.
2. **Nothing gates on them.** Builds, `--final`, signing and service are
   unchanged. A report is advice to the drafter, written as a derived
   artifact under `derived/review/<target>/`.
3. **Every report records what it reviewed.** `sc review report` writes
   the header: the check, the target, the combined and per-file sha256
   of the sources, the commit, and `status: current`. The filename
   carries the date and the short hash.
4. **Staleness is computed, then acted on.** `sc review status`
   recomputes the sources' hashes and marks any report whose sources
   changed as stale, rewriting its status line; `--tidy` moves stale
   reports into `superseded/`. `sc review paths`, which every skill runs
   first, lists current reports and names stale ones as not to be
   quoted. `/preflight` tidies before it collates.
5. **The cite extractor is deterministic and over-inclusive.** A false
   positive costs a reader one row; a missed cite is the failure the
   check exists to prevent. `knowledge/authorities.yaml` holds cites a
   human has verified, keyed by normalized cite, with the proposition
   and a date; the check treats them as verified for existence and still
   checks the proposition.
6. **Each persona declares its own model.** Cite, clerk and judge run
   on Opus; opposing counsel runs on the strongest model available, and
   a deployment may point it at another vendor through `agent-run`'s
   custom command when it wants a different mind (the owner's decision
   4 allows any vendor for his own matters). Personas do not read each
   other's reports; only the collator does.
7. **The bench sees only what the court sees.** `/judgereview` reads
   the filing, its exhibits and the filed record under `pleadings/`,
   and nothing else; `sc find --scope` restricts a search to named
   directories for the same reason. A finding that rests on the
   drafter's notes is not one a judge could make.
8. **A second opinion from a different mind is a fifth command.**
   `/secondopinion` sends the draft and a one-paragraph brief to the
   `second-opinion` role, normally another vendor's model reached
   through a role-level command with a Keychain-resolved credential,
   and the drafting model then weighs every suggestion against the
   sources and the record into accepted, rejected and needs-the-human,
   applying nothing until told. The other model sees the draft and the
   brief only; the integration stays with the model that has the file.
9. **The opposing-counsel profile is knowledge.** A topic note,
   `knowledge/topics/opposing-counsel-profile.md`, records how opposing
   counsel argues, what they move to strike, what they call misleading,
   with cites to their filings; the nightly refinement proposes updates
   to it from new filings and correspondence.

## Consequences

- A drafter can run one check in a minute or all four before a filing,
  and skip them under time pressure without breaking anything.
- A report can never silently describe a superseded draft: the hash in
  its header and filename ties it to a revision, and the status pass
  demotes it the moment the source moves.
- Cite checking has a deterministic floor: the table of what the draft
  cites is produced without a model, and the model's job is judgment on
  each row, not discovery.
- `flows/draft-review.yaml` remains the batch form for `sc flow`, useful
  when a review should run on a different vendor or entirely outside a
  session.
- Reports accumulate under `derived/review/`; `sc clean --older-than`
  covers them.
