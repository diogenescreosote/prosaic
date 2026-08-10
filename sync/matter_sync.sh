#!/bin/bash
#
# matter_sync.sh <matter_dir> [--scheduled]
#
# Unified per-matter evidence sync. Runs every connector configured for
# the matter (matter.yaml `connectors:` — legacy envelopes.yaml keys
# also honored), then one headless AI triage pass over everything new.
#
# Scheduling contract (see docs/scheduling.md):
#   - launchd fires this every 12h and once at load (boot/login)
#   - scheduled runs (--scheduled) are skipped if the last fully
#     successful sync was under MIN_INTERVAL_HOURS ago, so firings
#     missed while the machine was off/asleep collapse to ONE catch-up
#   - manual runs bypass the guard
#
# Connector contract (see docs/connectors.md): each connector is
# connectors/<name>/pull.js, invoked with the matter dir, printing
# "NEW <absolute path>" per new file on stdout, logging to stderr,
# exiting nonzero on failure. The guard state only advances when every
# configured connector succeeded, so failures retry at the next firing.

set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# The interpreter that parses matter.yaml must have PyYAML. The PATH
# above is deliberately minimal for launchd, and its python3 often
# lacks it, so probe candidates and fail loudly rather than silently
# resolving zero connectors. Override with PROSAIC_PYTHON.
sc_python() {
  local c
  for c in "${PROSAIC_PYTHON:-}" python3 \
           "$HOME/miniforge3/bin/python3" "$HOME/miniconda3/bin/python3" \
           "$HOME/.local/bin/python3" \
           /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -n "$c" ] || continue
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c "import yaml" >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  return 1
}

MATTER_DIR="${1:?usage: matter_sync.sh <matter_dir> [--scheduled]}"
SCHEDULED=0
[ "${2:-}" = "--scheduled" ] && SCHEDULED=1

# Repo root: resolve through symlinks so an installed copy still finds home.
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do SOURCE="$(readlink "$SOURCE")"; done
PROSAIC_ROOT="${PROSAIC_ROOT:-$(cd "$(dirname "$SOURCE")/.." && pwd)}"
CONNECTORS_DIR="$PROSAIC_ROOT/connectors"

. "$PROSAIC_ROOT/sync/lib.sh"

MATTER_NAME="$(basename "$MATTER_DIR")"
# Resolve once, then export: every connector this script spawns
# inherits the answer instead of resolving it again.
LOG_ROOT="$(sc_log_root)"
export PROSAIC_LOG_DIR="$LOG_ROOT"
LOG_FILE="$LOG_ROOT/sync-$MATTER_NAME.log"
STATE_DIR="$MATTER_DIR/.state"
GUARD_FILE="$STATE_DIR/sync_last_success"
LOCK_DIR="${TMPDIR:-/tmp}/prosaic_sync_${MATTER_NAME}.lock"
MIN_INTERVAL_HOURS="${PROSAIC_MIN_INTERVAL_HOURS:-11}"

mkdir -p "$LOG_ROOT"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

# --- sanity: matter reachable (cloud-synced volume may be unmounted) ---------
if [ ! -f "$MATTER_DIR/matter.yaml" ] && [ ! -f "$MATTER_DIR/envelopes.yaml" ]; then
  log "SKIP: no matter.yaml/envelopes.yaml at $MATTER_DIR (volume unmounted?)"
  exit 0
fi
mkdir -p "$STATE_DIR"

# --- min-interval guard (scheduled runs only) ---------------------------------
if [ "$SCHEDULED" = 1 ] && [ -f "$GUARD_FILE" ]; then
  last=$(cat "$GUARD_FILE" 2>/dev/null || echo 0)
  elapsed_h=$(( ($(date +%s) - last) / 3600 ))
  if [ "$elapsed_h" -lt "$MIN_INTERVAL_HOURS" ]; then
    log "SKIP: last successful sync ${elapsed_h}h ago (< ${MIN_INTERVAL_HOURS}h guard)"
    exit 0
  fi
fi

