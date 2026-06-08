# Cancellation Backfill — Integration Decisions

**Status:** M1 + RadFlow adopted (2026-05-28); **M2 Step 1.1 Twilio adopted (2026-05-31)**  
**Architecture:** [`architecture.md`](./architecture.md)  
**Implementation log:** [`implementation-log.md`](./implementation-log.md)

---

## Appointment & cancellation data

| Environment | Cancel event | Appointment / patient data |
|-------------|--------------|----------------------------|
| **Local dev / QA** | `POST /api/simulator/appointments/{id}/cancel` or RadFlow webhook | Tables in **backfill DB** — seed via `/api/simulator/bootstrap/demo` or webhook upsert |
| **Staging / production** | `POST /api/integrations/radflow/appointment-cancellations` | Webhook upserts canceled appointment; candidate pool from same DB (+ future RadFlow sync API) |

Backfill **does not** read the outbound caller database (`outboundvoice`) or import `app/` code.

---

## RadFlow cancellation webhook

| Item | Value |
|------|--------|
| Path | `POST /api/integrations/radflow/appointment-cancellations` |
| Auth | `Authorization: Bearer <RADFLOW_WEBHOOK_TOKEN>` |
| Idempotency | `X-RadFlow-Event-Id` (stable per event; retries must not duplicate campaigns) |
| Body | JSON — see [`fixtures/radflow-cancel-sample.json`](./fixtures/radflow-cancel-sample.json) |

Env vars: `RADFLOW_WEBHOOK_TOKEN`, `RADFLOW_WEBHOOK_ENABLED` (see `backfill-backend/.env.example`).

---

## Rationale

- Outbound `patients` table has orders and call state, not facility/CPT/scheduled exam/cancel status required by the spec.
- Local tables let us simulate cancellations and candidate matching without VPN or RadFlow.
- Dev REST cancel and RadFlow webhook both call the same campaign engine; production uses the webhook path.

---

## Twilio — SMS & voice (Milestone 2, Step 1.1)

### Decision summary

| Question | Decision | Rationale |
|----------|----------|-----------|
| Twilio **account** | **Shared** with outbound caller (same `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN`) | One org account; outbound already uses Twilio. Backfill reads credentials in **`backfill-backend/.env` only** — no imports from repo-root `app/`. |
| Twilio **phone numbers** | **Dedicated backfill SMS number** (separate E.164 from scheduling notifications) | YES/NO replies must route to backfill webhooks only. Avoids a shared-number dispatcher in outbound `app/`. |
| Inbound webhook **host** | **`backfill-backend`** (`:8001` locally) | Keeps the two-system boundary in [`architecture.md`](./architecture.md). Twilio console points at backfill URLs, not outbound. |
| Signature validation | **Required** in staging/production | Validate `X-Twilio-Signature` using `BACKFILL_PUBLIC_BASE_URL` + request path + POST body. Reject unsigned requests. |
| Local development | **ngrok (or similar) → `:8001`** | Twilio cannot reach `localhost`. Set `BACKFILL_PUBLIC_BASE_URL` to the tunnel HTTPS origin; use that URL in Twilio console. |

### Webhook URLs (Twilio console)

Replace `{BASE}` with the public HTTPS origin of this service (no trailing slash).

| Twilio setting | Method | URL |
|----------------|--------|-----|
| SMS number → **A MESSAGE COMES IN** | POST | `{BASE}/api/webhooks/sms/inbound` |
| Outbound SMS → **Status callback** (optional) | POST | `{BASE}/api/webhooks/sms/status` |
| Voice → status / disposition (Phase 4) | POST | `{BASE}/api/webhooks/voice/status` |

**Examples**

| Environment | `{BASE}` |
|-------------|----------|
| Local (ngrok) | `https://abc123.ngrok-free.app` |
| Staging | `https://backfill-staging.example.com` (from infra) |
| Production | `https://backfill.example.com` (from infra) |

RadFlow and Twilio share the same backfill host; paths differ (`/api/integrations/radflow/...` vs `/api/webhooks/sms/...`).

### Outbound SMS

- Send from **`TWILIO_SMS_FROM_NUMBER`** (dedicated backfill number).
- Include a **status callback** URL when implementing `SmsProvider` (M2 Phase 3) so delivery failures update `BackfillActionLog.outcome`.
- Message body comes from template settings (`allowed_sms_template_id` on campaign snapshot) — renderer in Phase 3.

### Inbound SMS → campaign / candidate

Twilio POST fields used later (Phase 3.3 / 5):

