#!/bin/bash
# Script to run the Zettelkasten web application

set -e  # Exit on error

# Configuration
PORT=8000
HOST="127.0.0.1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    print_error "python3 is not installed or not in PATH"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
print_info "Using Python $PYTHON_VERSION"

# Check if port is already in use
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    print_warning "Port $PORT is already in use"

    # Get process info
    PIDS=$(lsof -Pi :$PORT -sTCP:LISTEN -t)
    print_warning "Found processes: $PIDS"

    # Ask user what to do
    read -p "Kill existing processes and restart? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Killing processes: $PIDS"
        kill $PIDS 2>/dev/null || true
        sleep 2
        print_info "Processes killed"
    else
        print_error "Cannot start server while port $PORT is in use"
        exit 1
    fi
fi

# Check if running in project directory
if [ ! -f "pyproject.toml" ]; then
    print_error "Must run from project root directory (where pyproject.toml is located)"
    exit 1
fi

# Check if package is installed
if ! python3 -c "import zettelkasten" 2>/dev/null; then
    print_warning "Package not installed. Installing in editable mode..."
    python3 -m pip install -e .
fi

# Check for .env file
if [ ! -f ".env" ]; then
    print_warning ".env file not found"
    if [ -f ".env.example" ]; then
        print_info "Consider copying .env.example to .env and adding your API key"
    fi
fi

# Start the server
print_info "Starting Zettelkasten web server on http://$HOST:$PORT"
print_info "Press Ctrl+C to stop the server"
echo

python3 -m uvicorn zettelkasten.web.app:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload
