# Milestone 1 — Foundation, Data Model & Operator UI

**Status:** Planned  
**Target:** Campaign creation, candidate selection, settings, and read-only operator visibility — **no live SMS/voice outreach yet**  
**Spec:** [`cancellation-backfill-spec.md`](./cancellation-backfill-spec.md)  
**Architecture:** [`architecture.md`](./architecture.md) (independent `backfill-backend/` + shared frontend chrome)

---

## Goal

Deliver the **backbone** of the Cancellation Backfill Agent: persistent schema, agent settings, cancellation → campaign pipeline, candidate matching/ranking, and the **Campaigns** + **Settings** UI tabs. Operators can configure the agent and inspect campaigns/candidates/timeline; outreach is simulated or logged as system events only.

**Milestone 1 exit criteria:** An admin can trigger (or simulate) an eligible cancellation, see a campaign with ranked candidates (including excluded rows), change settings for the *next* campaign, and review an audit timeline — without sending real SMS or placing AI calls.

---

## In scope

| Area | Delivered in M1 |
|------|-----------------|
| DB | `BackfillCampaign`, `BackfillCandidate`, `BackfillActionLog`, `BackfillAgentSettings` (or equivalent) in **backfill DB** |
| Trigger | Eligibility check (≥ min notice hours), duplicate-campaign guard, campaign create/close |
| Candidates | Query, exclusions, deterministic ranking, `RankOrder` persistence |
| API | Settings CRUD, campaign list/detail, manual/dev cancellation trigger |
| UI | `/backfill` — **Campaigns** tab (list + detail) and **Settings** tab |
| Audit | `BackfillActionLog` rows for system events (created, candidates built, closed, manual stop stub) |
| Dev data | Local appointment/patient **projection** or fixture API (no cross-DB reads from outbound DB) |

## Out of scope (Milestone 2)

- Wave scheduler and delayed execution
- Real Twilio SMS / AI voice
- Inbound YES/NO handling and single-winner booking
- Business-hours / holiday **deferral** of waves (settings stored in M1; enforcement in M2)
- **Reports** tab and CSV export
- Appointment reschedule integration

---

## Current baseline (already done)

- [x] `backfill-backend/` FastAPI skeleton, health endpoint, separate Alembic env
- [x] `frontend/app/(agents)/backfill/page.tsx` placeholder + `useBackfillApi`
- [x] `AgentShell` nav; `/backfill` public in middleware
- [x] Local `backfill` database

---

## Architecture reminders

1. **No imports** from `app/` (outbound) into `backfill-backend/`.
2. Patient/appointment data: **HTTP API or replicated tables** in backfill DB — decide in Step 1.1.
3. Settings at campaign creation are **snapshotted** on `BackfillCampaign` (per spec: running campaigns unaffected by later edits).
4. Spec “shared platform” items (holidays, opt-out, Twilio) are **explicit integrations** — stub interfaces in M1, real wiring mostly in M2.

---

## Step-by-step implementation plan

### Phase 1 — Data & configuration (backend)

| Step | Task | Notes |
|------|------|--------|
| 1.1 | **Decision log** — document in `backfill-backend/README.md` or `docs/.../integrations.md`: patient/appointment source (fixture vs outbound HTTP vs RadFlow), auth model for backfill API | Unblocks candidate query |
| 1.2 | SQLAlchemy models: `BackfillCampaign`, `BackfillCandidate`, `BackfillActionLog` per spec field list | Use `architecture.md` DB, not `tenant_db` |
| 1.3 | Model: `BackfillAgentSettings` (single-row or versioned) mapping spec § Admin Settings | Defaults match spec table (24h notice, batch 3, delay 10, max waves 3, etc.) |
| 1.4 | Alembic revision `001_initial_backfill_schema` | Register models in `alembic/env.py` `target_metadata` |
| 1.5 | Pydantic schemas + repository/service layer for campaigns, candidates, logs, settings | Keep routers thin |
| 1.6 | Seed/dev script: sample facilities, patients, appointments for local candidate queries | Or sync job from fixture JSON |

### Phase 2 — Campaign lifecycle (backend)

| Step | Task | Notes |
|------|------|--------|
| 2.1 | `CampaignStatus` and `CandidateStatus` enums/constants aligned with spec § Status Model | Map to DB varchar/check constraints |
| 2.2 | **Trigger service** `evaluate_cancellation(appointment_id)` | Implements FR-1: notice hours, slot still open, no duplicate campaign |
| 2.3 | On eligible cancel: create `BackfillCampaign` (`Pending` → `Running` or stay `Pending` until M2), snapshot settings onto campaign row | Store `MinNoticeHoursApplied`, wave settings copies |
| 2.4 | **Candidate builder** `build_candidates(campaign_id)` | FR-2, FR-3, FR-4: facility + CPT match, exclusions, `ORDER BY ScheduledAppointmentDateTime DESC, AppointmentId ASC` |
| 2.5 | Persist `BackfillCandidate` rows with `RankOrder`, `EligibilityStatus`, `ExclusionReason` | Include excluded rows in DB (UI shows muted) |
| 2.6 | If zero eligible: set `ClosedNoCandidates`, write `BackfillActionLog` `CampaignClosed` | |
| 2.7 | **Idempotency**: unique constraint on `CancelledAppointmentId` + safe retry on duplicate trigger events | NFR: Reliability |
| 2.8 | `POST /api/dev/trigger-cancellation` (dev-only) or webhook stub `POST /api/events/appointment-cancelled` | For QA without RadFlow |
| 2.9 | `POST /api/campaigns/{id}/stop` — set `ClosedManually`, log action | UI button in M1; wave engine respects in M2 |

