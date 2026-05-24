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

# Navigate to project root
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Ensure venv exists
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}Creating Python virtual environment (.venv)...${NC}"
    python3 -m venv .venv
fi

# Activate environment and verify dependencies
echo -e "${BLUE}Upgrading pip and installing GUI dependencies...${NC}"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt -r requirements-gui.txt

# Run PyInstaller compilation
echo -e "\n${BLUE}Compiling TubeLM status bar application using PyInstaller...${NC}"
.venv/bin/pyinstaller \
    --windowed \
    --noconsole \
    --clean \
    --name="TubeLM" \
    --icon="assets/logo.png" \
    --add-data "templates:templates" \
    --add-data "assets:assets" \
    --add-data "Summary_Prompt.md:." \
    --add-data "Podcast_Prompt.md:." \
    mac_launcher.py

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
