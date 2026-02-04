#!/bin/bash
#
# Stanford Human-AI Collaboration Study - Setup Script
# This script automates the environment setup for participants
#
# Usage: bash setup.sh
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Initialize conda for this script
init_conda() {
    # Try to find and source conda
    if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
    elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
        source "$HOME/anaconda3/etc/profile.d/conda.sh"
    elif [ -f "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh" ]; then
        source "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    elif [ -f "/usr/local/Caskroom/miniconda/base/etc/profile.d/conda.sh" ]; then
        source "/usr/local/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    elif command -v conda &> /dev/null; then
        eval "$(conda shell.bash hook)"
    else
        echo -e "${RED}Could not initialize conda. Please ensure conda is installed.${NC}"
        exit 1
    fi
}

echo -e "${BLUE}"
echo "=============================================================================="
echo "     Stanford Human-AI Collaboration Study - Setup Script        "
echo "=============================================================================="
echo -e "${NC}"

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)    OS="macos" ;;
        Linux*)     OS="linux" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *)          OS="unknown" ;;
    esac
    echo -e "${GREEN}Detected OS: $OS${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Step 1: Check prerequisites
check_prerequisites() {
    echo -e "\n${BLUE}[1/6] Checking prerequisites...${NC}"

    MISSING=""
    GO_NEEDS_INSTALL=false

    # Check conda
    if ! command_exists conda; then
        MISSING="$MISSING conda"
        echo -e "${RED}[X] conda not found${NC}"
        echo "  Please install Miniconda or Anaconda from:"
        echo "  https://docs.conda.io/en/latest/miniconda.html"
    else
        echo -e "${GREEN}[OK] conda found${NC}"
    fi

    # Check Docker
    if ! command_exists docker; then
        MISSING="$MISSING docker"
        echo -e "${RED}[X] docker not found${NC}"
        echo "  Please install Docker Desktop from:"
        echo "  https://docs.docker.com/desktop/"
    else
        echo -e "${GREEN}[OK] docker found${NC}"
        # Check if Docker daemon is running
        if ! docker info >/dev/null 2>&1; then
            echo -e "${YELLOW}[!] Docker daemon is not running${NC}"
            case "$OS" in
                macos|windows)
                    echo "  Please open Docker Desktop and keep it running."
                    echo "  The daemon only runs when Docker Desktop is open."
                    ;;
                linux)
                    echo "  If using Docker Engine: sudo systemctl start docker"
                    echo "  If using Docker Desktop: Open the application and keep it running."
                    ;;
            esac
            read -p "Continue anyway? [y/N]: " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        else
            echo -e "${GREEN}[OK] Docker daemon running${NC}"
        fi
    fi

    # Check Git
    if ! command_exists git; then
        MISSING="$MISSING git"
        echo -e "${RED}[X] git not found${NC}"
    else
        echo -e "${GREEN}[OK] git found${NC}"
    fi

    # Check Go (will be installed via conda if not found)
    if ! command_exists go; then
        echo -e "${YELLOW}[!] go not found - will be installed via conda${NC}"
    else
        echo -e "${GREEN}[OK] go found ($(go version | cut -d' ' -f3))${NC}"
    fi

    if [ -n "$MISSING" ]; then
        echo -e "\n${RED}Missing prerequisites:$MISSING${NC}"
        echo "Please install them and run this script again."
        exit 1
    fi
}

# Step 2: Initialize git submodules
init_submodules() {
    echo -e "\n${BLUE}[2/6] Initializing git submodules...${NC}"
    git submodule update --init --recursive
    echo -e "${GREEN}[OK] Submodules initialized${NC}"
}

# Step 3: Create conda environment
setup_conda_env() {
    echo -e "\n${BLUE}[3/6] Setting up conda environment...${NC}"

    # Check if environment already exists
    if conda env list | grep -q "^snake "; then
        echo -e "${YELLOW}Conda environment 'snake' already exists.${NC}"
        read -p "Do you want to recreate it? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            conda deactivate 2>/dev/null || true
            conda env remove -n snake -y
            conda create -n snake python=3.10 -y
        fi
    else
        conda create -n snake python=3.10 -y
    fi

    echo -e "${GREEN}[OK] Conda environment ready${NC}"

    # Activate environment
    conda activate snake

    # Install dependencies
    echo -e "\n${BLUE}Installing Python dependencies...${NC}"
    pip install -r requirements.txt

    echo -e "${GREEN}[OK] Python dependencies installed${NC}"
}

