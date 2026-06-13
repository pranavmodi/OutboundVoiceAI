# Milestone 2 — Outreach, Responses & Campaign Completion

**Status:** Planned  
**Prerequisite:** [Milestone 1 — Foundation](./milestone-1-foundation.md) complete  
**Target:** Wave-based SMS/voice outreach, inbound handling, single-winner booking, Reports tab, production integrations  
**Spec:** [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md)  
**Architecture:** [`architecture.md`](./architecture.md)

---

## Goal

Turn Milestone 1 campaigns from **planned** into **executed**: run configurable waves, send real (or staging) SMS and AI calls, process YES/NO responses with atomic single-winner enforcement, reschedule the winner’s appointment, and close campaigns with full audit + reporting.

**Milestone 2 exit criteria:** End-to-end flow from eligible cancellation through wave outreach to either `Filled` or a terminal closed status, with spec acceptance scenarios 6–9 and concurrency scenario 7 passing in QA.

---

## In scope

| Area | Delivered in M2 |
|------|-----------------|
| Waves | SMS batches, inter-wave delay, AI call escalation, stop conditions |
| Compliance | Contact window, allowed days, holiday/blackout deferral (queue, don’t skip) |
| Channels | Twilio SMS outbound + inbound; voice/AI call provider |
| Responses | YES → atomic winner; NO → declined; late → closeout message |
| Booking | Appointment update / reschedule integration (transactional) |
| UI | Reports tab, transcript links, raw payload expanders, wave indicators on timeline |
| Ops | Campaign timeout, agent enabled gate, provider message IDs on log rows |

## Out of scope (future)

- Temporary slot holding, overbooking, cross-facility, travel-time (spec § Out of Scope)
- Human scheduler approval gates
- Unified cross-agent reporting across outbound + backfill

---

## Step-by-step implementation plan

### Phase 1 — Integration decisions (before coding)

