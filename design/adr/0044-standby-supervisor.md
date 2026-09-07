# ADR-0044: A standby supervisor per matter

**Status:** Accepted (September 7, 2026)

## Context

Material reached a matter twice a day, when launchd fired the sync; a
file dropped into `inbox/` by hand waited up to twelve hours. Knowledge
was refined only when a human or an agent happened to open the file.
Connector failures were logged as success for weeks. Stale output
accumulated with no notion of age. The human's daily contact with the
system was whatever session they opened, with no agenda.

The pieces existed: launchd and the FDA shim (ADR-0004), the sync script,
the agent seam (ADR-0020), the coverage pass (ADR-0041), the vault
(ADR-0043). What was missing was a supervisor that keeps them running on
their own and puts one thirty-minute human loop on top.

## Decision

1. **One launchd agent per matter**, `com.prosaic.supervisor.<matter>`,
   installed by `sc schedule`. It fires on any change under `inbox/`
   (throttled to one run a minute), at the two sync times, at 02:30, at
   the standup time (08:50 by default), and at load, and runs
   `sync/matter_supervisor.sh`, which decides what is due: inbox triage
   of files that landed and stopped changing (`matter_sync.sh --watch`,
   no connectors); the guarded connector sync; `sc refine --scheduled`
   once a day after 02:30; `sc standup agenda --notify` once a day after
   the standup time. One job means one background item in System
   Settings rather than one per task, which an earlier layout produced.
   Earlier per-task agents and the legacy `com.slopcannon.sync` label
   are unloaded and removed on install.
2. **Every run writes a summary.** `matter_sync.sh` records mode,
   outcome, new-file count, triage result and per-connector status in
   `.state/sync_last_run.json`; the brief and the agenda read it, so a
   failed connector is seen the next morning.
3. **Roles route models.** `agent-run --role NAME` reads
   `agent.roles.NAME` in the matter's `matter.yaml` for a model and a
   turn cap and passes them to the harness. Triage runs as `triage`,
   refinement as `refine`, the test judge as `judge`. Unset means the
   harness default; triage and refine stay on the strongest model.
4. **Refinement proposes and never edits.** `sc refine` gathers inputs
   deterministically (commits and changed files since the last pass,
   vault lint, notes citing changed documents, stale notes, coverage
   gaps, the last sync, open questions), then one agent pass writes
   `derived/refine/<date>.md`: proposed edits with sources,
   contradictions, questions, housekeeping. Any file the agent touched
   outside that directory is reported, not reverted.
5. **The standup is where knowledge changes.** `sc standup agenda`
   writes `derived/standup/<date>.md` from the brief, the sync summary,
   the latest proposal, QUESTIONS.md and the vault's state, and posts a
   notification. The `/standup` command walks the human through it for
   thirty minutes; answers land in notes as `verified: human`, decided
   proposals are applied or declined with a reason, and the session
   ends in a `record(standup)` commit.
6. **Age-based retention is a report first.** `sc clean --older-than N`
   lists files older than N days under `out/`, `.flow/` and
   `derived/{find,refine,standup}`, tracked and untracked separately;
   `--apply` deletes only those. Nothing under `assets/`, `pleadings/`,
   `discovery/`, `processed_files/` or `derived/text/` is ever a
   candidate.

## Consequences

- A document is triaged within about a minute of landing, by the
  strongest model, with the read-every-page discipline, and appears in
  the coverage audit before anyone searches for it.
- The human's daily obligation is bounded and scheduled: one agenda,
  one command, thirty minutes. Knowledge changes only there or in
  triage, never unattended overnight.
- Failures surface where the human looks: the brief and the agenda,
  not a log.
- One launchd agent per matter; the legacy label is retired. The Full
  Disk Access grant is per binary and the installer reuses a legacy shim
  that already holds it rather than installing an ungranted one.
- Model routing lives in matter configuration, not in prosaic; the
  same deployment can run triage on one vendor and the judge on
  another, which is the precondition for W5.
- `matter_sync.sh` remains the least-tested surface; the watch mode
  adds a smoke test, not coverage.
