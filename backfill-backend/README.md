# Cancellation Backfill Backend

Independent backend service for the Cancellation Backfill Agent.

Architecture decision: [`../docs/cancellation-backfill/architecture.md`](../docs/cancellation-backfill/architecture.md). Spec: [`../docs/cancellation-backfill/cancellation-backfill-spec.md`](../docs/cancellation-backfill/cancellation-backfill-spec.md). Dev runbook (run `/backfill` without the outbound caller): [`../docs/cancellation-backfill/developing-independently.md`](../docs/cancellation-backfill/developing-independently.md).

## Boundaries

This service is **independent** of the outbound caller at the repo root. It does not import from `../app/`, share Alembic history with `../alembic/`, or connect to the outbound caller's database. The only deliberate coupling is at the frontend layer (`../frontend/`), which hosts both agent UIs.

## Running locally

```bash
cd backfill-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit
./run.sh
```

The service listens on `BACKFILL_BACKEND_PORT` (default `8001`) so it doesn't collide with the outbound caller on `8000`.

## Health check

```
GET /api/health → {"status": "ok", "service": "backfill-backend"}
```

## Status

Skeleton only. Domain code (campaigns, candidates, action log, wave scheduler, inbound SMS handling) is not yet implemented — see the spec for scope.