| Step | Task | Notes |
|------|------|--------|
| 1.1 | **Twilio:** shared account vs dedicated; inbound webhook URL and routing (spec architecture § Implications) | Document in `integrations.md` |
| 1.2 | **Opt-out / suppression:** replicate list in backfill DB vs poll outbound API | Must respect FR-5 / exclusions |
| 1.3 | **Holiday calendar:** own table vs HTTP fetch from outbound | Implement `HolidayService` interface |
| 1.4 | **Appointment updates:** which service/API performs atomic reschedule on win | Required for FR-8 |
| 1.5 | **AI calls:** provider choice (reuse OpenAI Realtime pattern vs new adapter) | Separate codebase — copy patterns, not imports |
| 1.6 | Resolve open spec decisions: late closeout toggle (#3), call targets same-wave vs all prior (#5), `CampaignTimeoutMinutes` default (#6), per-facility timezone (#7) | Record in decision log |

### Phase 2 — Wave engine (backend)

| Step | Task | Notes |
|------|------|--------|
| 2.1 | Background worker: asyncio loop, APScheduler, or ARQ — **runs inside `backfill-backend`** | Poll campaigns in `Running` |
| 2.2 | `WaveExecutor` — for campaign, if stop conditions false and within contact window → execute wave; else **queue until window opens** | FR-5, Scenario 6 |
| 2.3 | Wave steps per spec: (1) select top N uncontacted for SMS, (2) dispatch SMS, (3) wait `DelayBetweenWavesMinutes`, (4) AI-call 1–2 non-responders if enabled, (5) check stops, (6) increment `LastWaveNumber` | Default pattern § Outreach Strategy |
| 2.4 | Stop conditions: filled, pool exhausted, max waves, manual stop, slot invalid | |
| 2.5 | Update candidate: `WaveNumberFirstContacted`, `LastContactedAt`, `CurrentContactStatus` (`TextSent`, `CallPlaced`, etc.) | |
| 2.6 | Log every action to `BackfillActionLog` with `Channel`, `ProviderMessageId`, `Wave` | FR-10, FR-12 |
| 2.7 | **Messaging guardrails:** templates must not guarantee availability (FR-7) | Review copy with PM |
| 2.8 | Campaign timeout job — auto-close unfilled after `CampaignTimeoutMinutes` | Open decision #6 |

### Phase 3 — SMS (backend)

| Step | Task | Notes |
|------|------|--------|
| 3.1 | `SmsProvider` adapter (Twilio) — send templated message | Settings: `AllowedSmsTemplateId` |
| 3.2 | Template renderer: facility name, conditional language | |
| 3.3 | `POST /api/webhooks/sms/inbound` — parse YES/NO (and variants), map to campaign/candidate | Twilio signature validation |
| 3.4 | On inbound: invoke **response handler** (Phase 4) | |
| 3.5 | Delivery status callback webhook (optional) — update `Outcome` on log row | |

### Phase 4 — Voice / AI (backend)

| Step | Task | Notes |
|------|------|--------|
| 4.1 | `VoiceProvider` adapter — initiate outbound call to candidate | `AllowedVoiceTemplateId` |
| 4.2 | Call flow script per spec § Voice / AI Call Script Intent | Interest capture, no guarantee |
| 4.3 | Disposition webhook or post-call handler → `Interested` / `Declined` / `NoResponse` / `VoicemailLeft` | |
| 4.4 | Store `TranscriptId` / transcript blob reference on `BackfillActionLog` | FR-12 transcript panel |
| 4.5 | Link `AgentRunId` for traceability | Spec open decision #4 |

### Phase 5 — Response handling & single winner (backend)

| Step | Task | Notes |
|------|------|--------|
| 5.1 | `ResponseProcessor.handle_interest(candidate_id)` | FR-8 |
| 5.2 | **Atomic slot check** in DB transaction: `SELECT ... FOR UPDATE` on campaign/slot row; verify still open | Open decision #1 |
| 5.3 | If open: set `SelectedWinner`, call appointment service to reschedule, set `FilledByPatientId` / `FilledByAppointmentId`, campaign → `Filled`, **stop all waves** | |
| 5.4 | If closed: `LostSlot`, send closeout SMS if `LateResponseCloseoutEnabled` | Scenario 7 |
| 5.5 | If declined: `Declined`, no retry in campaign | |
| 5.6 | Concurrency test: two parallel YES → exactly one winner | Scenario 7 |
| 5.7 | Log `ResponseReceived`, `WinnerAssigned`, `CampaignClosed` events | |

### Phase 6 — Business rules enforcement (backend)

| Step | Task | Notes |
|------|------|--------|
| 6.1 | `ContactWindowService` — allowed days + start/end time + timezone (per facility if #7 resolved) | |
| 6.2 | `HolidayService` — shared calendar + agent blackout dates | |
| 6.3 | Integrate opt-out / suppression checks before each send | Spec exclusions table |
| 6.4 | When wave due outside window → schedule next run at window open (persist `next_wave_at` on campaign) | Do not skip wave |

### Phase 7 — Reports API & UI (backend + frontend)

| Step | Task | Notes |
|------|------|--------|
| 7.1 | `GET /api/reports/summary?from=&to=&facility=&status=&channel=` — metrics per spec § Reports Tab | |
| 7.2 | Metrics: created, filled, fill rate, avg time to fill, contacted, SMS sent, calls placed, response rates, fills by wave, close reasons | |
| 7.3 | `GET /api/reports/export.csv` | |
| 7.4 | Frontend **Reports** tab on `/backfill` — filters + metric cards + charts (simple tables OK for v1) | |
| 7.5 | Campaign detail: **Transcript** link on voice rows; **Raw payload** expandable (admin) | Spec § Campaign Detail |

### Phase 8 — Agent enable & polish (backend + frontend)

| Step | Task | Notes |
|------|------|--------|
| 8.1 | When `Enabled=false`, no new campaigns; running campaigns continue to completion | Spec § Agent Toggle |
| 8.2 | `AgentShell` — show backfill enabled/disabled from `GET /api/agent/status` | |
| 8.3 | Status badge colors on campaign list (Running=blue, Filled=green, Closed=gray, Error=red) | |
| 8.4 | Error path: `ClosedSystemError` + candidate `Error` with retry policy documented | |

### Phase 9 — End-to-end testing & hardening

| Step | Task | Notes |
|------|------|--------|
| 9.1 | Staging Twilio numbers + webhook tunnel (ngrok) documented | |
| 9.2 | Integration tests: wave progression (mock clock), stop conditions | |
| 9.3 | Load test: 10 concurrent campaigns, no duplicate winners | NFR Concurrency |
| 9.4 | QA runbook: full acceptance scenarios 1–10 | |
| 9.5 | Production readiness: secrets, CORS, `APP_*` auth if added for backfill API | |

---

## API summary (Milestone 2 additions)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/webhooks/sms/inbound` | Twilio inbound SMS |
| POST | `/api/webhooks/sms/status` | Delivery receipts (optional) |
| POST | `/api/webhooks/voice/*` | Call status / disposition |
| POST | `/api/campaigns/{id}/start-waves` | Optional manual start (if not auto on create) |
| GET | `/api/reports/summary` | Aggregates |
| GET | `/api/reports/export.csv` | CSV export |
| GET | `/api/campaigns/{id}/transcripts/{log_id}` | Transcript fetch |

---

## Acceptance criteria covered (spec)

| Scenario | M2 |
|----------|-----|
| 1–5 | ✅ Verified end-to-end with real channels |
| 6 — Business hours | ✅ |
| 7 — Single winner | ✅ |
| 8 — Shared UI | ✅ Full (incl. Reports) |
| 9 — Full audit log | ✅ SMS, calls, responses in timeline |
| 10 — Settings | ✅ Already M1; verify wave delay change on new campaigns |

---

## Functional requirements mapping

| ID | M2 delivery |
|----|-------------|
| FR-5 | Contact window, holidays, quiet-hour deferral |
| FR-6 | Wave SMS + optional AI calls |
| FR-7 | Conditional messaging in templates |
| FR-8 | Single winner + atomic booking |
| FR-10 | Full logging with provider IDs |
| FR-12 | Complete timeline + transcript |

---

## Definition of done

- [ ] Eligible cancellation → waves run → SMS/call logs appear in timeline
- [ ] First YES assigns winner, closes campaign, stops other outreach
- [ ] Second simultaneous YES gets `LostSlot` + closeout when enabled
- [ ] Waves respect delay, max waves, contact window, holidays
- [ ] Manual stop halts further waves
- [ ] Reports tab shows accurate aggregates for test date range
- [ ] CSV export works
- [ ] Staging/demo documented in `developing-independently.md`
- [ ] No regression to outbound caller dashboard at `/`

---

## Suggested implementation order (critical path)

```text
Integrations decided → Wave engine skeleton → SMS send → Inbound SMS →
Winner transaction → Voice escalation → Contact window/holidays →
Reports UI → E2E QA
```

---

## Milestone split rationale

| Milestone | Operator value | Engineering risk |
|-----------|----------------|------------------|
| **M1** | See and configure campaigns; validate matching rules without Twilio | Low — CRUD + rules |
| **M2** | Production outreach and revenue-impacting booking | High — concurrency, webhooks, scheduling |

Delivering M1 first de-risks data model and UI while parallel work can proceed on integration contracts (Twilio, appointment API).
