#!/bin/bash
# Run the backend server

cd "$(dirname "$0")"

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

BACKEND_PORT=${BACKEND_PORT:-8000}

echo "Starting backend on http://localhost:$BACKEND_PORT"

source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload --log-level warning


uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload --log-level warning