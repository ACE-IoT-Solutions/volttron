#!/usr/bin/env bash
# UV-based VOLTTRON Bootstrap Script
# Upgraded for Python 3.10+ and modern dependency management

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}VOLTTRON UV Bootstrap Script${NC}"
echo "================================"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | sed -n 's/Python \([0-9]*\.[0-9]*\).*/\1/p')
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}Error: Python $REQUIRED_VERSION or higher is required. Found $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION detected${NC}"

# Install UV if not present
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Installing UV package manager...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo -e "${GREEN}✓ UV package manager ready${NC}"

# Create virtual environment with UV
echo -e "${YELLOW}Creating virtual environment...${NC}"
uv venv --python python3.10 .venv

# Activate virtual environment
source .venv/bin/activate

echo -e "${GREEN}✓ Virtual environment created${NC}"

# Install dependencies
echo -e "${YELLOW}Installing base dependencies...${NC}"
uv pip install -e .

# Install optional dependencies based on arguments
for arg in "$@"; do
    case $arg in
        --databases)
            echo -e "${YELLOW}Installing database dependencies...${NC}"
            uv pip install -e ".[databases]"
            ;;
        --drivers)
            echo -e "${YELLOW}Installing driver dependencies...${NC}"
            uv pip install -e ".[drivers]"
            ;;
        --testing)
            echo -e "${YELLOW}Installing testing dependencies...${NC}"
            uv pip install -e ".[testing]"
            ;;
        --web)
            echo -e "${YELLOW}Installing web dependencies...${NC}"
            uv pip install -e ".[web]"
            ;;
        --all)
            echo -e "${YELLOW}Installing all optional dependencies...${NC}"
            uv pip install -e ".[databases,drivers,testing,web]"
            ;;
        --dev)
            echo -e "${YELLOW}Installing development dependencies...${NC}"
            uv pip install ruff black mypy pytest pytest-cov
            ;;
    esac
done

# Install ZMQ with bundled option
echo -e "${YELLOW}Installing ZMQ with bundled libraries...${NC}"
uv pip install pyzmq --config-settings="--zmq=bundled"

# Create necessary directories
mkdir -p $HOME/.volttron
mkdir -p $HOME/.volttron/certificates
mkdir -p $HOME/.volttron/run

echo -e "${GREEN}✓ Bootstrap complete!${NC}"
echo ""
echo "To activate the environment, run:"
echo "  source .venv/bin/activate"
echo ""
echo "To start VOLTTRON, run:"
echo "  volttron -vv"