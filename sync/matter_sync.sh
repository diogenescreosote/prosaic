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

MATTER_DIR="${1:?usage: matter_sync.sh <matter_dir> [--scheduled|--watch]}"
SCHEDULED=0
WATCH=0
case "${2:-}" in
  --scheduled) SCHEDULED=1 ;;
  --watch)     WATCH=1 ;;   # inbox watcher: no connectors, triage what landed (ADR-0044)
esac
RUN_STARTED="$(date +%s)"
RUN_MODE="manual"; [ "$SCHEDULED" = 1 ] && RUN_MODE="scheduled"; [ "$WATCH" = 1 ] && RUN_MODE="watch"

# Repo root: resolve through symlinks so an installed copy still finds home.
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do SOURCE="$(readlink "$SOURCE")"; done
PROSAIC_ROOT="${PROSAIC_ROOT:-$(cd "$(dirname "$SOURCE")/.." && pwd)}"
CONNECTORS_DIR="$PROSAIC_ROOT/connectors"
# Local modules (ADR-0032): a gitignored local/ overlay may carry extra
# connectors; the local copy wins when a name exists in both.
LOCAL_CONNECTORS_DIR="$PROSAIC_ROOT/local/connectors"

# Resolve a connector name to its pull.js, local overlay first.
connector_entry() {
  if [ -f "$LOCAL_CONNECTORS_DIR/$1/pull.js" ]; then
    echo "$LOCAL_CONNECTORS_DIR/$1/pull.js"
  elif [ -f "$CONNECTORS_DIR/$1/pull.js" ]; then
    echo "$CONNECTORS_DIR/$1/pull.js"
  fi
}

