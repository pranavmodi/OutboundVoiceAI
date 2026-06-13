#!/usr/bin/env bash
# Appointment simulator on port 3001 (separate from main dashboard on 3000)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/frontend-dev"

FRONTEND_DEV_PORT="${FRONTEND_DEV_PORT:-3001}"

# Load root .env safely (optional)
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -v '^#' "$ROOT/.env" | grep -E '^(NEXT_PUBLIC_BACKFILL_API_URL|NEXT_PUBLIC_BACKFILL_UI_URL|FRONTEND_DEV_PORT)=' || true)
  set +a
fi

if command -v ss >/dev/null 2>&1; then
  if ss -lntp 2>/dev/null | grep -q ":${FRONTEND_DEV_PORT} "; then
    echo "Port ${FRONTEND_DEV_PORT} is already in use."
    echo "Open http://localhost:${FRONTEND_DEV_PORT}/dev/appointments"
    echo "Or stop the other process and run this script again."
    exit 0
  fi
fi

if [ ! -d node_modules ]; then
  echo "Installing frontend-dev dependencies (first time)..."
  npm install --no-audit --no-fund
fi

echo "Starting appointment simulator on http://localhost:${FRONTEND_DEV_PORT}/dev/appointments"
echo "Backfill API: ${NEXT_PUBLIC_BACKFILL_API_URL:-http://localhost:8001}"
echo "Campaigns UI: ${NEXT_PUBLIC_BACKFILL_UI_URL:-http://localhost:3000}/backfill"
echo ""

exec env PORT="$FRONTEND_DEV_PORT" npm run dev
