# Getting set up

You are joining a system for running litigation matters out of plain
files: Markdown sources, a build that turns them into court-ready PDFs,
and git as the audit trail. This page gets you from nothing to a working
setup.

**You can hand this whole page to Claude Code and ask it to do the
setup.** It will read the `deploy` skill and work through the steps. Stay
with it for the two decisions only you can make — where to put the
deployment, and whether the access checks pass.

## What you need first

- **GitHub access to two private repositories.** Ask Andrew for
  `diogenescreosote/family-law-forms` and
  `diogenescreosote/slopcannon-local`. Without both, setup cannot
  complete — and it fails quietly rather than loudly, which is why this
  is first.
- **git**, **Python 3.12+**, and [**uv**](https://docs.astral.sh/uv/).
- macOS or Linux. Some system binaries get installed along the way; the
  tooling tells you which and how.

## The one irreversible choice

Pick where the deployment lives before cloning, e.g.
`~/lawyering/slopcannon`. Every matter you later create symlinks its
build into that path, so moving it afterwards breaks all of them at once.
Put matters beside it, not inside it:

```
~/lawyering/
    slopcannon/       the deployment: engine, forms, glue
    AGENTS.md         symlink -> slopcannon/local/templates/workspace/AGENTS.md
    michael/          a matter
    smith/            another matter
```

## Doing it

Tell Claude Code:

> Use the `deploy` skill to set up a prosaic deployment at
> `~/lawyering/slopcannon`, then verify it.

Or follow [`skills/deploy/SKILL.md`](skills/deploy/SKILL.md) by hand —
it is seven short steps. The reasoning behind them is in
[`docs/deploy.md`](docs/deploy.md).

**Do not skip step 6.** Every way this setup can fail, it fails silently:
a missing form module looks like a form nobody registered, and a missing
contract looks like a matter with no conventions. Step 6 proves each
layer resolved.

## Then: your matter

If the matter already exists (it has a `matter.yaml`), you are done —
`cd` into it and `make list` shows what it can build.

If you are starting one, ask Claude Code to use the `new-matter` skill.
It scaffolds the layout, git repo, commit hooks and backup remote.

## What to read next, in order

1. **`AGENTS.md`** in the workspace root — the rules every matter
   inherits. Read it before drawing conclusions from anything in a
   matter directory. It is short and it is binding.
2. **The matter's own `CLAUDE.md`** — parties, posture, quirks. Where it
   disagrees with the workspace contract, it wins for that matter.
3. [`docs/matter-layout.md`](docs/matter-layout.md) — what each
   directory is for.
4. [`skills/README.md`](skills/README.md) — the task-shaped capabilities:
   building a filing, filling a form, triaging an inbox, signing.

## Things that will save you a bad afternoon

- **Originals are sacred.** Processing adds siblings and sidecars; it
  never modifies bytes that arrived from outside.
- **`pleadings/` holds the court's copy and nothing else.** Not drafts,
  not working markups. Provenance is recorded by a human at intake and
  never inferred — two identical files prove only that they are the same
  file, not that either came from the court.
- **Never file, serve, send, or sign anything.** Draft, catalogue,
  summarise, route. The human does the acts that bind.
- **Read the build's warnings.** `sc build` warns rather than fails on
  things you need to know: an invented front-matter key that will do
  nothing forever, a spaced em dash that will print as a gap, output that
  landed in the wrong variant directory.
- **Em dashes in `src/` markdown are `text---text`**, never spaced. The
  renderer keeps the surrounding whitespace, so a space becomes a
  permanent gap in the filed PDF.

## If something does not work

Re-run step 6 of the `deploy` skill; its table maps each symptom to the
layer that did not take. The commonest by far is a submodule that was
cloned but never checked out — `git submodule update --init --recursive`
in the deployment fixes it.
