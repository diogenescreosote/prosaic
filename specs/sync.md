# Spec: scheduled sync

## Purpose

Evidence should accumulate while nobody is thinking about the case.
Scheduled sync runs every configured connector for a matter and then
one AI triage pass over whatever arrived, on a cadence a human never
has to remember — so that opening the matter after a week away means
reading a current record, not running a checklist. The scheduler's
own promises are about *never silently stopping*: the failure modes
that matter are the quiet ones (asleep at fire time, unmounted
volume, expired session) where a naive scheduler just stops
collecting evidence and nobody notices until a filing deadline.

## Promises

1. **Twelve-hour cadence.** The matter syncs twice a day at fixed
   times, plus once at boot/login. *(untested)*
2. **Catch-up once, not zero and not many.** Firings missed while
   the machine was asleep or off collapse into exactly one catch-up
   run on wake/boot: an interval guard skips any scheduled run
   starting less than 11 hours after the last *fully successful*
   sync, so a boot-time firing and a calendar firing minutes apart
   produce one pull. *(untested)*
3. **Failure holds the guard, so nothing is skipped forever.** The
   guard timestamp advances only when *every* configured connector
   succeeded. One broken source means the next firing retries the
   whole sync instead of waiting out the interval — a failing
   connector can never push its own retry into next week.
   *(untested)*
4. **No overlapping runs.** A lock ensures two syncs of the same
   matter never interleave (and a stale lock from a crashed run is
   reclaimed after a timeout rather than wedging the schedule
   permanently). *(untested)*
5. **Graceful degradation.** An unmounted cloud volume at fire time
   is a logged `SKIP` and exit 0 — no error spam, and the next
   firing works. Dead portal credentials or an expired session fail
   that connector loudly (holding the guard) without taking down the
   other connectors' pulls. Manual runs work regardless of the
   scheduler's state. *(untested)*
6. **Everything is logged where a human will look**: one pipeline
   log per matter, raw stdout/stderr from the scheduler, and portal
   failure snapshots, all under one log directory. `SKIP`/`ERROR`
   lines are the first diagnostic. *(untested)*

## Non-obvious constraints

- **launchd, not cron, on macOS** — cron silently discards firings
  missed while asleep, which is the exact quiet-stop failure this
  component exists to prevent.
- **The TCC wall is real**: background jobs cannot read Desktop,
  Documents, or cloud-synced folders (where matters live) without a
  Full Disk Access grant, and the failure mode is misleading
  (`Operation not permitted` on read, no prompt). Grants attach to
  binaries and cover child processes, so prosaic ships a tiny
  compiled runner to be the *one* thing the user grants — granting
  `/bin/bash` instead would be absurdly broad. Until the grant
  exists, scheduled runs fail gracefully and log; they must never
  half-work.
- **The scheduled environment is hostile by default** — minimal
  PATH, possibly locked keychain, possibly absent network. The sync
  owns its own PATH; keychain access requires a logged-in user (a
  locked screen is fine, a logged-out machine is not).
- **The 11-hour guard is deliberately less than the 12-hour
  cadence**, absorbing clock drift and slow runs so a healthy
  schedule never self-skips.
- **Manual sync bypasses the guard** — a human asking for a sync
  now means now.
