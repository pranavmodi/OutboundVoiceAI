# Dev appointment simulator

Local-only mock of RadFlow scheduling data. **Not mounted when `BACKFILL_SIMULATOR_ENABLED=false`** (production default).

## Purpose

Exercise cancellation → campaign flow without RadFlow VPN or real patient feeds:

- Create/list facilities, patients, appointments
- Load or clear the Alice/Bob/Carol/Dave demo dataset
- Cancel an appointment (dev trigger — same engine as the RadFlow webhook)
- Delete appointment rows for cleanup

Production ingress is `POST /api/integrations/radflow/appointment-cancellations`. The simulator writes to the same `facilities`, `patients`, and `appointments` tables so candidate matching behaves the same locally.

## Layout

```
simulator/
├── api/           # FastAPI routers (facilities, patients, appointments, bootstrap)
├── fixtures/      # Demo seed data (demo_seed.py)
├── services/      # Delete/clear helpers
├── schemas.py     # Pydantic request/response models
└── router.py      # Mounted at /api/simulator when enabled
```

## API (dev only)

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/api/simulator/facilities` | List / create facilities |
| GET/POST | `/api/simulator/patients` | List / create patients |
| GET/POST | `/api/simulator/appointments` | List / book appointments |
| POST | `/api/simulator/appointments/{id}/cancel` | Dev cancel → campaign |
| DELETE | `/api/simulator/appointments/{id}` | Remove row + linked campaigns |
| POST | `/api/simulator/bootstrap/demo` | Seed demo scenario |
| POST | `/api/simulator/bootstrap/clear-demo` | Remove demo seed only |

Read-only `GET /api/facilities` stays on the main app for campaign UI filters (works with webhook-populated data too).

## Config

```bash
# backfill-backend/.env
BACKFILL_SIMULATOR_ENABLED=true   # false in production
```

## Frontend

- Appointment UI: `frontend-dev/` at `/dev/appointments` (port 3001)
- Hooks: `useAppointmentSimApi.ts` → `/api/simulator/...`
