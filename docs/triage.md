# AI triage

After each sync, one headless [Claude Code](https://claude.com/claude-code)
session folds everything new into the matter: catalog rows for email
threads, knowledge updates from message reports, routing for staged
portal documents. This page explains the design and its guardrails.

## How it runs

`sync/matter_sync.sh` collects the `NEW <path>` lines from every
connector, then runs:

```bash
cd <matter_dir> && claude -p "<prompt>" --dangerously-skip-permissions
```

- The prompt is `triage/prompts/sync_triage.md` plus the file list.
  Edit the template to tune behavior; it's plain Markdown.
- Running *inside the matter directory* means Claude Code picks up the
  matter's `CLAUDE.md` automatically — the agent contract (index
  discipline, originals-are-sacred, em-dash rules, NOTREAL, "you are a
  clerk, not a lawyer") applies to every triage session without being
  repeated in the prompt.
- `--dangerously-skip-permissions` is what makes unattended operation
  possible: there is no human present to approve each edit. The risk
  is bounded by the prompt's scope rules, the matter contract, and the
  fact that the matter is (ideally) a git repository — every triage
  session's changes are diffable and revertable.

## Design principles

**Conservative by instruction.** The prompt's standing order: when
significance or routing is unclear, *leave the file where it is*, mark
it "needs human review" in the catalog/index, and move on. A triage
pass that does less is recoverable; one that guesses wrong and moves
records around confidently is expensive.

**Small increments.** The 12-hour cadence means a typical triage sees
a handful of files. Initial bulk imports (hundreds of historical
threads/documents) should NOT go through the headless pass — do those
interactively, with mechanically generated backfill indexes and a
human (or supervised agent) deciding cataloging depth.

**Everything it does is legible.** Catalog rows, index rows, and
KNOWLEDGE.md diffs are ordinary text changes in git. The sync log
(`~/Library/Logs/prosaic/sync-<matter>.log`) records what ran and
what it was given.

**Privilege awareness.** The prompt requires marking attorney-client
threads PRIVILEGED in catalogs. This is a labeling convention for the
humans working the file — it is not access control, and nothing in
prosaic transmits matter content anywhere except to the AI harness
you configured.

**Hard limits.** The triage agent never files, serves, sends, or
signs anything; never edits pleading sources during triage; and never
deletes anything except a staged duplicate whose content-identical
twin is already in place.

## Tuning

- Per-connector handling lives in `triage/prompts/sync_triage.md`.
- Matter-wide behavior lives in the matter's `CLAUDE.md`.
- If you add a connector whose output needs special handling, add a
  section to the prompt template; otherwise the generic
  "treat as inbox material" clause covers it.

## Using other harnesses

The seam is narrow by design: the orchestrator shells out to one CLI
with one prompt and a working directory. Any agent harness that can
(a) run headless with file-editing tools scoped to a directory and
(b) honor an instruction file in that directory could be substituted
by editing the `TRIAGE` block of `sync/matter_sync.sh`. Claude Code is
what this system is tested with.
