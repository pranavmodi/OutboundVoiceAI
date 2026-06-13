#!/usr/bin/env bash
# Start both frontends: appointment simulator (:3001) + operator UI (:3000)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DEV_PORT="${FRONTEND_DEV_PORT:-3001}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

cleanup() {
  [ -n "${SIM_PID:-}" ] && kill "$SIM_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting appointment simulator on :${FRONTEND_DEV_PORT}..."
"$ROOT/run-frontend-dev.sh" &
SIM_PID=$!

echo "Waiting for simulator to bind :${FRONTEND_DEV_PORT}..."
for _ in $(seq 1 45); do
  if curl -sf -o /dev/null "http://127.0.0.1:${FRONTEND_DEV_PORT}/dev/appointments" 2>/dev/null; then
    break
  fi
  sleep 1
done

echo ""
echo "  Simulator:  http://localhost:${FRONTEND_DEV_PORT}/dev/appointments"
echo "  Campaigns:  http://localhost:${FRONTEND_PORT}/backfill"
echo ""

cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install --no-audit --no-fund
fi

exec env PORT="$FRONTEND_PORT" npm run dev
