#!/usr/bin/env bash
# test_deb_sandbox.sh — Orchestrates building and running the autonomous TubeLM GUI test sandbox.
set -euo pipefail

# Text color formatting
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No color

echo -e "${CYAN}=========================================================================${NC}"
echo -e "${CYAN}             📦 TubeLM Native .deb Sandboxed GUI Validator 📦            ${NC}"
echo -e "${CYAN}=========================================================================${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

# Ensure docker is running
if ! command -v docker &>/dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH. Skipping containerized validation.${NC}"
    exit 1
fi

echo -e "${BLUE}[*] Building clean GUI test Docker image (Ubuntu 22.04 + Xvfb)...${NC}"
docker build -t tubelm-gui-test -f desktop/scripts/Dockerfile.test .

echo -e "\n${BLUE}[*] Launching container and running headless E2E verification...${NC}"
# Mount host's summaries/ directory to capture the visual screenshots out of the sandbox
docker run --rm \
    -v "${PROJECT_DIR}/summaries:/app/summaries" \
    tubelm-gui-test

# Overwrite root installer with the backward-compatible build generated inside container
if [ -f "summaries/tubelm_1.0.0_amd64_compat.deb" ]; then
    echo -e "${BLUE}[*] Copying backwards-compatible debian build to root dist/...${NC}"
    mkdir -p dist
    cp summaries/tubelm_1.0.0_amd64_compat.deb dist/tubelm_1.0.0_amd64.deb
    rm -f summaries/tubelm_1.0.0_amd64_compat.deb
fi

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}          🎉 Containerized GUI Verification Complete! 🎉                ${NC}"
echo -e "${GREEN}=========================================================================${NC}"
echo -e "You can inspect the captured sandboxed screenshots here:"
echo -e "    ${CYAN}${PROJECT_DIR}/summaries/test_report/01_homepage_dashboard.png${NC}\n"
echo -e "Backward-compatible production package saved to:"
echo -e "    ${CYAN}${PROJECT_DIR}/dist/tubelm_1.0.0_amd64.deb${NC}\n"
