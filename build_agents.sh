#!/usr/bin/env bash
# Build and install VOLTTRON agents

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}VOLTTRON Agent Builder${NC}"
echo "======================"

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    if [ -f .venv/bin/activate ]; then
        source .venv/bin/activate
    else
        echo "Error: Virtual environment not found. Run bootstrap_uv.sh first."
        exit 1
    fi
fi

# Function to build an agent
build_agent() {
    local agent_path=$1
    local agent_name=$(basename $agent_path)
    
    echo -e "${YELLOW}Building $agent_name...${NC}"
    
    if [ -f "$agent_path/setup.py" ]; then
        cd "$agent_path"
        python setup.py bdist_wheel
        cd - > /dev/null
        echo -e "${GREEN}✓ $agent_name built successfully${NC}"
    else
        echo "Warning: No setup.py found for $agent_name"
    fi
}

# Build core agents
echo -e "${YELLOW}Building core service agents...${NC}"
for agent in services/core/*/; do
    if [ -d "$agent" ]; then
        build_agent "$agent"
    fi
done

# Build contributed agents if requested
if [[ "$1" == "--contrib" ]] || [[ "$1" == "--all" ]]; then
    echo -e "${YELLOW}Building contributed agents...${NC}"
    for agent in services/contrib/*/; do
        if [ -d "$agent" ]; then
            build_agent "$agent"
        fi
    done
fi

# Build operations agents if requested
if [[ "$1" == "--ops" ]] || [[ "$1" == "--all" ]]; then
    echo -e "${YELLOW}Building operations agents...${NC}"
    for agent in services/ops/*/; do
        if [ -d "$agent" ]; then
            build_agent "$agent"
        fi
    done
fi

echo -e "${GREEN}✓ Agent build complete!${NC}"
echo "To install an agent, use:"
echo "  vctl install <path-to-wheel-file>"