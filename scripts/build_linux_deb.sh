#!/usr/bin/env bash
# scripts/build_linux_deb.sh — Packages TubeLM into a native Debian/Ubuntu (.deb) installer
set -euo pipefail

# Text color formatting
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No color

echo -e "${CYAN}=========================================================================${NC}"
echo -e "${CYAN}                📺 TubeLM Debian/Ubuntu (.deb) Packager 📺               ${NC}"
echo -e "${CYAN}=========================================================================${NC}"

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
echo -e "\n${BLUE}Compiling Linux application using PyInstaller...${NC}"
.venv/bin/pyinstaller \
    --noconsole \
    --clean \
    --name="tubelm" \
    --icon="assets/logo.png" \
    --add-data "templates:templates" \
    --add-data "assets:assets" \
    --add-data "Summary_Prompt.md:." \
    --add-data "Podcast_Prompt.md:." \
    linux_launcher.py

# Create Debian directory structure
echo -e "\n${BLUE}Creating Debian package structure...${NC}"
DEB_ROOT="dist/debian_build"
rm -rf "$DEB_ROOT"
mkdir -p "$DEB_ROOT/DEBIAN"
mkdir -p "$DEB_ROOT/opt"
mkdir -p "$DEB_ROOT/usr/bin"
mkdir -p "$DEB_ROOT/usr/share/applications"
mkdir -p "$DEB_ROOT/usr/share/pixmaps"

# 1. Write control file
cat <<EOF > "$DEB_ROOT/DEBIAN/control"
Package: tubelm
Version: 1.0.0
Section: utils
Priority: optional
Architecture: amd64
Maintainer: TubeLM Team <maintainer@tubelm.io>
Description: Premium YouTube to NotebookLM Automation Pipeline & Email Digest
 Self-hosted automation pipeline that monitors YouTube feeds, synchronizes
 uploads to NotebookLM, and builds cinematic summaries/infographics.
EOF

# 2. Copy compiled binary folder
cp -r dist/tubelm "$DEB_ROOT/opt/tubelm"

# 3. Create usr/bin symlink wrapper
cat <<'EOF' > "$DEB_ROOT/usr/bin/tubelm"
#!/bin/sh
exec /opt/tubelm/tubelm "$@"
EOF
chmod +x "$DEB_ROOT/usr/bin/tubelm"

# 4. Create desktop entry file
cat <<EOF > "$DEB_ROOT/usr/share/applications/tubelm.desktop"
[Desktop Entry]
Type=Application
Version=1.0
Name=TubeLM
Comment=Premium YouTube to NotebookLM Intelligence Pipeline
Path=/opt/tubelm
Exec=/usr/bin/tubelm
Icon=tubelm
Terminal=false
Categories=Utility;Office;
EOF

# 5. Copy logo pixmap
cp assets/logo.png "$DEB_ROOT/usr/share/pixmaps/tubelm.png"

# Fix permissions
chmod 755 "$DEB_ROOT/DEBIAN"
chmod 644 "$DEB_ROOT/DEBIAN/control"
chmod 644 "$DEB_ROOT/usr/share/applications/tubelm.desktop"
chmod 644 "$DEB_ROOT/usr/share/pixmaps/tubelm.png"

# Build the .deb file
echo -e "\n${BLUE}Building Debian package using dpkg-deb...${NC}"
dpkg-deb --build "$DEB_ROOT" dist/tubelm_1.0.0_amd64.deb

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}             🎉 Debian Package Compiled Successfully! 🎉                ${NC}"
echo -e "${GREEN}=========================================================================${NC}"
echo -e "\nYou can locate your native Debian/Ubuntu installer here:"
echo -e "    ${CYAN}${PROJECT_DIR}/dist/tubelm_1.0.0_amd64.deb${NC}"
echo -e "\nTo install it locally on Ubuntu/Debian, double-click the .deb file or run:"
echo -e "    ${CYAN}sudo dpkg -i dist/tubelm_1.0.0_amd64.deb${NC}\n"
