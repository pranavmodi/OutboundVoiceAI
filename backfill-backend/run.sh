#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${BACKFILL_BACKEND_PORT:-8001}"
echo "Starting backfill-backend on http://localhost:${PORT}"

if [ ! -x .venv/bin/uvicorn ]; then
  echo "Error: .venv not found or uvicorn not installed. Run:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

exec .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT}"