# Every installed connector name, both trees, for the legacy-key scan.
installed_connectors() {
  for d in "$CONNECTORS_DIR" "$LOCAL_CONNECTORS_DIR"; do
    [ -d "$d" ] || continue
    for e in "$d"/*/pull.js; do
      [ -f "$e" ] && basename "$(dirname "$e")"
    done
  done | sort -u
}

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
# One JSON document per run in .state/sync_last_run.json: what the brief
# and the standup agenda read, so a failed connector is seen the next
# morning rather than found in a log weeks later.
CONNECTOR_STATUS=""
write_summary() {   # $1 = outcome word, $2 = new-file count, $3 = triage status
  mkdir -p "$STATE_DIR"
  local py; py="$(sc_python 2>/dev/null || echo python3)"
  "$py" - "$STATE_DIR/sync_last_run.json" "$RUN_MODE" "$RUN_STARTED" "$1" "$2" "$3" "$CONNECTOR_STATUS" <<'PY' 2>/dev/null || true
import json, sys, time
path, mode, started, outcome, new, triage, conns = sys.argv[1:8]
status = {}
for item in conns.split():
    name, _, st = item.partition("=")
    status[name] = st
json.dump({"mode": mode, "started": int(started), "finished": int(time.time()),
           "outcome": outcome, "new_files": int(new or 0), "triage": triage,
           "connectors": status,
           "failed_connectors": sorted(n for n, st in status.items() if st != "ok")},
          open(path, "w"), indent=1)
PY
}

# --- sanity: matter reachable (cloud-synced volume may be unmounted) ---------
if [ ! -f "$MATTER_DIR/matter.yaml" ] && [ ! -f "$MATTER_DIR/envelopes.yaml" ]; then
  log "SKIP: no matter.yaml/envelopes.yaml at $MATTER_DIR (volume unmounted?)"
  exit 0
fi
mkdir -p "$STATE_DIR"

# --- inbox watcher (--watch): triage what landed, no connectors ---------------
# launchd fires this on any change under inbox/ (WatchPaths). A file still
# being written is skipped until a later firing sees it settled; a file the
# watcher already listed is not re-triaged unless its size or mtime changed.
if [ "$WATCH" = 1 ]; then
  WATCH_SEEN="$STATE_DIR/watch_seen.txt"; touch "$WATCH_SEEN"
  NEW_LIST="$(mktemp)"
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in .*) continue ;; esac
    if [ -n "$(find "$f" -newermt '-20 seconds' 2>/dev/null)" ]; then continue; fi   # still being written
    sig="$(stat -f '%z:%m' "$f" 2>/dev/null || stat -c '%s:%Y' "$f")"
    if grep -qxF "$f|$sig" "$WATCH_SEEN"; then continue; fi
    echo "$f|$sig" >> "$WATCH_SEEN"
    echo "inbox $f" >> "$NEW_LIST"
  done < <(find "$MATTER_DIR/inbox" -type f 2>/dev/null | sort)
  if [ ! -s "$NEW_LIST" ]; then
    log "WATCH: nothing new and settled under inbox/"
    rm -f "$NEW_LIST"; exit 0
  fi
fi

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
  "$SC_PY" - "$MATTER_DIR" $(installed_connectors) <<'PY'
import sys, os, yaml
matter = sys.argv[1]
installed = sys.argv[2:]  # every connector shipped in-repo or in local/
names = []
def load(p):
    try:
        with open(p) as f: return yaml.safe_load(f) or {}
    except FileNotFoundError: return {}
m = load(os.path.join(matter, 'matter.yaml'))
names += list((m.get('connectors') or {}).keys())
legacy = load(os.path.join(matter, 'envelopes.yaml'))
if 'gmail' not in names and legacy.get('gmail_addresses'): names.append('gmail')
for k in installed:
    if k not in names and legacy.get(k): names.append(k)
print('\n'.join(names))
PY
}

[ "$WATCH" = 1 ] || NEW_LIST=$(mktemp)
FAILURES=0

SC_PY="$(sc_python)" || {
  log "ERROR: no python3 with PyYAML found (tried PROSAIC_PYTHON, PATH, common locations)."
  log "       Cannot read connector config; NOT advancing the success guard."
  exit 1
}

CONNECTORS="$(configured_connectors)"
# A matter that declares connectors but resolves none means the config
# could not be parsed — never let that look like a clean, empty sync.
LEGACY_KEYS="$(installed_connectors | tr '\n' '|' | sed 's/|$//')"
if [ -z "$CONNECTORS" ] && grep -qE "^(connectors|gmail_addresses${LEGACY_KEYS:+|$LEGACY_KEYS}):" \
     "$MATTER_DIR/matter.yaml" "$MATTER_DIR/envelopes.yaml" 2>/dev/null; then
  log "ERROR: matter declares connectors but none resolved (config parse failure?)."
  log "       NOT advancing the success guard."
  exit 1
fi

[ "$WATCH" = 1 ] && CONNECTORS=""
for name in $CONNECTORS; do
  entry="$(connector_entry "$name")"
  if [ -z "$entry" ]; then
    log "WARN: connector '$name' configured but no pull.js found in $CONNECTORS_DIR or $LOCAL_CONNECTORS_DIR"
    continue
  fi
  log "CONNECTOR $name start"
  # The pipe's status is sed's, not node's, so a crashed connector used
  # to log `ok` and advance the success guard. Test node's status.
  NODE_PATH="$CONNECTORS_DIR/node_modules" node "$entry" "$MATTER_DIR" 2>> "$LOG_FILE" \
      | sed -n "s/^NEW /$name /p" >> "$NEW_LIST"
  if [ "${PIPESTATUS[0]}" = 0 ]; then
    log "CONNECTOR $name ok"
    CONNECTOR_STATUS="$CONNECTOR_STATUS $name=ok"
  else
    log "ERROR: connector $name failed (exit ${PIPESTATUS[0]})"
    CONNECTOR_STATUS="$CONNECTOR_STATUS $name=failed"
    FAILURES=$((FAILURES+1))
  fi
done

# --- text coverage -----------------------------------------------------------
# Every document the matter holds gets a page-marked text sidecar (and an
# _ocr sibling where pages lack text) before any agent reads or searches.
# Deterministic, cached, and never dependent on a model remembering to.
log "TEXT ensure start"
if "$PROSAIC_ROOT/cli/sc" text ensure "$MATTER_DIR" --jobs 2 > "$STATE_DIR/text_ensure_last.txt" 2>> "$LOG_FILE"; then
  log "TEXT ensure ok: $(head -1 "$STATE_DIR/text_ensure_last.txt")"
else
  log "TEXT ensure: gaps remain: $(head -1 "$STATE_DIR/text_ensure_last.txt")"
fi

[ "$FAILURES" = 0 ] && [ "$WATCH" = 0 ] && date +%s > "$GUARD_FILE"

if [ ! -s "$NEW_LIST" ]; then
  log "SYNC done: nothing new (failures=$FAILURES)"
  write_summary "$([ "$FAILURES" = 0 ] && echo ok || echo connector-failures)" 0 skipped
  rm -f "$NEW_LIST"; exit 0
fi
count=$(wc -l < "$NEW_LIST" | tr -d ' ')
log "SYNC done: $count new file(s) (failures=$FAILURES):"
sed 's/^/    /' "$NEW_LIST" >> "$LOG_FILE"

# --- headless AI triage ----------------------------------------------------------
# The agent CLI is whatever cli/agent-run finds (claude, codex,
# gemini, or PROSAIC_AGENT_CMD) — see ADR-0020 for the seam.
AGENT_RUN="$PROSAIC_ROOT/cli/agent-run"
if ! "$AGENT_RUN" --check >/dev/null 2>&1; then
  log "WARN: no agent CLI found (claude/codex/gemini, or PROSAIC_AGENT_CMD); skipping knowledge triage"
  write_summary "no-agent" "$count" skipped
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

log "TRIAGE start ($count files, role triage)"
if ( cd "$MATTER_DIR" && printf '%s' "$PROMPT" | "$AGENT_RUN" --yolo --role triage ) >> "$LOG_FILE" 2>&1; then
  log "TRIAGE done"
  write_summary "$([ "$FAILURES" = 0 ] && echo ok || echo connector-failures)" "$count" ok
else
  log "ERROR: triage failed (new files remain in place)"
  write_summary "triage-failed" "$count" failed
fi
rm -f "$NEW_LIST"
