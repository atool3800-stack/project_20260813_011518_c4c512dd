#!/usr/bin/env bash
#
# install_cron.sh - install the hourly quality-sync cron job
#
# Adds/refreshes a crontab entry that runs scripts/run_sync.sh at minute 0 of
# every hour (e.g. 00:00, 01:00, 02:00 ...).
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO_DIR/scripts/run_sync.sh"
chmod +x "$RUNNER"

CRON_LINE="0 * * * * cd $REPO_DIR && $RUNNER >> $REPO_DIR/logs/quality_sync.log 2>&1"
mkdir -p "$REPO_DIR/logs"

# Remove any previously installed line for this runner, then append fresh
( crontab -l 2>/dev/null | grep -v "scripts/run_sync.sh" || true
  echo "$CRON_LINE" ) | crontab -

echo "Installed hourly cron job:"
crontab -l | grep run_sync || true
echo "Logs: $REPO_DIR/logs/quality_sync.log"
