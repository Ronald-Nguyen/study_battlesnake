#!/bin/bash
# Add output to a file
exec > >(tee -a run_dev_tournament_local.log) 2>&1
echo "Running tournament at $(date)"
echo "--------------------------------"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "  PRE-FLIGHT CHECKS"
echo "========================================"
echo ""

PREFLIGHT_FAILED=0

# Check 1: Git submodules initialized
if [ ! -f "rules/cli/battlesnake/main.go" ]; then
    echo -e "${RED}[X] Git submodules not initialized${NC}"
    echo "  Run: git submodule update --init --recursive"
    PREFLIGHT_FAILED=1
else
    echo -e "${GREEN}[OK] Git submodules initialized${NC}"
fi

# Check 2: Battlesnake CLI built
if [ ! -f "rules/battlesnake" ]; then
    echo -e "${RED}[X] Battlesnake CLI not built${NC}"
    echo "  Run: cd rules && go build -o battlesnake ./cli/battlesnake/main.go"
    PREFLIGHT_FAILED=1
else
    echo -e "${GREEN}[OK] Battlesnake CLI built${NC}"
fi

# Check 3: Docker installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[X] Docker not installed${NC}"
    echo "  Install from: https://docs.docker.com/desktop/"
    PREFLIGHT_FAILED=1
else
    echo -e "${GREEN}[OK] Docker installed${NC}"

    # Check 4: Docker daemon running
    if ! docker info &> /dev/null; then
        echo -e "${RED}[X] Docker daemon not running${NC}"
        case "$(uname -s)" in
            Darwin*)
                echo "  macOS: Open Docker Desktop and keep it running"
                ;;
            Linux*)
                echo "  Linux (Docker Engine): sudo systemctl start docker"
                echo "  Linux (Docker Desktop): Open the application"
                ;;
            MINGW*|MSYS*|CYGWIN*)
                echo "  Windows: Open Docker Desktop and keep it running"
                ;;
        esac
        PREFLIGHT_FAILED=1
    else
        echo -e "${GREEN}[OK] Docker daemon running${NC}"
    fi
fi

# Check 5: Snapshot config exists (warning only)
if [ ! -f "eval/snapshot_config.json" ]; then
    echo -e "${YELLOW}[!] Snapshot config not found - results won't be uploaded${NC}"
    echo "  Setup: cp eval/snapshot_config.json.template eval/snapshot_config.json"
    echo "  Then paste your config from the email"
else
    echo -e "${GREEN}[OK] Snapshot config found${NC}"
fi

# Check 6: your_snake exists
if [ ! -f "your_snake/main.py" ]; then
    echo -e "${RED}[X] your_snake/main.py not found${NC}"
    echo "  Make sure your snake code is in the your_snake/ directory"
    PREFLIGHT_FAILED=1
else
    echo -e "${GREEN}[OK] your_snake/main.py found${NC}"
fi

echo ""

if [ $PREFLIGHT_FAILED -eq 1 ]; then
    echo -e "${RED}Pre-flight checks failed. Please fix the issues above.${NC}"
    exit 1
fi

echo -e "${GREEN}All pre-flight checks passed!${NC}"
echo ""
echo "========================================"
echo ""

# Activate conda environment
if [ -n "$ZSH_VERSION" ]; then
    # Running in zsh
    [ -f ~/.zshrc ] && source ~/.zshrc
elif [ -n "$BASH_VERSION" ]; then
    # Running in bash
    [ -f ~/.bashrc ] && source ~/.bashrc
else
    # Fallback: try both
    [ -f ~/.bashrc ] && source ~/.bashrc
    [ -f ~/.zshrc ] && source ~/.zshrc
fi
eval "$(conda shell.bash hook)"
conda activate snake

echo "Active conda environment: $CONDA_DEFAULT_ENV"
echo "Python being used: $(which python)"
echo ""

# Detect docker-compose command (standalone vs plugin)
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
    echo "Using standalone docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
    echo "Using docker compose plugin"
else
    echo "ERROR: Neither 'docker-compose' nor 'docker compose' is available! Have you tried `brew install docker-compose`?"
    exit 1
fi

# Configuration file
SNAKES_CONFIG_FILE="snakes_config.json"

if [ ! -f "$SNAKES_CONFIG_FILE" ]; then
    echo "Error: $SNAKES_CONFIG_FILE not found!"
    exit 1
fi

echo ""
echo "=========================================="
echo "Reading snake configuration..."
echo "=========================================="
echo ""

eval $(python3 eval/config.py "$SNAKES_CONFIG_FILE" --type snake)

# Convert space-separated to newline-separated
SNAKE_LIST=$(echo "$SNAKE_DATA" | tr ' ' '\n')

if [ $? -ne 0 ]; then
    echo "Error parsing configuration file!"
    exit 1
fi

# Variables are now set: SNAKE_LIST, ITERATIONS, WORKERS, NUM_SNAKES

echo "Found $NUM_SNAKES snakes:"
echo "$SNAKE_LIST" | while IFS=':' read -r name port; do
    echo "  - $name (port $port)"
done
echo ""
echo "Tournament settings:"
echo "  - Iterations per matchup: $ITERATIONS"
echo "  - Workers: $WORKERS"
echo ""