| Field | Use |
|-------|-----|
| `From` | Match `patients.phone` (normalize to E.164) |
| `Body` | Parse YES/NO variants → `ResponseProcessor` |
| `MessageSid` | Store on `BackfillActionLog.provider_message_id` |

**Resolution rules** (when multiple campaigns could match):

1. Prefer **Running** campaigns with a candidate for that patient where `current_contact_status` is `TextSent` or `CallPlaced`.
2. If multiple, pick most recent `last_wave_at`, then lowest `rank_order`.
3. Unparseable or orphan replies → log for ops review; no campaign update.

### Environment variables

Set in **`backfill-backend/.env`** (see `.env.example`). The outbound caller may define the same Twilio vars at repo root — copy values into backfill `.env` for local dev; do not import outbound code.

| Variable | Purpose |
|----------|---------|
| `TWILIO_ACCOUNT_SID` | Shared org account |
| `TWILIO_AUTH_TOKEN` | Shared org auth token |
| `TWILIO_SMS_FROM_NUMBER` | Dedicated E.164 for backfill offer SMS |
| `BACKFILL_PUBLIC_BASE_URL` | Public origin for signature validation + callbacks |
| `TWILIO_WEBHOOK_AUTH_ENABLED` | Optional extra gate (default off until webhooks exist) |

Voice-specific vars are documented in Step 1.5 when Phase 4 starts.

### Not in scope for Step 1.1 (later phases)

| Item | Phase |
|------|--------|
| `SmsProvider` / Twilio SDK | 3.1 |
| `POST /api/webhooks/sms/inbound` handler | 3.3 |
| Wave engine sending SMS | 2.x + 3.x |
| Changes to outbound `app/` Twilio routes | None planned |

---

## Milestone 2 — Phase 1 follow-up decisions (2026-06-02)

### Step 1.2 — Opt-out / suppression source

| Decision | Value |
|----------|-------|
| Source of truth (current) | Backfill DB patient projection flags (`patients.sms_opt_out`, `patients.suppressed`) |
| Selection behavior | Candidate is excluded before outreach with deterministic exclusion reason |
| Future upgrade path | Move to replicated suppression table or HTTP source behind a backfill-local service interface |

Notes:
- This keeps the system independent from outbound `app/` and allows immediate M2 work.
- Suppression checks must run both at candidate build time and before each outbound send in wave execution.

### Step 1.3 — Holiday calendar

| Decision | Value |
|----------|-------|
| M2 initial behavior | Respect `agent_blackout_dates` + contact-window day/time settings from `BackfillAgentSettings` |
| Shared holiday calendar toggle | Keep `use_shared_holiday_calendar` as config intent; implement adapter in wave scheduler phase |
| Data dependency | No direct DB coupling; shared holidays must come via replication or HTTP API |

### Step 1.4 — Appointment update (winner booking)

| Decision | Value |
|----------|-------|
| Integration style | External HTTP API called by backfill backend |
| Config | `BACKFILL_APPOINTMENT_API_BASE_URL`, `BACKFILL_APPOINTMENT_API_TOKEN` |
| Transaction boundary | Backfill winner assignment and remote appointment update coordinated by response processor |

### Step 1.5 — Voice provider

| Decision | Value |
|----------|-------|
| Initial adapter | Twilio Programmable Voice |
| Runtime selector | `BACKFILL_VOICE_PROVIDER` (default `twilio`) |
| Scope in Phase 1 | Decision + config only; implementation lands in Milestone 2 voice phase |

### Step 1.6 — Open defaults

| Item | Current default |
|------|-----------------|
| `late_response_closeout_enabled` | `true` (already in settings schema) |
| `campaign_timeout_minutes` | `null` (to be set per environment/policy) |
| Contact window timezone strategy | Existing global timezone setting (`contact_window_timezone`), revisit for per-facility support in M2 |

### Infra / mentor checklist

- [ ] Provision **staging** backfill SMS number
- [ ] Configure Twilio inbound + status URLs to `{BASE}/api/webhooks/sms/...`
- [ ] Confirm org policy: **shared account + dedicated number** (vs separate subaccount)
- [ ] Share staging `BACKFILL_PUBLIC_BASE_URL` with the team

---

## Production follow-ups

1. RadFlow appointment list / sync API for full candidate pool (webhook alone only upserts the canceled row).
2. Staging/production host URL and shared token from infra.
3. Opt-out and holiday data: replicate in backfill DB or fetch from a shared HTTP service (M2 Step 1.2).
4. Provision Twilio backfill SMS number + webhook URLs (M2 Step 1.1).
