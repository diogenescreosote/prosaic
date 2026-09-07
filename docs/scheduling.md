# Scheduling (macOS)

`sc schedule <matter_dir>` installs a launchd agent that syncs the
matter every 12 hours. This page documents the semantics and — more
importantly — the macOS traps that will otherwise cost you an
afternoon.

## Semantics

- The agent fires at two fixed times (default 08:00 and 20:00) **and
  once at load** (login/boot).
- `matter_sync.sh --scheduled` skips any run starting less than 11
  hours after the last *fully successful* sync.

Together these give **catch-up-once** behavior: if the machine was
asleep, launchd coalesces missed calendar firings into a single run on
wake; if it was powered off, the run-at-load firing catches up at
boot; and the interval guard collapses any resulting pile-up (boot at
07:55, calendar at 08:00) into exactly one pull. Failures don't
advance the guard, so a broken source retries at the next firing
instead of waiting out the interval.

Why launchd, not cron: cron silently skips anything missed while
asleep or off, and macOS cron jobs hit the same TCC wall below with a
clumsier fix.

## The TCC / Full Disk Access wall

Background launchd jobs **cannot read protected locations** —
Desktop, Documents, Downloads, and critically `~/Library/CloudStorage`
(Google Drive, Dropbox, OneDrive folders), where matter directories
often live. The failure is maddening: `stat` works, reads fail with
`Operation not permitted` (or Node's `MODULE_NOT_FOUND`), and nothing
prompts.

Facts that shape the fix:

- TCC grants attach to a **binary**. Shell scripts are attributed to
  their interpreter, so you'd have to grant `/bin/bash` — far too
  broad.
- You cannot copy a platform binary to grant the copy: macOS **kills
  copied system binaries** (SIGKILL at exec).
- Grants cover **child processes** via responsible-process
  attribution (this is why granting `cron` FDA covers cron jobs).

So prosaic ships a ~40-line C shim (`sync/runner_shim.c`).
`sc schedule` compiles it to `~/.local/bin/prosaic-runner` and
makes it the launchd program; it just spawns `/bin/bash` on
`matter_sync.sh` and waits. **One-time manual step:** System Settings
→ Privacy & Security → Full Disk Access → “+” → ⌘⇧G →
`~/.local/bin/prosaic-runner`. That single grant covers bash, node,
and the AI harness underneath.

Until the grant exists, scheduled runs fail gracefully and log;
manual `sc sync` from your terminal works regardless (your terminal
app's grants apply).

## Other gotchas

- **Cloud-synced matter dirs may be unmounted** at fire time (login
  races, network). The sync checks reachability first and exits 0
  with a `SKIP` log line — no error spam, next firing works.
- **PATH is minimal under launchd.** The sync script sets its own
  (Homebrew, `~/.local/bin`, system paths); if your tools live
  elsewhere, edit the `export PATH` line.
- **Keychain access** works in scheduled runs as long as the login
  keychain is unlocked (i.e., you're logged in). A locked-screen
  machine still syncs; a logged-out one doesn't.
- **Don't put the Puppeteer profiles in the cloud folder.** Session
  cookies in a synced directory are both a privacy smell and a
  corruption risk; prosaic keeps them in
  `~/.local/share/prosaic/portal-profiles/`.
- **Logs** land in `~/Library/Logs/prosaic/` (`sync-<matter>.log`
  for the pipeline, `launchd-<matter>.log` for raw stdout/stderr,
  `debug/` for portal failure snapshots). Check `SKIP`/`ERROR` lines
  there first.

## Linux

Nothing in the sync script is macOS-specific except the Keychain
(swap `security` for `secret-tool` in
`connectors/core/portal_common.js`) and the installer. Use a systemd
user timer with `Persistent=true` for equivalent catch-up-once
semantics; contributions welcome.

## The standby supervisor (ADR-0044)

`sc schedule <matter>` installs one agent, `com.prosaic.supervisor.<matter>`,
through the Full Disk Access shim. It fires on any change under `inbox/`
(throttle 60 s), at 08:00 and 20:00, at 02:30, at 08:50
(`PROSAIC_STANDUP_TIME`), and at load, and runs
`sync/matter_supervisor.sh`, which does only what is due:

| Piece | When it actually runs |
|---|---|
| inbox triage (`matter_sync.sh --watch`) | files under `inbox/` that landed and have not changed for 20 s and were not already listed |
| connector sync + triage (`matter_sync.sh --scheduled`) | when the 11-hour guard says so |
| `sc refine --scheduled` | once a day after 02:30 (`PROSAIC_REFINE_AFTER`) |
| `sc standup agenda --notify` | once a day after the standup time |

One job means one background item in System Settings per matter. Earlier
per-task agents and the legacy `com.slopcannon.sync.<matter>` agent are
unloaded and removed on install. If `~/.local/bin/gmail-pull-runner`
already holds the FDA grant and no `prosaic-runner` exists, the installer
keeps using it.

Every sync or watch run writes `.state/sync_last_run.json` (mode,
outcome, new files, triage result, per-connector status); `sc brief`
and the standup agenda read it.

Headless jobs run under a role: triage as `agent-run --role triage`,
refinement as `--role refine`. A role's model and turn cap come from the
matter's `matter.yaml`:

```yaml
agent:
  roles:
    triage: {max_turns: 80}
    refine: {max_turns: 40}
    judge:  {model: claude-sonnet-5, max_turns: 20}
```

Unset means the harness default, uncapped.
