#!/usr/bin/env bash
# Package an unsigned .app into a standard .ipa for LiveContainer sideloading.
set -euo pipefail

APP_PATH="${1:-}"
OUTPUT_IPA="${2:-TubeLM.ipa}"

if [ -z "$APP_PATH" ] || [ ! -d "$APP_PATH" ]; then
    echo "Usage: $0 <path-to-TubeLM.app> [output-ipa-path]"
    exit 1
fi

STAGE_DIR=$(mktemp -d)
trap 'rm -rf "$STAGE_DIR"' EXIT

echo "Staging application payload from: $APP_PATH"
mkdir -p "$STAGE_DIR/Payload"
cp -R "$APP_PATH" "$STAGE_DIR/Payload/TubeLM.app"

echo "Creating unsigned IPA: $OUTPUT_IPA"
(cd "$STAGE_DIR" && zip -qr -9 "$OLDPWD/$OUTPUT_IPA" Payload)

echo "✓ Successfully generated $OUTPUT_IPA (ready for LiveContainer sideloading)!"
