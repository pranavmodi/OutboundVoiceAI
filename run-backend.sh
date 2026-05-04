#!/bin/bash
# Run the backend server
#
# Usage:
#   ./run-backend.sh              # production mode (no auto-reload)
#   ./run-backend.sh --dev        # development mode (auto-reload on file changes)
#   ./run-backend.sh --verbose    # enable verbose dispatcher/call logging

cd "$(dirname "$0")"

# Load .env if it exists (using set -a to preserve quotes in JSON values)
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Parse flags
RELOAD_FLAG=""
for arg in "$@"; do
    case "$arg" in
        --verbose) export VERBOSE_LOGGING=true ;;
        --dev) RELOAD_FLAG="--reload" ;;
    esac
done

BACKEND_PORT=${BACKEND_PORT:-8000}

# Tee stdout+stderr to logs/backend.log AND the terminal. Each run starts a
# new timestamped file; logs/backend.log is a symlink to the latest so
# `tail -f logs/backend.log` always tracks the current run.
mkdir -p logs
LOG_TS=$(date +%Y%m%d-%H%M%S)
LOG_FILE="logs/backend-${LOG_TS}.log"
ln -sfn "backend-${LOG_TS}.log" logs/backend.log

echo "Starting backend on http://localhost:$BACKEND_PORT"
echo "  Logging to: $LOG_FILE (symlink: logs/backend.log)"
[ "$VERBOSE_LOGGING" = "true" ] && echo "  Verbose logging enabled"
[ -n "$RELOAD_FLAG" ] && echo "  Dev mode (auto-reload) — DO NOT use during live calls"

source .venv/bin/activate
# Force unbuffered Python so logs flush in real time — otherwise print()
# stays in the stdout buffer until the process exits, breaking `tail -f`.
export PYTHONUNBUFFERED=1
uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT $RELOAD_FLAG --log-level warning 2>&1 | tee -a "$LOG_FILE"
