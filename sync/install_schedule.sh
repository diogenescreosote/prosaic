#!/bin/bash
#
# install_schedule.sh <matter_dir> [HH:MM HH:MM]
#
# Installs the standby supervisor for a matter (macOS launchd, ADR-0044).
# Idempotent — re-run after moving the repo or matter.
#
# What it does:
#   1. compiles sync/runner_shim.c to ~/.local/bin/prosaic-runner
#      (the binary you grant Full Disk Access to — see below); an
#      existing legacy shim that already holds the grant is reused
#   2. writes four LaunchAgents under ~/Library/LaunchAgents/:
#        com.prosaic.sync.<matter>     connectors + triage at the two given
#                                      times (default 08:00 and 20:00) and at
#                                      load; the interval guard collapses
#                                      missed firings to one catch-up run
#        com.prosaic.watch.<matter>    inbox watcher: WatchPaths on inbox/,
#                                      throttled to one run a minute; triages
#                                      what landed (matter_sync.sh --watch)
#        com.prosaic.refine.<matter>   nightly knowledge refinement at 02:30
#                                      (sc refine --scheduled): proposals and
#                                      questions only, never edits notes
#        com.prosaic.standup.<matter>  standup agenda at PROSAIC_STANDUP_TIME
#                                      (default 08:50) with a notification
#   3. unloads a legacy com.slopcannon.sync.<matter> agent if present
#   4. loads all four
#
# ONE-TIME MANUAL STEP after first install: System Settings → Privacy &
# Security → Full Disk Access → “+” → ⌘⇧G → ~/.local/bin/prosaic-runner
# Without this, scheduled runs cannot read cloud-synced or protected
# folders (they fail gracefully and log). See docs/scheduling.md.

set -euo pipefail

MATTER_DIR="$(cd "${1:?usage: install_schedule.sh <matter_dir> [HH:MM HH:MM]}" && pwd)"
T1="${2:-08:00}"; T2="${3:-20:00}"
SYNC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATTER_NAME="$(basename "$MATTER_DIR" | tr -cd 'A-Za-z0-9_-')"
LABEL="com.prosaic.sync.$MATTER_NAME"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
RUNNER="${PROSAIC_RUNNER:-$HOME/.local/bin/prosaic-runner}"
STANDUP_TIME="${PROSAIC_STANDUP_TIME:-08:50}"
SC="$(cd "$SYNC_DIR/.." && pwd)/cli/sc"
. "$SYNC_DIR/lib.sh"
LOG_ROOT="$(sc_log_root)"

# Everything below this line is launchd — plists, LaunchAgents, and the
# Full Disk Access shim, none of which have a counterpart elsewhere.
# The Linux backend is systemd timers, where `Persistent=true` gives
# catch-up-once semantics natively; it goes here as install_systemd(),
# behind this same dispatch. Refuse loudly rather than half-installing.
case "${PROSAIC_PLATFORM:-$(uname -s)}" in
  darwin | Darwin) ;;
  *)
    echo "install_schedule.sh: scheduling is implemented for macOS only." >&2
    echo "  On Linux, run matter_sync.sh from a systemd timer with" >&2
    echo "  Persistent=true, or from cron. See ROADMAP.md, Phase 1." >&2
    exit 1
    ;;
esac

mkdir -p "$HOME/.local/bin" "$LOG_ROOT" "$HOME/Library/LaunchAgents"

# Full Disk Access is granted per binary path. If a legacy shim already
# holds the grant and no prosaic-runner exists yet, keep using it rather
# than installing a binary that will fail on the cloud-synced volume until
# a human opens System Settings.
if [ -z "${PROSAIC_RUNNER:-}" ] && [ ! -x "$RUNNER" ] && [ -x "$HOME/.local/bin/gmail-pull-runner" ]; then
  RUNNER="$HOME/.local/bin/gmail-pull-runner"
  echo "Using the legacy shim $RUNNER (it already holds Full Disk Access)."
