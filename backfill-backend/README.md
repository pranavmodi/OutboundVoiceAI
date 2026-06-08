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

## Appointment data (dev vs production)

See [`../docs/cancellation-backfill/integrations.md`](../docs/cancellation-backfill/integrations.md).

- **Dev:** [`simulator/`](./simulator/) — mock CRUD + cancel at `/api/simulator/*` when `BACKFILL_SIMULATOR_ENABLED=true`
- **Prod / staging:** `POST /api/integrations/radflow/appointment-cancellations` (RadFlow webhook) — see [`../docs/cancellation-backfill/integrations.md`](../docs/cancellation-backfill/integrations.md)
- **Implementation log:** [`../docs/cancellation-backfill/implementation-log.md`](../docs/cancellation-backfill/implementation-log.md)

## Status (Milestone 1)

- [x] Schema, migrations, cancel → campaign + ranked candidates (later-scheduled only)
- [x] Settings API, campaigns list/detail/timeline/stop, agent status
- [x] Frontend `/backfill` — Campaigns + Settings tabs
- [x] RadFlow cancellation webhook + idempotency (`X-RadFlow-Event-Id`)
- [x] M2 Step 1.1 — Twilio integration decision ([`integrations.md`](../docs/cancellation-backfill/integrations.md) § Twilio)
- [ ] Milestone 2 — wave engine, SMS/voice, Reports (implementation)

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```
