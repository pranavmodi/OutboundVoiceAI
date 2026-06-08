# Cancellation Backfill — Implementation Log

Living record of what has been built in `backfill-backend/` and related docs.  
**Do not edit** [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md) — it is the frozen product spec.

---

## 2026-05-31 — Milestone 2 Step 1.1: Twilio integration decision

### Done

| Area | Decision |
|------|----------|
| **Account** | Shared Twilio account with outbound; credentials in `backfill-backend/.env` only |
| **Numbers** | Dedicated backfill SMS number — inbound webhooks on `backfill-backend`, not `app/` |
| **Inbound** | `POST {BACKFILL_PUBLIC_BASE_URL}/api/webhooks/sms/inbound` |
| **Status** | `POST {BACKFILL_PUBLIC_BASE_URL}/api/webhooks/sms/status` (optional) |
| **Local dev** | ngrok → `:8001`; set `BACKFILL_PUBLIC_BASE_URL` to tunnel HTTPS origin |
| **Security** | Require `X-Twilio-Signature` in staging/production |

### Files changed

- [`integrations.md`](./integrations.md) — Twilio section
- [`backfill-backend/.env.example`](../backfill-backend/.env.example) — commented Twilio vars

### Not done yet (by design)

- No `SmsProvider`, webhook routes, or wave engine code

### Next

- **M2 Step 1.2** — opt-out / suppression decision in `integrations.md`

---

## 2026-06-02 — Milestone 2 Phase 1 (Steps 1.2–1.6) foundations

### Done

| Area | Detail |
|------|--------|
| **Integrations decision log** | Added Step 1.2–1.6 decisions to [`integrations.md`](./integrations.md): suppression source, holiday strategy, appointment API contract, voice provider selection, and default toggles |
| **Suppression logic extraction** | Added `app/services/suppression_service.py` with centralized SMS suppression reason logic |
| **Candidate rules wiring** | `campaign_service._evaluate_row` now calls suppression service instead of inlining flags |
| **Test coverage** | Added unit tests for SMS opt-out and suppressed-patient exclusions in `tests/test_campaign_rules.py` |
| **Config surface** | Added M2 integration env config fields in `app/config.py` and `.env.example` |

### Files changed

- `docs/cancellation-backfill/integrations.md`
- `backfill-backend/app/services/suppression_service.py`
- `backfill-backend/app/services/campaign_service.py`
- `backfill-backend/tests/test_campaign_rules.py`
- `backfill-backend/app/config.py`
- `backfill-backend/.env.example`

### Not done yet (by design)

- No Twilio SMS provider code
- No voice provider implementation
- No inbound SMS/voice webhooks
- No wave engine scheduling
- No appointment booking client implementation

### Next

- **M2 Phase 2 Step 2.1** — background wave worker skeleton in `backfill-backend`

---

## 2026-06-02 — Milestone 2 Phase 2 Step 2.1: wave worker skeleton

### Done

| Area | Detail |
|------|--------|
| **Worker scaffold** | Added `WaveWorker` polling loop in `backfill-backend/app/services/wave_worker.py` |
| **Lifecycle wiring** | FastAPI lifespan now starts/stops worker when `BACKFILL_WAVE_WORKER_ENABLED=true` |
| **Campaign polling** | Worker queries `Running` campaigns ordered by start time |
| **Skeleton progression** | When wave is due, increments `last_wave_number`, updates `last_wave_at`, logs `WavePlanned` |
| **Stop condition (basic)** | Closes campaign as `ClosedMaxWavesReached` when wave limit reached |
| **Config flags** | Added worker envs: enabled, poll interval, batch size |
| **Tests** | Added helper tests for delay/max-wave scheduling logic (`tests/test_wave_worker.py`) |

### Files changed

- `backfill-backend/app/services/wave_worker.py`
- `backfill-backend/app/main.py`
- `backfill-backend/app/config.py`
- `backfill-backend/.env.example`
- `backfill-backend/tests/test_wave_worker.py`

### Not done yet (by design)

- No SMS dispatch
- No voice escalation
- No contact window / holiday gating in worker
- No inbound response handling / winner assignment

### Next

- **M2 Phase 2 Step 2.2** — contact window + holiday deferral (queue until allowed window)

---

## 2026-06-02 — Milestone 2 Phase 2 Step 2.2: contact window/holiday gating

### Done

| Area | Detail |
|------|--------|
| **Timezone-aware checks** | Worker now evaluates contact eligibility using `contact_window_timezone` |
| **Allowed days** | Parses `allowed_contact_days` and blocks outreach outside configured weekdays |
| **Contact window** | Enforces `contact_window_start`/`contact_window_end` before planning next wave |
| **Blackout dates** | Honors `agent_blackout_dates` in campaign settings snapshot |
| **Wave gating** | Wave planning now requires both “wave due” and “contact allowed now” |
| **Tests** | Added unit tests for weekday parsing, blackout parsing, and contact-window/blackout behavior |

