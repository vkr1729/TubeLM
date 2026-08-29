#!/usr/bin/env bash
# tubelm-launch.sh — Start TubeLM GUI server and open Google Chrome
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

URL="http://127.0.0.1:5000"

# Check if GUI server is already listening on port 5000
if curl -s --connect-timeout 1 "$URL/" >/dev/null 2>&1; then
    echo "TubeLM GUI server is already running on $URL."
else
    echo "Starting TubeLM GUI server..."
    # Launch server in background — gui.py's own webbrowser.open is disabled
    # because we handle Chrome launch below explicitly.
    nohup "$REPO_DIR/.venv/bin/python" "$REPO_DIR/desktop/gui.py" --port 5000 \
        >> "$HOME/.tubelm/gui-server.log" 2>&1 &

    # Wait for server to actually respond (up to 8 seconds)
    echo "Waiting for server to start..."
    for i in {1..16}; do
        if curl -s --connect-timeout 1 "$URL/" >/dev/null 2>&1; then
            echo "Server is ready."
            break
        fi
        sleep 0.5
    done
fi

# Open Google Chrome (always, even if server was already running)
if command -v google-chrome &>/dev/null; then
    google-chrome "$URL" &
elif command -v google-chrome-stable &>/dev/null; then
    google-chrome-stable "$URL" &
else
    xdg-open "$URL" &
fi
