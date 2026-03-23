#!/bin/bash
# Run the backend server

cd "$(dirname "$0")"

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --verbose) export VERBOSE_LOGGING=true ;;
    esac
done

BACKEND_PORT=${BACKEND_PORT:-8000}

echo "Starting backend on http://localhost:$BACKEND_PORT"
if [ "$VERBOSE_LOGGING" = "true" ]; then
    echo "Verbose logging enabled"
fi

source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload --log-level warning