### Files changed

- `backfill-backend/app/services/wave_worker.py`
- `backfill-backend/tests/test_wave_worker.py`

### Not done yet (by design)

- No persisted `next_wave_at` on campaign rows
- No shared holiday calendar adapter yet (`use_shared_holiday_calendar` remains intent/config)
- No outbound SMS/voice dispatch

### Next

- **M2 Phase 2 Step 2.3** — implement actual wave actions: SMS candidate selection + dispatch scaffold

---

## 2026-06-02 — Milestone 2 Phase 2 Step 2.3: SMS selection + dispatch scaffold

### Done

| Area | Detail |
|------|--------|
| **SMS provider interface** | Added `app/services/sms_provider.py` with safe mock `send_offer_sms()` returning synthetic provider IDs |
| **Wave actions** | Worker now selects top-ranked uncontacted eligible candidates per wave (`sms_batch_size_per_wave`) |
| **Contact state updates** | On send, candidate gets `wave_number_first_contacted`, `last_contacted_at`, `current_contact_status=TextSent` |
| **Suppression re-check** | Re-validates suppression and phone presence at send time; skips and marks invalid-contact when necessary |
| **Audit trail** | Writes `SmsSent`, `SmsSkipped`, and `SmsSendFailed` action logs with channel and wave metadata |
| **Pool exhaustion close** | If a planned wave sends 0 and no eligible uncontacted candidates remain, campaign closes as `ClosedExhausted` |

### Files changed

- `backfill-backend/app/services/sms_provider.py`
- `backfill-backend/app/services/wave_worker.py`
- `backfill-backend/tests/test_wave_worker.py`

### Not done yet (by design)

- No real Twilio SDK dispatch (mock provider only)
- No SMS template renderer from template IDs
- No inbound YES/NO handling yet
- No AI call escalation yet

### Next

- **M2 Phase 3 Step 3.1/3.3** — Twilio `SmsProvider` + inbound webhook (`/api/webhooks/sms/inbound`)

---

## 2026-06-02 — Milestone 2 Phase 3 Step 3.1/3.3: SMS provider + inbound webhook

### Done

| Area | Detail |
|------|--------|
| **Provider mode switch** | Added `BACKFILL_SMS_PROVIDER` (`mock`/`twilio`) and Twilio-backed send path in `sms_provider.py` |
| **Twilio SDK dependency** | Added `twilio` package in `backfill-backend/requirements.txt` |
| **Inbound webhook** | Added `POST /api/webhooks/sms/inbound` route with Twilio form parsing |
| **Signature validation** | Added optional `X-Twilio-Signature` validation (gated by `TWILIO_WEBHOOK_AUTH_ENABLED`) |
| **Status callback endpoint** | Added `POST /api/webhooks/sms/status` stub endpoint (accepted + logged shape) |
| **Inbound processing service** | Added `inbound_sms_service.py` for phone normalization, YES/NO parsing, campaign/candidate match, response updates |
| **Candidate response updates** | YES → `Interested`; NO/STOP → `Declined`; persists `response_at` + `current_contact_status` |
| **Audit wiring** | `log_action()` now supports `provider_message_id`; inbound events logged as `ResponseReceived` / `SmsInboundReceived` |
| **App routing** | Registered webhook router in `app/main.py` under `/api/webhooks/sms/*` |
| **Tests** | Added helper tests (`test_inbound_sms.py`) and webhook route tests (`test_sms_webhooks.py`) |

### Files changed

- `backfill-backend/app/config.py`
- `backfill-backend/.env.example`
- `backfill-backend/requirements.txt`
- `backfill-backend/app/services/sms_provider.py`
- `backfill-backend/app/services/inbound_sms_service.py`
- `backfill-backend/app/api/webhooks_sms.py`
- `backfill-backend/app/services/audit_service.py`
- `backfill-backend/app/services/wave_worker.py`
- `backfill-backend/app/main.py`
- `backfill-backend/tests/test_inbound_sms.py`
- `backfill-backend/tests/test_sms_webhooks.py`

### Not done yet (by design)

- No atomic single-winner slot assignment on YES yet (Phase 5)
- No delivery receipt reconciliation into existing `SmsSent` rows yet
- No closeout message behavior for late responses yet

### Next

- **M2 Phase 5 Step 5.1+** — response processor with atomic winner assignment / lost-slot handling

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
