# Commits in a matter

A matter's git history is not a changelog. It is the record of what
happened to a case — and it is the only place some of that record
lives, because the conventions deliberately keep drafting history out
of the documents themselves.

So the commit vocabulary comes from what a docket records, not from
what a build system records. `feat` / `fix` / `chore` answers "what
does this do to the product?" A matter has no product. The question a
legal history has to answer is **what happened, and did it happen in
the world or only in this folder?**

That distinction is not academic. A final-looking PDF in `out/` is the
same object whether or not it was ever filed. Nothing about the file
says which. The `notreal:` banner
([ADR-0015](../design/adr/0015-unfiled-documents-announce-themselves.md))
handles it on the page; the commit type handles it in history.

## Format

```
type(scope): subject

body — why, and what a reader needs to know

Footer-Key: value
```

- Imperative, lowercase, no trailing period, subject line under 72
  characters.
- **Dates absolute, never relative.** "yesterday" is meaningless in a
  record read a year later — the same rule KNOWLEDGE.md follows.
- Scope is the envelope, connector, or document set:
  `triage(gmail)`, `draft(subpoenas_aug_7)`, `docket(opposition)`.

## Types

| Type | Means | Typically touches |
|---|---|---|
| `intake` | material arrived; nothing evaluated yet | `inbox/`, connector pulls, `processed_files/` |
| `triage` | material became evidence: OCR, sidecars, INDEX row | `assets/`, `assets/INDEX.md` |
| `draft` | work product written or revised; **not filed** | `src/`, `memos/`, `lawyer_drafts/` |
| `build` | outputs regenerated from sources; no decisions inside | `out/` |
| `docket` | a real-world event: filed, served, lodged, received | `pleadings/` |
| `discovery` | requests, responses, subpoenas, productions | `discovery/` |
| `record` | durable case knowledge | `KNOWLEDGE.md`, `TODO.md`, `QUESTIONS.md` |
| `config` | matter machinery | `matter.yaml`, `envelopes.yaml`, `Makefile` |
| `chore` | housekeeping with no case meaning | renames, `.gitignore` |

`sc commit-check --list-types` prints this list.

`draft` and `docket` being separate types is the point of the whole
scheme. `build` being separate tells a reviewer that no judgment is
inside — only regeneration.

### `!` — this changes the record

Conventional Commits uses `!` for a breaking change. The analog in a
matter is **a change to what the evidence says**: removing an asset,
re-pointing a symlink, shifting exhibit letters, correcting a fact
previously asserted in KNOWLEDGE.md.

```
triage(mycase)!: replace the April 10 export with the complete range
```

`git log --oneline | grep '!'` then answers "what has changed about
what this case says?"

## Footers

| Footer | When | Why |
|---|---|---|
| `Filed:` `Served:` `Lodged:` `Received:` `Executed:` `Recorded:` | required on `docket` (one of them) | date + court, method, or ceremony |
| `Source:` | expected on `intake`, `triage`, `docket` | connector pull, counsel email, ECF, hand delivery |
| `Verified:` | required when the commit adds machine output | `machine — unverified`, or `human, <initials> <date>` |
| `Exhibits:` | when exhibit letters shift | the change cascades into every pleading citing them |
| `Drafted-by:` | on `draft` touching `src/` | `agent`, `human`, or `agent, revised by human` |
| `Co-Authored-By:` | agent-assisted commits | standard git attribution |

`Verified:` and `Drafted-by:` are the two that earn their keep over
time. "Did a human check this transcript before we quoted it?" and
"who wrote this paragraph of the declaration?" are questions with real
consequences, and git is the only place the answer survives.

`Drafted-by:` records **origin at the time of writing** and is not
maintained afterward. It is not a workflow state, so it cannot go
stale; if a human later rewrites the paragraph, that is a new commit
with its own footer.

## Examples

```
intake(gmail): pull the 2026-08-07..08-09 thread PDFs

Scheduled sync. Not yet triaged into assets/ — no INDEX row, no
exhibit number, nothing cited from it.

Source: gmail connector, scheduled run 2026-08-09
```

```
docket: add the 7/29 order granting the peremptory challenge

Received: 2026-07-29, San Francisco County Superior Court
Source: MyCase docket download
Verified: machine — unverified (OCR text layer)
```

```
triage(mycase)!: replace the April 10 export with the complete range

The earlier export stopped mid-thread; the replacement covers the
full exchange. Exhibit F cited the truncated version.

Exhibits: F re-points to the complete export; letters unchanged
Source: portal manual export, 2026-08-09
```

## What agents may commit

The commit inherits the change's authority. **It never creates new
authority** — if the edit needed consent, so does the commit.

Beyond that, six rules specific to the act of committing:

1. **Stage by path.** Never `git add -A` or `git commit -a` in a
   matter. A blanket add sweeps up whatever the human had in flight —
   a half-edited declaration, a file dragged in mid-thought — and
   buries it under someone else's message.
2. **Never assert an event you did not witness.** `Filed:`, `Served:`,
   `Lodged:` go in only on the user's statement or on the face of the
   document. An agent may write `docket: add respondent's 7/27
   objections` from a PDF it found; it may **not** supply
   `Filed: 2026-07-27` by inference. This is the NOTREAL rule extended
   to history.
3. **Matters are private; prosaic is public.** An agent may push a
   matter to its configured `backup` remote and **nowhere else**, and
   does not add or repoint that remote — see
   [docs/backup.md](backup.md). No case material crosses into
   prosaic: not into tests, examples, docs, ADRs, or commit
   messages.
4. **Never rewrite history.** No amend, no rebase, no force, on
   anything a human authored or that has been shared. ADR-0001 makes
   git the audit trail, and an audit trail you can edit is not one.
5. **Originals are never modified**, including by a commit that
   "fixes" one. Corrections are new files with new INDEX rows.
6. **Drafting history goes here.** The conventions forbid "corrected
   from the prior draft" inside a pleading. That reasoning still has
   to live somewhere, and this is the somewhere. The stricter the rule
   inside `src/`, the more the commit message has to carry.

### When to commit

Commit at the natural seams of the work, not at the end of a session:

| After | Commit |
|---|---|
| a connector pull lands files | `intake` |
| a document is triaged into `assets/` **and INDEX.md updated** | `triage` — same commit, never separately |
| a draft reaches a coherent state | `draft` |
| an envelope is rebuilt | `build`, separate from the `draft` that caused it |
| a filed or received document is added | `docket` |
| KNOWLEDGE/TODO absorb what was learned | `record` |

Do **not** accumulate a large working tree "for human review." Seven
typed commits are a far better review surface than a thirty-file dirty
tree: they group related changes, carry the reasoning, and survive.
Flag rather than withhold — `Drafted-by: agent` and
`Verified: machine — unverified` make the caution greppable.

The one thing that does wait: a change the user has not authorized
under the change-authority rules. Leave that staged or unstaged and
say so.

## Enforcement

`sc commit-check [file]` validates a message. `sc hooks <matter>`
installs a `commit-msg` hook that runs it, and `sc init` does that for
new matters automatically.

Errors — an unknown or missing type — fail the commit; they cost one
word to fix. Missing footers and overlong subjects **warn and let the
commit through**: the moment you are committing during a filing is not
the moment to be argued with by a hook. `--no-verify` bypasses it
entirely.