### Phase 3 — Read APIs & audit (backend)

| Step | Task | Notes |
|------|------|--------|
| 3.1 | `GET /api/campaigns` — list with filters (date range, facility, status, CPT, filled toggle), sort default `StartedAt` desc | Pagination |
| 3.2 | `GET /api/campaigns/{id}` — header fields + close reason + filled-by | |
| 3.3 | `GET /api/campaigns/{id}/candidates` — all candidates including excluded | |
| 3.4 | `GET /api/campaigns/{id}/timeline` — chronological `BackfillActionLog` | FR-12 partial: system events only in M1 |
| 3.5 | `GET /api/settings` / `PUT /api/settings` — agent settings | FR-11, FR-13; validate templates IDs nullable until M2 |
| 3.6 | `GET /api/agent/status` — enabled flag, health | For AgentShell inline status |
| 3.7 | Helper `log_action(campaign_id, candidate_id?, event_type, channel, outcome, payload?)` | Central audit writer |

### Phase 4 — Frontend shell (Campaigns + Settings)

| Step | Task | Notes |
|------|------|--------|
| 4.1 | Extend `useBackfillApi.ts`: campaigns, settings, agent status | No `useApi` imports |
| 4.2 | Replace placeholder `/backfill` with tab layout: **Campaigns** \| **Settings** (Reports tab disabled/“Coming in M2”) | Match spec § UI Requirements |
| 4.3 | **Campaigns list**: columns per spec (ID, facility, CPT, slot datetime, status badge, started/ended, filled by, close reason, actions) | Filters + sortable columns |
| 4.4 | **Campaign detail** route or drawer: header, candidate table, timeline | Excluded candidates muted |
| 4.5 | **Settings tab**: all M1 fields (agent toggle, trigger hours, wave defaults, contact window, holiday toggle, matching toggles, template dropdowns stub) | Unsaved-changes banner; save via PUT |
| 4.6 | Wire **Stop** on running campaigns to `POST .../stop` | |
| 4.7 | Types file `frontend/types/backfill.ts` — mirror API shapes | Isolated from outbound types |

### Phase 5 — Dry-run “wave preview” (optional but recommended)

| Step | Task | Notes |
|------|------|--------|
| 5.1 | `POST /api/campaigns/{id}/preview-next-wave` — returns who *would* be contacted (SMS batch + call targets) without sending | Helps QA before M2 |
| 5.2 | Log `CandidatesBuilt` and `WavePlanned` (dry-run) to `BackfillActionLog` | |

### Phase 6 — Testing & documentation

| Step | Task | Notes |
|------|------|--------|
| 6.1 | Backend unit tests: eligibility, exclusions, ranking, duplicate campaign | |
| 6.2 | API integration tests: trigger → list → detail → settings save | |
| 6.3 | Manual QA script in `docs/cancellation-backfill/developing-independently.md` — add M1 checklist | |
| 6.4 | Update `.env.example` files for any new backfill env vars | |

---

## API summary (Milestone 1)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Already exists |
| GET/PUT | `/api/settings` | Agent settings |
| GET | `/api/agent/status` | Enabled + version |
| GET | `/api/campaigns` | List + filters |
| GET | `/api/campaigns/{id}` | Detail |
| GET | `/api/campaigns/{id}/candidates` | Candidate table |
| GET | `/api/campaigns/{id}/timeline` | Action log |
| POST | `/api/dev/trigger-cancellation` | Dev trigger |
| POST | `/api/campaigns/{id}/stop` | Manual stop |
| POST | `/api/campaigns/{id}/preview-next-wave` | Optional dry-run |

---

## Acceptance criteria covered (spec)

| Scenario | M1 |
|----------|-----|
| 1 — Eligible cancellation (27h) | ✅ Campaign created |
| 2 — Ineligible cancellation (9h) | ✅ No campaign |
| 3 — Candidate selection (facility + CPT) | ✅ |
| 4 — No-show exclusion | ✅ |
| 5 — Ranking (farthest first) | ✅ |
| 6 — Business hours deferral | ⏳ M2 (settings UI only) |
| 7 — Single winner | ⏳ M2 |
| 8 — Shared UI / agent selection | ✅ Partial (Campaigns + Settings; Reports M2) |
| 9 — Full audit log | ✅ Partial (system events; SMS/call rows M2) |
| 10 — Settings saved without deployment | ✅ |

---

## Definition of done

- [ ] Migrations apply cleanly on local `backfill` DB
- [ ] Dev trigger creates campaign with ranked candidates per spec rules
- [ ] Duplicate trigger does not create second campaign
- [ ] Settings save and appear on **next** campaign snapshot
- [ ] `/backfill` Campaigns + Settings usable without outbound backend running
- [ ] No code imports from `app/` into `backfill-backend/`
- [ ] README/runbook updated for M1 QA steps

---

## Dependencies & risks

| Risk | Mitigation |
|------|------------|
| No real appointment feed | Fixtures + dev trigger API in M1 |
| Template library doesn’t exist in backfill service | Store template IDs as ints; validate in M2 when SMS goes live |
| Tie-break on same `ScheduledAppointmentDateTime` | Implement `AppointmentId ASC`; confirm with PM (spec open question #2) |

---

## Handoff to Milestone 2

M1 leaves campaigns in `Running` (or `Pending`) with candidates ready. M2 adds: wave worker, Twilio/voice, inbound responses, atomic winner, Reports tab, and full timeline with provider message IDs.

See [`milestone-2-outreach-and-completion.md`](./milestone-2-outreach-and-completion.md).
