#!/usr/bin/env bash
# Package an unsigned .app into a standard .ipa for LiveContainer sideloading.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

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

APP_DEST="$STAGE_DIR/Payload/TubeLM.app"

# 1. Always ensure canonical Info.plist is bundled
if [ -f "$REPO_ROOT/ios/TubeLM/Info.plist" ]; then
    cp "$REPO_ROOT/ios/TubeLM/Info.plist" "$APP_DEST/Info.plist"
fi

# 2. Bundle all AppIcon PNGs
echo "Staging app icons into bundle..."
for icon in "$REPO_ROOT/ios/TubeLM"/AppIcon*.png; do
    if [ -f "$icon" ]; then
        cp "$icon" "$APP_DEST/"
    fi
done

# 3. Bundle fallback data.json if missing
if [ ! -f "$APP_DEST/data.json" ]; then
    MOCK_PATH="$REPO_ROOT/.workflow/mocks/mock_data.json"
    if [ -f "$MOCK_PATH" ]; then
        cp "$MOCK_PATH" "$APP_DEST/data.json"
    fi
fi

# 4. Ad-hoc codesign (mandatory for iOS AMFI loading under LiveContainer)
if command -v codesign &>/dev/null; then
    echo "Applying ad-hoc code signature via codesign..."
    codesign -s - --force --deep "$APP_DEST" || true
elif command -v ldid &>/dev/null; then
    echo "Applying ad-hoc code signature via ldid..."
    ldid -S "$APP_DEST/TubeLM" || true
else
    echo "Note: Neither codesign nor ldid found; skipping ad-hoc signature on host."
fi

# 5. Pre-packaging validation assertions
echo "Running packaging validation assertions..."
[ -f "$APP_DEST/TubeLM" ] || { echo "::error::Missing TubeLM binary in bundle"; exit 1; }
[ -s "$APP_DEST/TubeLM" ] || { echo "::error::TubeLM binary is empty"; exit 1; }
[ -f "$APP_DEST/Info.plist" ] || { echo "::error::Missing Info.plist in bundle"; exit 1; }
grep -q "CFBundleIcons" "$APP_DEST/Info.plist" || { echo "::error::Info.plist missing CFBundleIcons"; exit 1; }
grep -q "CFBundleSupportedPlatforms" "$APP_DEST/Info.plist" || { echo "::error::Info.plist missing CFBundleSupportedPlatforms"; exit 1; }

# Verify all 5 icons
for required_icon in AppIcon.png AppIcon60x60@2x.png AppIcon60x60@3x.png AppIcon76x76@2x.png AppIcon83.5x83.5@2x.png; do
    [ -f "$APP_DEST/$required_icon" ] || { echo "::error::Missing required icon: $required_icon"; exit 1; }
done
echo "✓ All 5 icon assets verified in bundle"

echo "Creating IPA: $OUTPUT_IPA"
mkdir -p "$(dirname "$OUTPUT_IPA")"
(cd "$STAGE_DIR" && zip -qr -9 "$OLDPWD/$OUTPUT_IPA" Payload)

echo "Verifying generated IPA:"
unzip -l "$OUTPUT_IPA" | grep -E "AppIcon.*\.png"
ls -lh "$OUTPUT_IPA"

echo "✓ Successfully generated $OUTPUT_IPA (ready for LiveContainer sideloading)!"
