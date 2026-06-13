# Cancellation Backfill — Implementation Log

Living record of what has been built in `backfill-backend/` and related docs.  
**Do not edit** [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md) — it is the frozen product spec.

---

## 2026-05-28 — RadFlow cancellation webhook

### Done

| Area | Detail |
|------|--------|
| **Endpoint** | `POST /api/integrations/radflow/appointment-cancellations` |
| **Auth** | `Authorization: Bearer <RADFLOW_WEBHOOK_TOKEN>` |
| **Idempotency** | `X-RadFlow-Event-Id` header → `backfill_inbound_events.radflow_event_id` (unique); retries return stored JSON response |
| **Payload** | Pydantic model `RadflowCancellationEvent` — required fields per RadFlow contract |
| **Upsert** | `facilities`, `patients`, `appointments` by `external_id` (RadFlow `FAC-*`, `PAT-*`, `APT-*`) |
| **Campaign** | Reuses `cancel_appointment_and_maybe_campaign()` — same rules as dev `POST /api/simulator/appointments/{id}/cancel` |
| **Migration** | `b8f2a1c90d4e_radflow_webhook_external_ids` — `external_id` columns, `procedure_description`, `backfill_inbound_events` |
| **Config** | `RADFLOW_WEBHOOK_TOKEN`, `RADFLOW_WEBHOOK_ENABLED` in `.env` |
| **Fixture** | [`fixtures/radflow-cancel-sample.json`](./fixtures/radflow-cancel-sample.json) |
| **Docs** | [`integrations.md`](./integrations.md), [`developing-independently.md`](./developing-independently.md) (webhook curl section) |

### Files added / changed

- `backfill-backend/app/api/integrations/radflow.py`
- `backfill-backend/app/services/radflow_webhook_service.py`
- `backfill-backend/app/schemas/radflow.py`
- `backfill-backend/app/models/inbound_event.py`
- `backfill-backend/app/models/appointment_data.py` (external IDs)
- `backfill-backend/alembic/versions/b8f2a1c90d4e_radflow_webhook_external_ids.py`
- `backfill-backend/tests/test_radflow_webhook.py`

### Response `status` values

| status | Meaning |
|--------|---------|
| `campaign_created` | Eligible cancel; campaign created (may be closed with no candidates) |
| `campaign_exists` | Campaign already existed for this appointment |
| `ineligible` | Inside minimum notice window (no new campaign) |
| `agent_disabled` | Agent off; appointment recorded canceled, no campaign |
| `ignored_event_type` | `eventType` ≠ `appointment.cancelled` |

### Local test

```bash
cd backfill-backend
# Apply migration once
.venv/bin/alembic upgrade head

# Set token in .env: RADFLOW_WEBHOOK_TOKEN=dev-secret

curl -sS -X POST "http://localhost:8001/api/integrations/radflow/appointment-cancellations" \
  -H "Authorization: Bearer dev-secret" \
  -H "Content-Type: application/json" \
  -H "X-RadFlow-Event-Id: evt_dev_001" \
  -d @../docs/cancellation-backfill/fixtures/radflow-cancel-sample.json
```

Repeat the same `X-RadFlow-Event-Id` — response should match the first call (idempotent).

Dev UI cancel (`POST /api/simulator/appointments/{id}/cancel`) lives under [`backfill-backend/simulator/`](../backfill-backend/simulator/) — disabled when `BACKFILL_SIMULATOR_ENABLED=false`.

---

## 2026-05-28 — Dev simulator package

Moved all mock appointment/patient CRUD from `app/api/` into `backfill-backend/simulator/`:

| Area | Detail |
|------|--------|
| **Mount** | `/api/simulator/*` when `BACKFILL_SIMULATOR_ENABLED=true` |
| **Contents** | facilities/patients/appointments CRUD, bootstrap demo, dev cancel, delete |
| **Production** | Set `BACKFILL_SIMULATOR_ENABLED=false`; use RadFlow webhook only |
| **Read API** | `GET /api/facilities` remains on main app for campaign filters |

See [`backfill-backend/simulator/README.md`](../backfill-backend/simulator/README.md).

### Not done yet

- RadFlow appointment **sync API** (populate candidate pool beyond webhook upserts)
- Staging/production host + token from infra
- Optional: point dev simulator at webhook instead of `/cancel`

---

## Earlier — Milestone 1 foundation (summary)

Already in place before the webhook:

- Backfill DB schema: campaigns, candidates, action logs, agent settings
- Dev appointment projection: facilities, patients, appointments
- Cancel → campaign + ranked candidates (`campaign_service.py`)
- APIs: settings, campaigns list/detail/candidates/timeline/stop, bootstrap demo
- Frontend `/backfill`: Campaigns + Settings tabs
- Unit tests: candidate eligibility rules (`tests/test_campaign_rules.py`)

---

## How to update this log

When you ship a feature, add a dated section with **Done**, **Files**, and **Not done yet**. Keep entries factual and short.
