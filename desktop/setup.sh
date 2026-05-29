#!/usr/bin/env bash
# setup.sh — Dynamic setup script for TubeLM (Core or GUI option)
set -euo pipefail

# Text color formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No color (reset)

echo -e "${CYAN}=========================================================================${NC}"
echo -e "${CYAN}                  📺 Welcome to TubeLM Setup Wizard 📺                  ${NC}"
echo -e "${CYAN}=========================================================================${NC}"

# Check for Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install it and try again.${NC}"
    exit 1
fi

echo -e "\nChoose your installation mode:"
echo -e "1) ${GREEN}GUI Mode${NC} (Default - Includes the Web Dashboard, live notebooks listing, selective channel running, and logs viewer)"
echo -e "2) ${BLUE}Core Only Mode${NC} (Lightweight CLI execution without web dependencies)\n"

read -p "Install with GUI? [Y/n]: " INSTALL_MODE
INSTALL_MODE=$(echo "$INSTALL_MODE" | tr '[:upper:]' '[:lower:]')

# Default to GUI mode
INSTALL_GUI=true
if [[ "$INSTALL_MODE" == "n" || "$INSTALL_MODE" == "no" || "$INSTALL_MODE" == "2" ]]; then
    INSTALL_GUI=false
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "\n${CYAN}Creating virtual environment (.venv)…${NC}"
python3 -m venv "$REPO_ROOT/.venv"

echo -e "${CYAN}Activating virtual environment…${NC}"
# Use temporary activation or direct bin calls
"$REPO_ROOT/.venv/bin/pip" install --upgrade pip

echo -e "${CYAN}Installing core dependencies…${NC}"
"$REPO_ROOT/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

if [ "$INSTALL_GUI" = true ]; then
    echo -e "${GREEN}Installing GUI dependencies…${NC}"
    "$REPO_ROOT/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements-gui.txt"
fi

echo -e "\n${CYAN}Setting up configuration files…${NC}"
if [ ! -f "$REPO_ROOT/.env" ]; then
    echo -e "Creating .env from template..."
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    echo -e "${RED}Action Required: Please edit the '.env' file to add your API keys and credentials.${NC}"
else
    echo -e "'.env' already exists. Skipping."
fi

if [ ! -f "$REPO_ROOT/channels.json" ]; then
    echo -e "Creating channels.json with sample monitored channels..."
    cp "$REPO_ROOT/channels.json.example" "$REPO_ROOT/channels.json"
else
    echo -e "'channels.json' already exists. Skipping."
fi

echo -e "\n${GREEN}=========================================================================${NC}"
echo -e "${GREEN}                     🎉 Installation Successful! 🎉                      ${NC}"
echo -e "${GREEN}=========================================================================${NC}"

if [ "$INSTALL_GUI" = true ]; then
    echo -e "\nTo run the TubeLM Web Dashboard GUI, execute:"
    echo -e "    ${CYAN}cd $(basename "$REPO_ROOT") && .venv/bin/python desktop/main.py --gui${NC}"
    echo -e "\nThen open your browser and navigate to:"
    echo -e "    ${CYAN}http://localhost:5000${NC} (or the next available port if 5000 is in use)"
else
    echo -e "\nTo run the TubeLM CLI Pipeline, execute:"
    echo -e "    ${CYAN}cd $(basename "$REPO_ROOT") && .venv/bin/python desktop/main.py${NC}"
    echo -e "\nFor a dry run (simulate without sending email or creating notebooks):"
    echo -e "    ${CYAN}cd $(basename "$REPO_ROOT") && .venv/bin/python desktop/main.py --dry-run${NC}"
fi
echo -e "\nFor more details, please check the README.md.\n"
