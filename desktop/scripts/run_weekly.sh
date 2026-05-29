#!/usr/bin/env bash
# scripts/run_weekly.sh — Weekly TubeLM pipeline wrapper
#
# Called by systemd timer (youtube-digest.timer) every Saturday.
# Handles: network wait, cookie refresh, pipeline execution, logging.
set -euo pipefail

# Resolve directories dynamically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_run_$(date +%Y-%m-%d_%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== YouTube Digest Weekly Run: $(date) ==="
echo "Log file: $LOG_FILE"

# ── Wait for network (max 60s) ────────────────────────────────────────────────
echo "Checking network connectivity…"
for i in $(seq 1 12); do
    if ping -c 1 -W 3 google.com &>/dev/null; then
        echo "Network available."
        break
    fi
    echo "Waiting for network… ($i/12)"
    sleep 5
done

# Final network check
if ! ping -c 1 -W 3 google.com &>/dev/null; then
    echo "ERROR: Network not available after 60 seconds. Aborting."
    exit 1
fi

# ── Refresh cookies from Chrome ───────────────────────────────────────────────
echo "Refreshing NotebookLM cookies from Chrome…"
"$VENV_DIR/bin/notebooklm" login --browser-cookies chrome || {
    echo "WARNING: Cookie refresh failed. Continuing with existing cookies."
}

sleep 5

# ── Run the main pipeline ─────────────────────────────────────────────────────
echo "Starting YouTube→NotebookLM pipeline…"
cd "$PROJECT_DIR"
"$VENV_DIR/bin/python" "$PROJECT_DIR/desktop/main.py" 2>&1
EXIT_CODE=$?

echo "=== Run complete: $(date) | Exit code: $EXIT_CODE ==="

# Clean up old logs (keep last 12 weeks)
find "$LOG_DIR" -name "weekly_run_*.log" -mtime +84 -delete 2>/dev/null || true

exit $EXIT_CODE
