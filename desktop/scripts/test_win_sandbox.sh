#!/usr/bin/env bash
# test_win_sandbox.sh — Orchestrates building and running the autonomous Windows-in-Wine E2E test sandbox.
set -euo pipefail

# Text color formatting
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No color

echo -e "${CYAN}=========================================================================${NC}"
echo -e "${CYAN}             📦 TubeLM Native Windows Sandboxed GUI Validator 📦         ${NC}"
echo -e "${CYAN}=========================================================================${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

# Ensure docker is running
if ! command -v docker &>/dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH. Skipping containerized validation.${NC}"
    exit 1
fi

echo -e "${BLUE}[*] Building clean Wine Windows GUI test Docker image (Ubuntu 22.04 + Wine + Xvfb)...${NC}"
docker build -t tubelm-win-test -f desktop/scripts/Dockerfile.win .

echo -e "\n${BLUE}[*] Launching container and running headless Windows E2E verification...${NC}"
# Mount host's summaries/ directory to capture the visual screenshots and output binary
docker run --rm \
    -v "${PROJECT_DIR}/summaries:/app/summaries" \
    tubelm-win-test

# Overwrite root installer with the backward-compatible build generated inside container
if [ -f "summaries/TubeLM_compat.exe" ]; then
    echo -e "${BLUE}[*] Copying validated Windows standalone executable to root dist/...${NC}"
    mkdir -p dist
    cp summaries/TubeLM_compat.exe dist/TubeLM.exe
    rm -f summaries/TubeLM_compat.exe
fi

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}          🎉 Containerized Windows GUI Verification Complete! 🎉        ${NC}"
echo -e "${GREEN}=========================================================================${NC}"
echo -e "You can inspect the captured sandboxed screenshots here:"
echo -e "    ${CYAN}${PROJECT_DIR}/summaries/test_report/01_homepage_dashboard.png${NC}\n"
echo -e "Standalone native Windows executable saved to:"
echo -e "    ${CYAN}${PROJECT_DIR}/dist/TubeLM.exe${NC}\n"