# Step 4: Install Go and build battlesnake CLI
setup_battlesnake() {
    echo -e "\n${BLUE}[4/6] Setting up BattleSnake CLI...${NC}"

    # Ensure we're in snake environment
    conda activate snake

    # Install Go via conda
    conda install -c conda-forge go -y

    # Build battlesnake CLI
    echo "Building battlesnake CLI..."
    cd rules
    go build -o battlesnake ./cli/battlesnake/main.go
    cd ..

    # Verify
    if [ -f "rules/battlesnake" ]; then
        echo -e "${GREEN}[OK] BattleSnake CLI built successfully${NC}"
    else
        echo -e "${RED}[X] Failed to build BattleSnake CLI${NC}"
        exit 1
    fi
}

# Step 5: Setup recording tool
setup_recording_tool() {
    echo -e "\n${BLUE}[5/6] Setting up recording tool...${NC}"

    # Ensure we're in snake environment
    conda activate snake

    cd record

    case "$OS" in
        macos)
            pip install -e .
            echo -e "${YELLOW}Note: Please enable Screen Recording permission for Terminal/VSCode${NC}"
            echo "  Go to: System Preferences -> Privacy & Security -> Screen Recording"
            ;;
        linux)
            # Check for required system packages
            echo "Checking Linux system dependencies..."
            MISSING_PKGS=""

            if ! command_exists wmctrl; then
                MISSING_PKGS="$MISSING_PKGS wmctrl"
            fi
            if ! command_exists maim; then
                MISSING_PKGS="$MISSING_PKGS maim"
            fi

            if [ -n "$MISSING_PKGS" ]; then
                echo -e "${YELLOW}Missing system packages:$MISSING_PKGS${NC}"
                echo "Please install them:"
                echo "  Arch: sudo pacman -S$MISSING_PKGS"
                echo "  Ubuntu/Debian: sudo apt install$MISSING_PKGS"
                echo "  Fedora: sudo dnf install$MISSING_PKGS"
                read -p "Continue anyway? [y/N]: " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    exit 1
                fi
            fi

            # Try installing with linux extras first
            if ! pip install -e .[linux] 2>/dev/null; then
                echo -e "${YELLOW}Linux extras failed, installing base package...${NC}"
                pip install -e .
            fi
            ;;
        windows)
            pip install -e .[windows]
            ;;
        *)
            pip install -e .
            ;;
    esac

    cd ..
    echo -e "${GREEN}[OK] Recording tool installed${NC}"
}

# Step 6: Setup tournament script
setup_tournament() {
    echo -e "\n${BLUE}[6/6] Setting up tournament script...${NC}"

    if [ ! -f "run_dev_tournament.sh" ]; then
        cp run_dev_tournament_local.sh run_dev_tournament.sh
        chmod +x run_dev_tournament.sh
        echo -e "${GREEN}[OK] Tournament script configured${NC}"
    else
        echo -e "${YELLOW}Tournament script already exists${NC}"
    fi

    # Interactive snapshot config setup
    setup_snapshot_config
}

