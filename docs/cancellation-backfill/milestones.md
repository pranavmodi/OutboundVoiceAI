# Cancellation Backfill — Implementation Milestones

**Spec:** [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md)  
**Architecture:** [`architecture.md`](./architecture.md) (independent backend + shared frontend)

This feature is split into **two milestones** so the team can ship operator-visible value early, then add high-risk outreach and booking logic.

---

## Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Milestone 1 — Foundation                                               │
│  DB · Settings · Trigger · Candidates · Campaigns UI · Settings UI      │
│  (no live SMS/voice)                                                    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Milestone 2 — Outreach & Completion                                    │
│  Waves · Twilio/voice · Inbound · Winner booking · Reports              │
└─────────────────────────────────────────────────────────────────────────┘
```

| | Milestone 1 | Milestone 2 |
|---|-------------|-------------|
| **Theme** | Plan & observe | Execute & complete |
| **Backend** | Models, APIs, candidate engine, audit (system events) | Wave worker, SMS/voice, webhooks, atomic winner |
| **Frontend** | Campaigns + Settings tabs | Reports tab, transcripts, payloads |
| **DB** | `backfill` — initial migration | Migrations for wave state, webhooks, indexes |
| **Integrations** | Fixtures / dev trigger | Twilio, appointment API, holidays, opt-out |
| **Spec scenarios** | 1–5, 8 (partial), 9 (partial), 10 | 6–9 (full), 1–5 E2E with real channels |

---

## Detailed plans

| Document | Description |
|----------|-------------|
| [**Milestone 1 — Foundation**](./milestone-1-foundation.md) | Step-by-step: schema, trigger, candidates, APIs, Campaigns/Settings UI |
| [**Milestone 2 — Outreach & Completion**](./milestone-2-outreach-and-completion.md) | Step-by-step: waves, SMS/voice, responses, winner, Reports |

---

## Cross-cutting rules (both milestones)

1. **Boundaries:** `backfill-backend/` only — no imports from `app/`. Frontend uses `useBackfillApi`, not `useApi`, for backfill pages.
2. **Databases:** `BACKFILL_DATABASE_URL` → `backfill` DB; outbound uses `DATABASE_URL` → `outboundvoice`.
3. **Settings:** Changes apply to **new** campaigns only; snapshot settings on `BackfillCampaign` at creation.
4. **UI:** Outbound dashboard at `/` stays frozen; backfill lives at `/backfill` under `AgentShell`.
5. **Auth:** `/backfill` is public in middleware today; add backfill API auth in M2 if required for production.

---

## Suggested timeline (indicative)

| Milestone | Rough effort | Depends on |
|-----------|--------------|------------|
| M1 | 2–3 weeks | Appointment data source decision |
| M2 | 3–5 weeks | Twilio + appointment API contracts |

Adjust after M1 integration spike (Phase 1.1).

---

## QA entry points

- **M1:** `POST /api/dev/trigger-cancellation` + `/backfill` Campaigns/Settings  
- **M2:** Staging Twilio + full cancellation → fill flow  

Runbook: [`developing-independently.md`](./developing-independently.md)

---

## Version history

| Version | Date | Notes |
|---------|------|--------|
| 1.0 | 2026-05-19 | Initial milestone split from spec v1.0 |