fi
if [ ! -x "$RUNNER" ] || { [ "$RUNNER" = "$HOME/.local/bin/prosaic-runner" ] && [ "$SYNC_DIR/runner_shim.c" -nt "$RUNNER" ]; }; then
  echo "Compiling runner shim -> $RUNNER"
  cc -O2 -o "$RUNNER" "$SYNC_DIR/runner_shim.c"
fi

# One plist writer for the four agents.
write_plist() {   # label file trigger-xml args...
  local label="$1" file="$2" trigger="$3"; shift 3
  {
    cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$RUNNER</string>
EOF
    local a
    for a in "$@"; do printf '    <string>%s</string>\n' "$a"; done
    cat <<EOF
  </array>
$trigger
  <key>StandardOutPath</key><string>$LOG_ROOT/launchd-$MATTER_NAME.log</string>
  <key>StandardErrorPath</key><string>$LOG_ROOT/launchd-$MATTER_NAME.log</string>
</dict>
</plist>
EOF
  } > "$file"
  plutil -lint "$file" >/dev/null
  launchctl unload "$file" 2>/dev/null || true
  launchctl load "$file"
}

# Legacy label from the pre-rename deployment: unload so two agents do not
# run the same sync.
LEGACY="$HOME/Library/LaunchAgents/com.slopcannon.sync.$MATTER_NAME.plist"
if [ -f "$LEGACY" ]; then
  launchctl unload "$LEGACY" 2>/dev/null || true
  mv "$LEGACY" "$LEGACY.disabled"
  echo "Unloaded legacy com.slopcannon.sync.$MATTER_NAME (kept as $LEGACY.disabled)."
fi

h1="${T1%%:*}"; m1="${T1##*:}"; h2="${T2%%:*}"; m2="${T2##*:}"
hs="${STANDUP_TIME%%:*}"; ms="${STANDUP_TIME##*:}"

write_plist "$LABEL" "$PLIST" "  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>$((10#$h1))</integer><key>Minute</key><integer>$((10#$m1))</integer></dict>
    <dict><key>Hour</key><integer>$((10#$h2))</integer><key>Minute</key><integer>$((10#$m2))</integer></dict>
  </array>
  <key>RunAtLoad</key><true/>" \
  "$SYNC_DIR/matter_sync.sh" "$MATTER_DIR" "--scheduled"

WATCH_PATHS="    <string>$MATTER_DIR/inbox</string>"
for sub in "$MATTER_DIR"/inbox/*/; do
  [ -d "$sub" ] && WATCH_PATHS="$WATCH_PATHS
    <string>${sub%/}</string>"
done
write_plist "com.prosaic.watch.$MATTER_NAME" "$HOME/Library/LaunchAgents/com.prosaic.watch.$MATTER_NAME.plist" "  <key>WatchPaths</key>
  <array>
$WATCH_PATHS
  </array>
  <key>ThrottleInterval</key><integer>60</integer>" \
  "$SYNC_DIR/matter_sync.sh" "$MATTER_DIR" "--watch"

write_plist "com.prosaic.refine.$MATTER_NAME" "$HOME/Library/LaunchAgents/com.prosaic.refine.$MATTER_NAME.plist" "  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>30</integer></dict>" \
  "$SC" "refine" "$MATTER_DIR" "--scheduled"

write_plist "com.prosaic.standup.$MATTER_NAME" "$HOME/Library/LaunchAgents/com.prosaic.standup.$MATTER_NAME.plist" "  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$((10#$hs))</integer><key>Minute</key><integer>$((10#$ms))</integer></dict>" \
  "$SC" "standup" "agenda" "$MATTER_DIR" "--notify"

echo "Installed and loaded: $LABEL ($T1, $T2, and at load); com.prosaic.watch.$MATTER_NAME (inbox/);"
echo "  com.prosaic.refine.$MATTER_NAME (02:30); com.prosaic.standup.$MATTER_NAME ($STANDUP_TIME)."
echo
echo "REMINDER: grant Full Disk Access to $RUNNER if you haven't"
echo "(System Settings → Privacy & Security → Full Disk Access)."
