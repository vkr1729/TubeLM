#!/usr/bin/env bash
# run_weekly.sh — TubeLM Weekly Automated Pipeline Sync
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

mkdir -p ~/.tubelm
echo "=========================================" >> ~/.tubelm/tubelm-weekly.log
echo "Starting TubeLM Weekly Sync: $(date)" >> ~/.tubelm/tubelm-weekly.log
echo "=========================================" >> ~/.tubelm/tubelm-weekly.log

"$REPO_DIR/.venv/bin/python" "$REPO_DIR/desktop/main.py" --scheduled >> ~/.tubelm/tubelm-weekly.log 2>&1
