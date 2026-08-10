#!/bin/bash
#
# install_schedule.sh <matter_dir> [HH:MM HH:MM]
#
# Installs the every-12-hours background sync for a matter (macOS
# launchd). Idempotent — re-run after moving the repo or matter.
#
# What it does:
#   1. compiles sync/runner_shim.c to ~/.local/bin/prosaic-runner
#      (the binary you grant Full Disk Access to — see below)
#   2. writes ~/Library/LaunchAgents/com.prosaic.sync.<matter>.plist
#      firing at the two given times (default 08:00 and 20:00) and at
#      load; matter_sync.sh's interval guard collapses missed/duplicate
#      firings to at most one catch-up run
#   3. loads the agent
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
RUNNER="$HOME/.local/bin/prosaic-runner"
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

if [ ! -x "$RUNNER" ] || [ "$SYNC_DIR/runner_shim.c" -nt "$RUNNER" ]; then
  echo "Compiling runner shim -> $RUNNER"
  cc -O2 -o "$RUNNER" "$SYNC_DIR/runner_shim.c"
fi

h1="${T1%%:*}"; m1="${T1##*:}"; h2="${T2%%:*}"; m2="${T2##*:}"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$RUNNER</string>
    <string>$SYNC_DIR/matter_sync.sh</string>
    <string>$MATTER_DIR</string>
    <string>--scheduled</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>$((10#$h1))</integer><key>Minute</key><integer>$((10#$m1))</integer></dict>
    <dict><key>Hour</key><integer>$((10#$h2))</integer><key>Minute</key><integer>$((10#$m2))</integer></dict>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG_ROOT/launchd-$MATTER_NAME.log</string>
  <key>StandardErrorPath</key><string>$LOG_ROOT/launchd-$MATTER_NAME.log</string>
</dict>
</plist>
EOF
plutil -lint "$PLIST" >/dev/null

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed and loaded $LABEL (fires $T1 and $T2, plus once at load)."
echo
echo "REMINDER: grant Full Disk Access to $RUNNER if you haven't"
echo "(System Settings → Privacy & Security → Full Disk Access)."