# --- lock (stale after 3h) -----------------------------------------------------
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if [ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +180 2>/dev/null)" ]; then
    log "WARN: removing stale lock $LOCK_DIR"
    rm -rf "$LOCK_DIR"; mkdir "$LOCK_DIR" || { log "ERROR: cannot acquire lock"; exit 1; }
  else
    log "SKIP: another sync is running (lock held)"
    exit 0
  fi
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

# --- which connectors are configured? ------------------------------------------
configured_connectors() {
  "$SC_PY" - "$MATTER_DIR" <<'PY'
import sys, os, yaml
matter = sys.argv[1]
names = []
def load(p):
    try:
        with open(p) as f: return yaml.safe_load(f) or {}
    except FileNotFoundError: return {}
m = load(os.path.join(matter, 'matter.yaml'))
names += list((m.get('connectors') or {}).keys())
legacy = load(os.path.join(matter, 'envelopes.yaml'))
if 'gmail' not in names and legacy.get('gmail_addresses'): names.append('gmail')
for k in ('mycase',):
    if k not in names and legacy.get(k): names.append(k)
print('\n'.join(names))
PY
}

NEW_LIST=$(mktemp)
FAILURES=0

SC_PY="$(sc_python)" || {
  log "ERROR: no python3 with PyYAML found (tried PROSAIC_PYTHON, PATH, common locations)."
  log "       Cannot read connector config; NOT advancing the success guard."
  exit 1
}

CONNECTORS="$(configured_connectors)"
# A matter that declares connectors but resolves none means the config
# could not be parsed — never let that look like a clean, empty sync.
if [ -z "$CONNECTORS" ] && grep -qE '^(connectors|gmail_addresses|mycase):' \
     "$MATTER_DIR/matter.yaml" "$MATTER_DIR/envelopes.yaml" 2>/dev/null; then
  log "ERROR: matter declares connectors but none resolved (config parse failure?)."
  log "       NOT advancing the success guard."
  exit 1
fi

for name in $CONNECTORS; do
  entry="$CONNECTORS_DIR/$name/pull.js"
  if [ ! -f "$entry" ]; then
    log "WARN: connector '$name' configured but $entry not found"
    continue
  fi
  log "CONNECTOR $name start"
  if NODE_PATH="$CONNECTORS_DIR/node_modules" node "$entry" "$MATTER_DIR" 2>> "$LOG_FILE" \
      | sed -n "s/^NEW /$name /p" >> "$NEW_LIST"; then
    log "CONNECTOR $name ok"
  else
    log "ERROR: connector $name failed"
    FAILURES=$((FAILURES+1))
  fi
done

[ "$FAILURES" = 0 ] && date +%s > "$GUARD_FILE"

if [ ! -s "$NEW_LIST" ]; then
  log "SYNC done: nothing new (failures=$FAILURES)"
  rm -f "$NEW_LIST"; exit 0
fi
count=$(wc -l < "$NEW_LIST" | tr -d ' ')
log "SYNC done: $count new file(s) (failures=$FAILURES):"
sed 's/^/    /' "$NEW_LIST" >> "$LOG_FILE"

# --- headless AI triage ----------------------------------------------------------
if ! command -v claude >/dev/null 2>&1; then
  log "WARN: claude CLI not found; skipping knowledge triage"
  rm -f "$NEW_LIST"; exit 0
fi
PROMPT_TEMPLATE="$PROSAIC_ROOT/triage/prompts/sync_triage.md"
if [ ! -f "$PROMPT_TEMPLATE" ]; then
  log "WARN: triage prompt template missing; skipping triage"
  rm -f "$NEW_LIST"; exit 0
fi
PROMPT="$(cat "$PROMPT_TEMPLATE")

NEW FILES (one per line: <connector> <absolute path>):

$(cat "$NEW_LIST")"

log "TRIAGE start ($count files)"
if ( cd "$MATTER_DIR" && claude -p "$PROMPT" --dangerously-skip-permissions ) >> "$LOG_FILE" 2>&1; then
  log "TRIAGE done"
else
  log "ERROR: triage failed (new files remain in place)"
fi
rm -f "$NEW_LIST"
