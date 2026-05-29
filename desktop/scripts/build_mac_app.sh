#!/usr/bin/env bash
# scripts/build_mac_app.sh — Compiles and bundles TubeLM into a native macOS App
set -euo pipefail

# Text color formatting
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No color

echo -e "${CYAN}=========================================================================${NC}"
echo -e "${CYAN}                  📺 TubeLM macOS App Bundler Wizard 📺                  ${NC}"
echo -e "${CYAN}=========================================================================${NC}"

# Navigate to desktop directory (where the spec file lives)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(dirname "$PROJECT_DIR")"
cd "$PROJECT_DIR"

# Ensure venv exists at the repo root (not inside desktop/)
if [ ! -d "$REPO_ROOT/.venv" ]; then
    echo -e "${BLUE}Creating Python virtual environment ($REPO_ROOT/.venv)...${NC}"
    python3 -m venv "$REPO_ROOT/.venv"
fi

# Upgrade pip and install GUI dependencies into root venv
echo -e "${BLUE}Upgrading pip and installing GUI dependencies into $REPO_ROOT/.venv...${NC}"
"$REPO_ROOT/.venv/bin/pip" install --upgrade pip
"$REPO_ROOT/.venv/bin/pip" install -r requirements.txt -r requirements-gui.txt

# Generate Apple Icon Image (ICNS) dynamically from PNG if running on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    if [ ! -f "$REPO_ROOT/shared/assets/logo.icns" ]; then
        echo -e "\n${BLUE}Generating logo.icns dynamically from logo.png...${NC}"
        ICONSET_DIR="logo.iconset"
        mkdir -p "$ICONSET_DIR"
        sips -z 16 16     "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1 || true
        sips -z 32 32     "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1 || true
        sips -z 32 32     "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1 || true
        sips -z 64 64     "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1 || true
        sips -z 128 128   "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1 || true
        sips -z 256 256   "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1 || true
        sips -z 256 256   "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1 || true
        sips -z 512 512   "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1 || true
        sips -z 512 512   "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1 || true
        sips -z 1024 1024 "$REPO_ROOT/shared/assets/logo.png" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null 2>&1 || true
        iconutil -c icns "$ICONSET_DIR" -o "$REPO_ROOT/shared/assets/logo.icns" >/dev/null 2>&1 || true
        rm -rf "$ICONSET_DIR"
    fi
fi

# Run PyInstaller using the macOS spec file (single source of truth)
# -y: automatically remove existing dist output directory without prompting
echo -e "\n${BLUE}Compiling TubeLM status bar application using PyInstaller spec (tubelm_mac.spec)...${NC}"
"$REPO_ROOT/.venv/bin/pyinstaller" --clean -y tubelm_mac.spec

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}             🎉 Application Compiled Successfully! 🎉                   ${NC}"
echo -e "${GREEN}=========================================================================${NC}"
echo -e "\nYou can locate your native macOS App Bundle here:"
echo -e "    ${CYAN}${PROJECT_DIR}/dist/TubeLM.app${NC}"

echo -e "\nTo test your application locally, run:"
echo -e "    ${CYAN}open dist/TubeLM.app${NC}"

echo -e "\n${BLUE}-------------------------------------------------------------------------${NC}"
echo -e "${BLUE}          🔒 Production Distribution (Sign & Notarize) Instructions      ${NC}"
echo -e "${BLUE}-------------------------------------------------------------------------${NC}"
echo -e "To distribute to users outside your machine without macOS Gatekeeper warnings:"
echo -e "1. ${CYAN}Code Sign${NC} using your Apple Developer ID Certificate:"
echo -e "   codesign --deep --force --options runtime --sign \"Developer ID Application: Your Name (TeamID)\" dist/TubeLM.app"
echo -e "\n2. ${CYAN}Package to DMG${NC} using create-dmg (install via: brew install create-dmg):"
echo -e "   create-dmg --volname \"TubeLM Installer\" --icon \"TubeLM.app\" 175 120 --app-drop-link 425 120 \"dist/TubeLM-macOS.dmg\" \"dist/\""
echo -e "\n3. ${CYAN}Notarize DMG${NC} with Apple Notary Service:"
echo -e "   xcrun notarytool submit dist/TubeLM-macOS.dmg --developer-id \"your_apple_id\" --password \"app_specific_password\" --wait"
echo -e "\n4. ${CYAN}Staple Notarization Ticket${NC} to your DMG:"
echo -e "   xcrun stapler staple dist/TubeLM-macOS.dmg\n"
