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
exec uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT}"
