#!/bin/bash
#
# matter_supervisor.sh <matter_dir>
#
# The one launchd entry point per matter (ADR-0044). launchd fires it on
# a change under inbox/, at the calendar times, and at load; it decides
# what is due and runs only that:
#
#   watch    files under inbox/ that landed and stopped changing -> triage
#   sync     connectors + triage, when the interval guard says it is due
#   refine   once a day after PROSAIC_REFINE_AFTER (02:30) -> derived/refine/<date>.md
#   standup  once a day after PROSAIC_STANDUP_TIME (08:50) -> agenda + notification
#
# One job, one background item in System Settings, one log. Each piece
# is idempotent, so a firing that finds nothing due exits quietly.
# PROSAIC_NOW=HH:MM overrides the clock for tests.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
MATTER_DIR="${1:?usage: matter_supervisor.sh <matter_dir>}"
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do SOURCE="$(readlink "$SOURCE")"; done
PROSAIC_ROOT="${PROSAIC_ROOT:-$(cd "$(dirname "$SOURCE")/.." && pwd)}"
export PROSAIC_ROOT
SC="$PROSAIC_ROOT/cli/sc"
SYNC="$PROSAIC_ROOT/sync/matter_sync.sh"
. "$PROSAIC_ROOT/sync/lib.sh"
LOG_ROOT="$(sc_log_root)"; mkdir -p "$LOG_ROOT"
LOG_FILE="$LOG_ROOT/sync-$(basename "$MATTER_DIR").log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] SUPERVISOR $*" >> "$LOG_FILE"; }

[ -f "$MATTER_DIR/matter.yaml" ] || { log "SKIP: no matter.yaml (volume unmounted?)"; exit 0; }
NOW="${PROSAIC_NOW:-$(date +%H:%M)}"
TODAY="$(date +%Y-%m-%d)"
REFINE_AFTER="${PROSAIC_REFINE_AFTER:-02:30}"
STANDUP_AT="${PROSAIC_STANDUP_TIME:-08:50}"
# 10# forces decimal: "0900" would otherwise be read as octal and fail.
after() { [ "$((10#${NOW//:/}))" -ge "$((10#${1//:/}))" ]; }

# 1. inbox: always look; the script itself exits fast when nothing settled
/bin/bash "$SYNC" "$MATTER_DIR" --watch

# 2. sync: the guard inside decides (11 h since the last full success)
/bin/bash "$SYNC" "$MATTER_DIR" --scheduled

# 3. refine: once a day, after the configured hour
if after "$REFINE_AFTER" && [ ! -f "$MATTER_DIR/derived/refine/$TODAY.md" ]; then
  log "refine start"
  if "$SC" refine "$MATTER_DIR" --scheduled >> "$LOG_FILE" 2>&1; then log "refine done"; else log "refine FAILED"; fi
fi

# 4. standup agenda: once a day, after the configured time
if after "$STANDUP_AT" && [ ! -f "$MATTER_DIR/derived/standup/$TODAY.md" ]; then
  log "standup agenda"
  "$SC" standup agenda "$MATTER_DIR" --notify >> "$LOG_FILE" 2>&1 || log "standup agenda FAILED"
fi
exit 0
