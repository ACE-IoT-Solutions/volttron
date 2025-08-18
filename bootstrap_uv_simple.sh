#!/usr/bin/env bash
# Simplified UV-based VOLTTRON Bootstrap Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}VOLTTRON UV Bootstrap Script (Simplified)${NC}"
echo "=========================================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | sed -n 's/Python \([0-9]*\.[0-9]*\).*/\1/p')
echo -e "${GREEN}✓ Python $PYTHON_VERSION detected${NC}"

# Create virtual environment with UV
echo -e "${YELLOW}Creating virtual environment...${NC}"
uv venv --python python3.10 .venv

# Activate virtual environment
source .venv/bin/activate

echo -e "${GREEN}✓ Virtual environment created${NC}"

# Install base dependencies directly (not using pyproject.toml)
echo -e "${YELLOW}Installing base dependencies...${NC}"

# Install core packages first
uv pip install wheel setuptools

# Install VOLTTRON dependencies from requirements.py
uv pip install \
    'gevent==24.2.1' \
    'grequests==0.7.0' \
    'requests==2.31.0' \
    'idna<3,>=2.5' \
    'ply==3.11' \
    'psutil==5.9.1' \
    'python-dateutil==2.8.2' \
    'pytz==2022.1' \
    'PyYAML==6.0' \
    'setuptools>=40.0.0,<=70.0.0' \
    'tzlocal==2.1' \
    'cryptography==37.0.4' \
    'watchdog<5.0' \
    'watchdog-gevent==0.1.1' \
    'deprecated==1.2.14'

# Install ZMQ with bundled option
echo -e "${YELLOW}Installing ZMQ with bundled libraries...${NC}"
uv pip install 'pyzmq==26.0.2' --config-settings="--zmq=bundled"

# Install optional dependencies based on arguments
for arg in "$@"; do
    case $arg in
        --databases)
            echo -e "${YELLOW}Installing database dependencies...${NC}"
            uv pip install \
                'mysql-connector-python==8.0.30' \
                'pymongo==4.5.0' \
                'crate==0.27.1' \
                'influxdb==5.3.1' \
                'psycopg2-binary==2.9.7'
            ;;
        --drivers)
            echo -e "${YELLOW}Installing driver dependencies...${NC}"
            uv pip install \
                'pymodbus==2.5.3' \
                'bacpypes==0.16.7' \
                'modbus-tk==1.1.2' \
                'pyserial==3.5'
            ;;
        --testing)
            echo -e "${YELLOW}Installing testing dependencies...${NC}"
            uv pip install \
                'mock==4.0.3' \
                'pytest==7.1.2' \
                'pytest-timeout==2.1.0' \
                'pytest-rerunfailures==10.2' \
                'websocket-client==1.2.2' \
                'deepdiff==5.8.1' \
                'docker==5.0.3' \
                'pytest-asyncio==0.19.0'
            ;;
        --web)
            echo -e "${YELLOW}Installing web dependencies...${NC}"
            uv pip install \
                'ws4py==0.5.1' \
                'PyJWT==1.7.1' \
                'Jinja2==3.1.2' \
                'passlib==1.7.4' \
                'argon2-cffi==21.3.0' \
                'Werkzeug==2.2.1' \
                'treelib==1.6.1'
            ;;
        --all)
            echo -e "${YELLOW}Installing all optional dependencies...${NC}"
            # Install all groups
            $0 --databases --drivers --testing --web
            exit 0
            ;;
        --dev)
            echo -e "${YELLOW}Installing development dependencies...${NC}"
            uv pip install ruff black mypy pytest pytest-cov
            ;;
    esac
done

# Now install VOLTTRON in development mode
echo -e "${YELLOW}Installing VOLTTRON in development mode...${NC}"
uv pip install -e .

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