# Cancellation Backfill — Integration Decisions

**Status:** Adopted for Milestone 1 local development + RadFlow webhook (2026-05-28)  
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

## Production follow-ups

1. RadFlow appointment list / sync API for full candidate pool (webhook alone only upserts the canceled row).
2. Staging/production host URL and shared token from infra.
3. Opt-out and holiday data: replicate in backfill DB or fetch from a shared HTTP service.
