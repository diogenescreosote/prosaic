# 0004 — launchd + compiled FDA shim for scheduling on macOS

**Status:** accepted (2026-08)

## Context
Syncs must run unattended every 12h with catch-up-once semantics after
sleep/shutdown. macOS TCC blocks background jobs from reading
~/Library/CloudStorage (where matters often live); grants attach to
binaries; scripts are attributed to their interpreter; copied system
binaries are killed by the OS (verified empirically, painfully).

## Decision
launchd (StartCalendarInterval ×2 + RunAtLoad) fires a ~40-line
locally compiled C shim that spawns bash on the sync script; the user
grants Full Disk Access to the shim once, and responsible-process
attribution extends the grant to all children. An 11-hour guard in the
script collapses pile-ups to one run.

## Consequences
True catch-up-once (cron silently skips missed runs and needs the same
TCC surgery with worse ergonomics); one narrow, inspectable grant
instead of blessing /bin/bash. Cost: a compile step and a one-time
manual Settings visit, both documented and automated by the installer.