# Generate docker-compose file dynamically
echo "=========================================="
echo "Generating docker-compose configuration..."
echo "=========================================="
echo ""

python generate_docker_compose.py --config $SNAKES_CONFIG_FILE --output docker-compose.test.yml

if [ $? -ne 0 ]; then
    echo "Error generating docker-compose file!"
    exit 1
fi

# Export all ports as environment variables for docker-compose
echo "$SNAKE_LIST" | while IFS=':' read -r name port; do
    export "PORT_${name//-/_}=$port"
done

echo ""
echo "=========================================="
echo "Starting Docker containers for all snakes"
echo "=========================================="
echo ""

# Start all snake containers
$DOCKER_COMPOSE -f docker-compose.test.yml up -d --build

# Wait for containers to be ready
echo "Waiting for containers to start..."
sleep 20

# Verify all snakes are responding
echo ""
echo "Verifying snake servers..."
FAILED=0
echo "$SNAKE_LIST" | while IFS=':' read -r name port; do
    if curl -s http://localhost:$port/ > /dev/null; then
        echo "[OK] $name (port $port) is responding"
    else
        echo "[X] WARNING: $name (port $port) is not responding!"
        FAILED=1
    fi
done

if [ $FAILED -eq 1 ]; then
    echo ""
    echo "WARNING: Some snakes failed to start!"
    echo "Continuing anyway..."
fi

echo ""
echo "=========================================="
echo "Running TrueSkill Round-Robin Tournament"
echo "=========================================="
echo ""

# Generate tournament ID upfront
TOURNAMENT_ID="round_robin_$(date +%Y%m%d_%H%M%S)"
echo "Tournament ID: $TOURNAMENT_ID"
export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}$(pwd)"

# Build snakes argument for tournament (comma-separated name:port pairs)
SNAKES_ARG=$(echo "$SNAKE_LIST" | paste -sd ',' -)

echo "Tournament matchups:"
echo "$SNAKE_LIST" | while IFS=':' read -r name port; do
    echo "  - $name"
done
echo ""

# Run the TrueSkill tournament with explicit tournament ID
python eval/trueskill_tournament.py \
    --snakes "$SNAKES_ARG" \
    --iterations $ITERATIONS \
    --workers $WORKERS \
    --tournament-id "$TOURNAMENT_ID"

TOURNAMENT_EXIT_CODE=$?

# Check if tournament completed successfully
if [ $TOURNAMENT_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[X] Tournament failed with exit code: $TOURNAMENT_EXIT_CODE"
    echo "Skipping snapshot upload."
    docker-compose -f docker-compose.test.yml down
    exit $TOURNAMENT_EXIT_CODE
fi

# Use the known tournament ID (no ls needed!)
LATEST_TOURNAMENT="tournaments/$TOURNAMENT_ID"
RESULTS_FILE="$LATEST_TOURNAMENT/trueskill_results.json"

echo ""
echo "=========================================="
echo "Uploading code snapshot..."
echo "=========================================="
echo ""

# Check if snapshot upload is configured
SNAPSHOT_CONFIG="eval/snapshot_config.json"

if [ ! -f "$SNAPSHOT_CONFIG" ]; then
    echo "No snapshot config found at $SNAPSHOT_CONFIG"
    echo "To enable snapshots:"
    echo "  cp eval/snapshot_config.json.template eval/snapshot_config.json"
    echo "  # Edit the file and set enabled=true"
else
    # Validate config file using eval/config.py and load variables directly
    VALIDATION_OUTPUT=$(python3 eval/config.py "$SNAPSHOT_CONFIG" --type snapshot 2>&1)
    VALIDATION_EXIT=$?
    
    # Parse the output
    if [ $VALIDATION_EXIT -eq 0 ]; then
        # Extract variables from output
        eval "$VALIDATION_OUTPUT"
        
        # Check validation result
        if [ "$VALIDATION_STATUS" = "DISABLED" ]; then
            echo "Snapshot upload is disabled in config"
            echo "Set 'enabled: true' in $SNAPSHOT_CONFIG to enable"
        elif [ "$VALIDATION_STATUS" = "VALID" ]; then
            # Configuration is valid
            echo "[OK] Configuration validated"
            echo "  User ID: $USER_ID"
            echo ""

            # Upload snapshot (snapshot_uploader.py reads URLs directly from config)
            UPLOAD_CMD="python eval/snapshot_uploader.py \
                --source your_snake \
                --tournament-id $TOURNAMENT_ID \
                --config $SNAPSHOT_CONFIG \
                --results-file $RESULTS_FILE"
            
            # Execute upload
            if $UPLOAD_CMD; then
                echo ""
                echo "[OK] Snapshot uploaded successfully"
            else
                echo ""
                echo "[X] Upload failed (continuing anyway...)"
            fi
        else
            echo "[X] Unexpected validation status: $VALIDATION_STATUS"
            echo "Skipping snapshot upload..."
        fi
    else
        # Validation failed with error
        echo "[X] Configuration validation failed:"
        echo "$VALIDATION_OUTPUT"
        echo ""
        echo "Please fix $SNAPSHOT_CONFIG"
        echo "Skipping snapshot upload..."
    fi
fi

# Cleanup
echo ""
echo "=========================================="
echo "Cleaning up..."
echo "=========================================="
docker-compose -f docker-compose.test.yml down