# Interactive snapshot config setup
setup_snapshot_config() {
    CONFIG_FILE="eval/snapshot_config.json"

    if [ -f "$CONFIG_FILE" ]; then
        echo -e "${GREEN}[OK] Snapshot config already exists${NC}"

        # Validate existing config
        if python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
            USER_ID=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('user_id', 'NOT SET'))" 2>/dev/null)
            echo -e "  User ID: ${BLUE}$USER_ID${NC}"

            read -p "Do you want to replace it with a new config? [y/N]: " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                return 0
            fi
        else
            echo -e "${YELLOW}  Existing config appears invalid. Let's set it up again.${NC}"
        fi
    fi

    echo -e "\n${BLUE}============================================================================${NC}"
    echo -e "${BLUE}                    SNAPSHOT CONFIG SETUP${NC}"
    echo -e "${BLUE}============================================================================${NC}"
    echo ""
    echo "You should have received your personal config JSON via email."
    echo "Please paste the ENTIRE JSON content below."
    echo ""
    echo -e "${YELLOW}Instructions:${NC}"
    echo "  1. Copy the JSON from your email"
    echo "  2. Paste it here (it may be multiple lines)"
    echo "  3. Press Enter, then Ctrl+D (Mac/Linux) or Ctrl+Z (Windows) to finish"
    echo ""
    echo -e "${BLUE}============================================================================${NC}"
    echo -e "Paste your config JSON now:"
    echo ""

    # Loop until valid JSON is provided
    while true; do
        # Read multiline input
        CONFIG_CONTENT=""
        while IFS= read -r line; do
            CONFIG_CONTENT="${CONFIG_CONTENT}${line}"$'\n'
        done

        # Check if empty
        if [ -z "$(echo "$CONFIG_CONTENT" | tr -d '[:space:]')" ]; then
            echo -e "\n${RED}No input received.${NC}"
            read -p "Try again? [Y/n]: " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Nn]$ ]]; then
                echo -e "${YELLOW}Skipping config setup. You can set it up later manually.${NC}"
                return 0
            fi
            echo -e "\nPaste your config JSON:"
            continue
        fi

        # Validate JSON
        if echo "$CONFIG_CONTENT" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
            # Valid JSON - save it
            echo "$CONFIG_CONTENT" > "$CONFIG_FILE"

            # Extract and display user_id for confirmation
            USER_ID=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('user_id', 'NOT SET'))")
            ENABLED=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('enabled', False))")

            echo -e "\n${GREEN}[OK] Config saved successfully!${NC}"
            echo -e "  File: ${BLUE}$CONFIG_FILE${NC}"
            echo -e "  User ID: ${BLUE}$USER_ID${NC}"
            echo -e "  Enabled: ${BLUE}$ENABLED${NC}"

            if [ "$ENABLED" != "True" ] && [ "$ENABLED" != "true" ]; then
                echo -e "\n${YELLOW}[!] Warning: 'enabled' is not set to true in your config.${NC}"
                echo "  Submissions may not work until this is enabled."
            fi

            break
        else
            echo -e "\n${RED}Invalid JSON format. Please check your input and try again.${NC}"
            echo -e "${YELLOW}Common issues:${NC}"
            echo "  - Make sure you copied the ENTIRE JSON (including { and })"
            echo "  - Check for any missing quotes or commas"
            echo ""
            read -p "Try again? [Y/n]: " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Nn]$ ]]; then
                echo -e "${YELLOW}Skipping config setup. You can set it up later manually:${NC}"
                echo "  cp eval/snapshot_config.json.template eval/snapshot_config.json"
                echo "  # Then edit the file with your config"
                return 0
            fi
            echo -e "\nPaste your config JSON:"
        fi
    done
}

# Final summary
print_summary() {
    echo -e "\n${GREEN}"
    echo "=============================================================================="
    echo "                    Setup Complete!                               "
    echo "=============================================================================="
    echo -e "${NC}"

    echo "Next steps:"
    echo ""
    echo "1. Activate the environment:"
    echo -e "   ${BLUE}conda activate snake${NC}"
    echo ""
    echo "2. Test your snake:"
    echo -e "   ${BLUE}PORT=7123 python your_snake/main.py${NC}"
    echo "   (In another terminal)"
    echo -e "   ${BLUE}./rules/battlesnake play -W 11 -H 11 --name your_snake --url http://localhost:7123 -g solo -v${NC}"
    echo ""
    echo "3. Start recording before you begin working:"
    echo -e "   ${BLUE}gum${NC}"
    echo ""
    echo "4. Run a benchmark tournament:"
    echo -e "   ${BLUE}./run_dev_tournament.sh${NC}"
    echo ""
    echo "5. Submit your work:"
    echo -e "   ${BLUE}python submit.py -s init --snake_name YOUR_SNAKE_NAME${NC}"
    echo ""

    if [ "$OS" = "macos" ]; then
        echo -e "${YELLOW}macOS users: Don't forget to enable Screen Recording permission!${NC}"
        echo -e "${YELLOW}macOS users: Keep Docker Desktop running when running tournaments!${NC}"
    elif [ "$OS" = "windows" ]; then
        echo -e "${YELLOW}Windows users: Keep Docker Desktop running when running tournaments!${NC}"
    elif [ "$OS" = "linux" ]; then
        echo -e "${YELLOW}Linux users: Ensure Docker daemon is running (systemctl start docker) before tournaments!${NC}"
    fi
}

# Main
main() {
    detect_os
    check_prerequisites
    init_conda  # Initialize conda for this script
    init_submodules
    setup_conda_env
    setup_battlesnake
    setup_recording_tool
    setup_tournament
    print_summary
}

main "$@"
