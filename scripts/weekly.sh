#!/bin/bash
# weekly.sh - Linux/macOS wrapper around the cross-platform runner, with a lock so runs never overlap.
#   scripts/weekly.sh              -> plan        (default: read-only lineup preview, no writes, no notifications)
#   scripts/weekly.sh waivers      -> waiver/free-agent suggestions (read-only; notification summary)
#   scripts/weekly.sh lineups      -> LIVE lineup moves (guarded: lineup-slot moves only), verify, notification
#   scripts/weekly.sh sunday       -> LIVE late-inactive recheck; notify only if a lineup changed or an error occurred
#   scripts/weekly.sh sunday-plan  -> preview of the Sunday path (no writes, no notifications)
# Example cron (local time):
#   0 8 * * 2  /path/to/fantasy-football-companion/scripts/weekly.sh waivers
#   0 8 * * 4  /path/to/fantasy-football-companion/scripts/weekly.sh lineups
#   0 11 * * 0 /path/to/fantasy-football-companion/scripts/weekly.sh sunday
set -u
APP="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"; [ -x "$APP/.venv/bin/python" ] && PY="$APP/.venv/bin/python"
LOGDIR="${FF_DATA_DIR:-$APP/data}/logs"; mkdir -p "$LOGDIR"; cd "$APP" || exit 1
export PYTHONUNBUFFERED=1
MODE="${1:-plan}"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOGDIR/.weekly.lock"
  flock -n 9 || { echo "$(date '+%Y-%m-%d %H:%M:%S %Z') SKIP: lock held" >> "$LOGDIR/weekly_$(date +%Y%m%d).log"; exit 0; }
fi
exec "$PY" -m ff_companion.weekly "$MODE"
