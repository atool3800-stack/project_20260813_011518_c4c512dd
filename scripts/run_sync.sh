#!/usr/bin/env bash
#
# run_sync.sh - hourly data-quality sync runner
#
# Pulls the latest data from the remote repository, runs the quality checks,
# updates the Markdown quality report + README, and pushes the result back via
# the GitHub API (authenticated remote URL).
#
# The GitHub personal access token is read (in priority order) from:
#   1. $GITHUB_TOKEN environment variable
#   2. $REPO_DIR/.github_token (file, gitignored)
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# --- Resolve token ---------------------------------------------------------
TOKEN="${GITHUB_TOKEN:-}"
if [[ -z "$TOKEN" && -f "$REPO_DIR/.github_token" ]]; then
  TOKEN="$(tr -d '[:space:]' < "$REPO_DIR/.github_token")"
fi
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: no GitHub token found (set GITHUB_TOKEN or create .github_token)" >&2
  exit 1
fi

# --- Point the authenticated remote at our repository -----------------------
git remote remove origin 2>/dev/null || true
git remote add origin "https://x-access-token:${TOKEN}@github.com/atool3800-stack/project_20260813_011518_c4c512dd.git"

# --- Run the pipeline --------------------------------------------------------
python3 "$REPO_DIR/scripts/quality_check.py"

# Re-write the remote URL without the embedded token for safety
git remote set-url origin "https://github.com/atool3800-stack/project_20260813_011518_c4c512dd.git"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] hourly quality sync completed."
