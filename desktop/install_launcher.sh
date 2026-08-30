#!/usr/bin/env bash
# Install the TubeLM dashboard launcher on the user's Linux desktop.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP)"
else
    DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
fi

if [[ -z "$DESKTOP_DIR" || "$DESKTOP_DIR" == "/" ]]; then
    echo "Could not determine a safe desktop directory." >&2
    exit 1
fi

mkdir -p "$DESKTOP_DIR"
TARGET="$DESKTOP_DIR/TubeLM.desktop"

sed "s|@PROJECT_ROOT@|$PROJECT_ROOT|g" \
    "$PROJECT_ROOT/desktop/TubeLM.desktop.in" > "$TARGET"
chmod 755 "$TARGET"

echo "Installed TubeLM launcher: $TARGET"
