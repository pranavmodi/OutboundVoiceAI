# Cancellation Backfill Agent Analysis: Fit with Existing Platform

This document analyzes the AI Cancellation Backfill Agent specification against the existing OutboundVoiceAI application, identifies what infrastructure exists versus what must be built, and evaluates the integration approach.

---

## 1. Current App Functionality (Recap)

The OutboundVoiceAI app is a **single-purpose, single-agent outbound calling system** for Precise Imaging. It:

1. **Polls FreePBX** every 10 seconds. When the scheduling queue is below threshold, selects the next eligible patient and dials them.
2. **Runs a voice AI conversation** (OpenAI Realtime or Gemini Live) to check if the patient is available to schedule, then transfers to a human scheduler or sends SMS follow-up.
3. **Tracks attempts** per patient with per-status max attempts (Ordered / No Show / Needs to Reschedule), cooldowns, and HL7 write-back on exhaustion.
4. **Integrates with RadFlow360** for patient data (polling) and outcome reporting (POST).
5. **Enforces business rules**: business hours with timezone and holidays, queue gating with 3-poll stability, language-based agent availability, 1-concurrent-call limit, per-patient cooldowns.
6. **Provides a dashboard** with queue state, active call transcript, call history, dispatcher decisions, KPIs, and audit log.

**Tech stack**: FastAPI + Next.js + PostgreSQL + Twilio + OpenAI Realtime / Gemini Live + WebSockets. Custom async dispatcher loop — no Temporal, no distributed task queue.

---

## 2. How the Backfill Spec Relates to the Existing App

Unlike the v2 intake agent spec (which extends the existing call flow with additional conversation phases), the backfill agent is a **fundamentally different workflow** that shares infrastructure but not flow logic.

### What's Similar (Shared Infrastructure)

| Capability | Current App | Backfill Agent |
|-----------|-------------|----------------|
| Outbound SMS sending | Yes — voicemail/callback notifications | Yes — wave-based offer messages |
| Outbound voice calls | Yes — scheduling confirmation | Yes — escalation calls to non-responders |
| Voice AI conversation | Yes — OpenAI/Gemini | Yes — different script, same providers |
| Business hours enforcement | Yes — timezone-aware with holidays | Yes — must reuse same rules |
| Call logging and audit | Yes — CallLogRow + AuditEventRow | Yes — must log to same system |
| Dashboard and UI | Yes — queue, history, KPIs | Yes — must appear in same admin plane |
| Twilio integration | Yes — voice + SMS | Yes — same provider |
| Patient data | Yes — patients table | Partially — needs appointment-level data |
| Settings management | Yes — DB-backed SystemSettings | Yes — needs per-agent extension |

### What's Fundamentally Different

| Aspect | Current App (Scheduling Agent) | Backfill Agent |
|--------|-------------------------------|----------------|
| **Trigger** | Polling loop on a timer (every 10s) | Event-driven: appointment cancellation |
| **Goal** | Get patient to a human scheduler | Fill a specific open slot with a different patient |
| **Patient selection** | Priority queue of all pending patients | Targeted: same facility + same CPT code as canceled slot |
| **Outreach pattern** | One patient at a time, sequential | Wave-based: SMS batch of 3, then escalate calls, repeat |
| **SMS direction** | Outbound only (fire-and-forget) | Two-way: send offer, receive YES/NO reply |
| **Concurrency** | 1 active call, no parallel outreach | Multiple patients contacted simultaneously per campaign |
| **State model** | Per-patient attempt tracking | Per-campaign with candidate pool, waves, winner selection |
| **Completion** | Transfer to scheduler or exhaust attempts | Atomic slot assignment to single winner |
| **Timing** | Immediate dispatch when queue allows | Scheduled waves with configurable delays between them |
| **Data model** | Patient + Order (no appointment details) | Appointment-centric: datetime, facility, CPT code |

---

## 3. Gap Analysis: What Exists vs. What Must Be Built

### 3.1 Infrastructure That Exists and Can Be Reused

**Twilio voice + SMS sending** — The `TwilioVoiceService` and `TwilioSmsService` handle outbound calls and SMS. The backfill agent can reuse the same Twilio account, phone numbers, and sending logic. SMS template rendering would need to be added, but the transport layer is ready.

**Voice AI services** — OpenAI Realtime and Gemini Live integrations are provider-agnostic enough to run a different conversation script. The `BaseVoiceService` interface, audio transcoding (mulaw/PCM), and WebSocket streaming infrastructure all carry over.

**Business hours and holiday enforcement** — `SettingsProvider.is_within_business_hours()` checks timezone-aware hours and holiday lists. The backfill agent can call this directly to suppress outreach outside allowed windows.

**Call logging and audit trail** — `CallLogRow` stores complete call records (outcome, transcript, duration, recording). `AuditEventRow` logs every external API call. Both are reusable for backfill calls, though campaign association fields would need to be added.

**Dashboard framework** — The Next.js dashboard with tabs, cards, and WebSocket real-time updates provides the shell for backfill campaign views. The `CallHistoryCard` filtering pattern (date range, status, search) can be adapted for campaign filtering.

**Database and ORM patterns** — SQLAlchemy async models, Alembic migrations, provider pattern for data access — all reusable.

**Settings API pattern** — The `POST /api/settings/*` endpoints and `SettingsProvider` CRUD pattern can be extended for agent-specific settings.

**Contact suppression (basic)** — SMS opt-out detection (Twilio error 21610) and invalid-number tracking exist, though the implementation is minimal (env var-based opt-out list).

### 3.2 Infrastructure Gaps — Must Be Built

#### Gap 1: No Agent-Type Abstraction
**Current state**: The entire system is hardcoded around a single agent purpose. `SystemSettings`, `DispatcherSettings`, `CallOrchestrator`, and the dispatcher loop all assume one type of outbound activity.

**What's needed**: An agent-type layer that allows multiple independent agents to coexist, each with its own settings, dispatch logic, candidate selection, and conversation script, while sharing business hours, Twilio, logging, and the dashboard.

**Impact**: This is the most architecturally significant gap. Every major component — dispatcher, settings, patient provider, call orchestrator, dashboard — needs to become agent-type-aware.

#### Gap 2: No Appointment Data Model
**Current state**: The system knows patients and orders (`patient_id`, `order_id`, `order_created`, `due_by`, `radflow_status`). It has no concept of specific appointments, facilities, CPT codes, or exam datetimes.

**What's needed**: Appointment-level data including `appointment_datetime`, `facility_id`, `facility_name`, `cpt_code`, `appointment_status`, `cancellation_datetime`. Either extend `PatientRow` or create a separate `AppointmentRow` table (recommended, since one patient can have multiple appointments).

**Impact**: Requires new data model, new RadFlow integration to fetch appointment details, and new candidate matching queries.

#### Gap 3: No Inbound SMS Handling
**Current state**: SMS is strictly outbound. The system sends notifications but cannot receive or process replies. No Twilio inbound SMS webhook exists.

**What's needed**: 
- Twilio inbound SMS webhook endpoint (`POST /api/twilio/sms-inbound`)
- Message parsing logic to detect YES/NO/interest responses
- Campaign-to-candidate resolution from inbound phone number
- Reply tracking and state updates
- Graceful closeout messages for late responders

**Impact**: This is a net-new capability. The current SMS service has zero infrastructure for two-way messaging.

#### Gap 4: No Campaign / Batch Concept
**Current state**: The system processes patients individually through a sequential dispatcher. There is no concept of grouped outreach, campaigns, or cohorts.

**What's needed**: Full campaign data model — `BackfillCampaign`, `BackfillCandidate`, `BackfillActionLog` as specified. Campaign lifecycle management (create, run, close). Candidate pool building with eligibility evaluation and ranking.

**Impact**: Entirely new domain model and service layer. Nothing in the current codebase maps to this.

#### Gap 5: No Wave-Based / Scheduled Outreach
**Current state**: The dispatcher immediately calls the next eligible patient when gating conditions pass. No concept of "send SMS to 3 people, wait 10 minutes, then do the next wave."

**What's needed**: A wave execution engine that:
- Sends SMS batches of configurable size
- Waits configurable delays between waves
- Escalates non-responders to voice calls
- Tracks wave number and timing per candidate
- Stops on fill, exhaustion, or manual cancel

**Impact**: Requires a new scheduler/timer mechanism. The existing dispatcher's 10-second polling loop is not suitable — waves need precise timing and multi-candidate parallel outreach.

#### Gap 6: No Event-Driven Trigger
**Current state**: The system is entirely polling-based. The dispatcher polls FreePBX every 10 seconds and RadFlow on each candidate selection. No external events trigger actions.

**What's needed**: A cancellation event receiver — either:
- Webhook endpoint that RadFlow/scheduling system calls on cancellation
- Polling endpoint that checks for recent cancellations periodically
- Message queue consumer (if the scheduling system publishes events)

The trigger must evaluate the 24-hour eligibility rule and create campaigns automatically.

**Impact**: New integration pattern. The current app never reacts to external events in real time.

#### Gap 7: No Atomic Booking / Concurrency Control
**Current state**: Minimal concurrency control. The dispatcher uses an in-memory asyncio lock for SMS deduplication. No database-level locking, no optimistic concurrency, no transaction isolation for critical operations.

**What's needed**: Atomic single-winner enforcement when multiple patients respond simultaneously. Requires database-level guarantees — `SELECT ... FOR UPDATE`, row versioning, or equivalent — to ensure exactly one patient gets the slot.

**Impact**: Requires adding transactional locking patterns to the data access layer. The current codebase has no precedent for this.

#### Gap 8: No Per-Agent Settings
**Current state**: `SystemSettings` is a flat dataclass with fixed fields. `DispatcherSettings` controls the single dispatcher globally. Adding new settings requires code changes across model, DB, API, and provider.

**What's needed**: Per-agent settings that layer on top of shared global settings. The backfill agent needs its own: enabled flag, min notice hours, SMS batch size, call escalation toggle, wave delay, max waves, etc. — independent from the scheduling agent's settings.

**Impact**: Requires either a new `AgentSettings` table keyed by agent type, or a JSONB extension to the existing settings model.

#### Gap 9: No Campaign UI
**Current state**: The dashboard shows patient queue, active call, call history, dispatcher events, KPIs, and audit log — all for the single scheduling agent.

**What's needed**: Campaign list view, campaign detail view (candidates, timeline, actions, outcome), agent-type filter across all existing views, and a backfill-specific settings panel. The spec requires all of this within the existing dashboard, not a separate admin interface.

**Impact**: Significant frontend work — new pages/tabs, new API endpoints, new data fetching hooks.

---

## 4. Integration Assessment

The spec explicitly mandates integration: "This feature must be built as a production-grade agent inside the existing outbound AI platform, not as a separate workflow or standalone service." This is the right call, but the gap between the current single-agent architecture and a multi-agent platform is substantial.

### Why Integration Is Correct

1. **Shared business rules are the hard part.** Business hours, holidays, quiet hours, opt-out enforcement, contact suppression — duplicating these guarantees correctness drift. A separate app would inevitably diverge.
2. **Unified operational view.** Operators need one dashboard showing all AI outreach activity. Two systems means two places to check, two audit trails to correlate, two sets of logs to search.
3. **Shared Twilio resources.** Both agents use the same phone numbers, same SMS sender ID, same Twilio account. Two apps competing for the same Twilio resources creates coordination problems (rate limits, number pooling, opt-out tracking).
4. **Single deployment surface.** One CI pipeline, one set of environment variables, one database, one monitoring stack.

### Why It's Harder Than It Looks

The current app was not designed as a platform — it's a purpose-built scheduling caller. Converting it into a multi-agent outbound platform requires:

1. **Agent-type abstraction across the stack.** Every layer (dispatcher, settings, providers, orchestrator, dashboard) needs to become agent-type-aware. This is not a feature addition — it's an architectural evolution.
2. **New dispatch paradigm.** The scheduling agent uses a polling loop with queue gating. The backfill agent uses event-driven triggers with wave-based timing. These are fundamentally different dispatch patterns that need to coexist.
3. **Two-way SMS is a new capability class.** Adding inbound SMS isn't just a webhook — it's message routing, conversation state, response parsing, and campaign resolution. This touches the data model, service layer, and UI.
4. **The backfill agent has no v1 to extend.** Unlike the intake agent spec (which extends the existing call flow), the backfill agent shares infrastructure but has entirely its own flow logic, data model, and state machine.

---

## 5. New Features Required (Organized by Effort)

### Large (New Subsystems)

| Feature | Description |
|---------|-------------|
| **Campaign engine** | `BackfillCampaign`, `BackfillCandidate`, `BackfillActionLog` tables. Campaign lifecycle: Pending → Running → Filled/Closed. Candidate eligibility evaluation, ranking, and status tracking. |
| **Wave outreach scheduler** | Timer-based wave execution: SMS batches, configurable delays, call escalation to non-responders. Independent of the existing dispatcher loop. |
| **Inbound SMS processing** | Twilio webhook for inbound SMS, message parsing (YES/NO detection), campaign-candidate resolution from phone number, reply state management, late-response closeout. |
| **Cancellation trigger** | Webhook or polling integration to detect appointment cancellations, evaluate 24-hour eligibility rule, and auto-create campaigns. |
| **Atomic booking** | Database-level transactional locking for single-winner slot assignment. Concurrent response handling where one wins and others fail cleanly. |
| **Appointment data model** | New table or fields for appointment datetime, facility, CPT code, appointment status. RadFlow integration to fetch this data. |

### Medium (Extensions to Existing Systems)

| Feature | Description |
|---------|-------------|
| **Agent-type abstraction** | Add agent type concept to settings, call logs, audit events, and dispatcher. Allow filtering and configuration per agent type. |
| **Per-agent settings** | New settings table or JSONB extension for backfill-specific config (min notice hours, batch size, wave delay, etc.) layered on shared global rules. |
| **Campaign UI** | Campaign list view, campaign detail view (candidates, timeline, actions, result), agent-type filter on existing views. |
| **Voice script for backfill** | Different AI conversation: identify facility, mention possible earlier appointment, ask if interested, capture response. Non-guaranteed language. |
| **Candidate matching queries** | SQL queries matching same facility + same CPT + scheduled status, excluding no-shows, opted-out, already contacted. Ranked by farthest appointment first. |

### Small (Tweaks to Existing Components)

| Feature | Description |
|---------|-------------|
| **SMS templates** | Template system for backfill offer messages, closeout messages, confirmation messages. |
| **Opt-out enhancement** | Move from env var to database-backed opt-out tracking. Per-patient suppression flag. |
| **Call history filtering** | Add agent-type filter to call history, audit log, and KPI views. |
| **Reporting extensions** | Backfill-specific KPIs: campaigns created, fill rate, time to fill, response rates by channel. |

---

## 6. Comparison: Backfill Agent vs. Intake Agent (v2) Integration Effort

| Dimension | v2 Intake Agent | Backfill Agent |
|-----------|----------------|----------------|
| **Relationship to v1** | Direct extension of the same call flow — adds phases between "patient answers" and "transfer" | Different workflow entirely — shares infrastructure but not flow logic |
| **Trigger** | Same as v1 (dispatcher polling + queue gating) | New: event-driven (cancellation webhook) |
| **Conversation type** | Extended version of existing call (longer, more phases) | Different call script and purpose |
| **SMS** | Outbound only (portal link) | Two-way (offer + reply processing) |
| **Data model changes** | Moderate — intake status, question config, handoff payload | Heavy — campaigns, candidates, action logs, appointments |
| **New subsystems** | Intake capture service, portal copilot, question config | Campaign engine, wave scheduler, inbound SMS, booking lock |
| **Architectural change** | Minimal — extends existing orchestrator | Significant — requires multi-agent abstraction |
| **Estimated relative effort** | Medium | Large |
| **Risk to v1** | Low — feature-flagged branch after identity verification | Medium — requires refactoring shared components to be agent-type-aware |

---

## 7. Recommended Implementation Approach

### Phase 1: Multi-Agent Foundation

Before building the backfill agent itself, refactor the platform to support multiple agent types:

1. **Add `agent_type` enum** — `SCHEDULING` (current), `CANCELLATION_BACKFILL` (new). Add to `CallLogRow`, `AuditEventRow`, settings model.
2. **Extract shared services** — Ensure business hours, holiday, opt-out, SMS sending, voice AI, and logging are cleanly separated from scheduling-specific logic.
3. **Per-agent settings model** — Create `AgentSettingsRow` table keyed by `(agent_type, setting_key)` with JSONB values, or add a `agent_settings: dict[str, dict]` JSONB field to `SystemSettingsRow`.
4. **Dashboard agent filter** — Add agent-type dropdown to call history, audit log, and KPI views.

This phase benefits both the backfill agent and the v2 intake agent (which also needs prompt/tool customization per flow type).

### Phase 2: Backfill Data Model and Trigger

1. **Appointment data** — Add `AppointmentRow` table (or extend RadFlow integration to include appointment details). Fields: appointment ID, datetime, facility, CPT code, status, cancellation timestamp.
2. **Campaign tables** — `BackfillCampaignRow`, `BackfillCandidateRow`, `BackfillActionLogRow` per the spec.
3. **Cancellation trigger** — Webhook endpoint or polling job to detect cancellations, evaluate 24-hour rule, and create campaigns.
4. **Candidate selection** — Query logic for same-facility + same-CPT matching, exclusion rules, farthest-first ranking.

### Phase 3: Outreach Engine

1. **Inbound SMS webhook** — `POST /api/twilio/sms-inbound` with message parsing, campaign resolution, and state updates.
2. **Wave scheduler** — Async task runner (or lightweight job queue) that executes waves at configurable intervals. Send SMS batches, wait, escalate to calls, repeat.
3. **Voice script** — Backfill-specific AI system prompt and function tools for the escalation calls.
4. **Atomic booking** — Transactional winner assignment with `SELECT ... FOR UPDATE` or equivalent. Campaign close on fill.

### Phase 4: UI and Reporting

1. **Campaign list and detail views** — New dashboard tab or section showing campaigns, candidates, timelines, outcomes.
2. **Backfill settings panel** — Agent-specific configuration in the existing settings area.
3. **Backfill KPIs** — Fill rate, time to fill, response rates, campaign closure reasons.

---

## 8. Key Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Multi-agent refactor destabilizes v1** | Scheduling agent breaks during platform evolution | Feature-flag agent-type code paths. Run v1 regression suite continuously. Keep scheduling agent as the default/fallback. |
| **Wave timing unreliable** | Waves fire late or not at all, degrading fill rates | Use a dedicated async scheduler (e.g., APScheduler, Celery beat, or Temporal) rather than relying on the dispatcher polling loop. |
| **Inbound SMS parsing fails** | Patient replies YES but system doesn't recognize it | Use a generous parser (regex or LLM) that accepts variations: "Yes", "YES", "yeah", "interested", "sure". Log unparseable messages for human review. |
| **Race condition on slot assignment** | Two patients get assigned the same slot | Database transaction with `SELECT ... FOR UPDATE` on campaign row. Test with concurrent load. |
| **RadFlow doesn't expose appointment details** | Can't match by facility + CPT without appointment data | Confirm RadFlow API capabilities early. If appointment data isn't available via API, the cancellation trigger and candidate matching become blocking dependencies. |
| **Longer wave cycles exceed business hours** | Wave 2 fires at 5:05 PM after 5:00 PM cutoff | Wave scheduler must check business hours before each wave. Defer to next business day if outside hours, or close campaign if slot has passed. |
| **SMS delivery failures** | Carrier filtering, opt-outs, invalid numbers reduce reach | Log delivery status via Twilio status callbacks. Skip to next candidate on permanent failure. Retry on transient failure. |

---

## 9. Open Questions to Resolve Before Implementation

1. **How does the system learn about cancellations?** Does RadFlow expose a cancellation webhook, a cancellation polling endpoint, or would we need to detect cancellations by diffing successive patient list pulls?
2. **Does RadFlow provide appointment-level data?** The current `CallListData` API returns patient/order info but not appointment datetime, facility, or CPT code. Are these fields available in the existing API or does a new endpoint need to be built on the RadFlow side?
3. **Can the system reschedule appointments via API?** The backfill agent needs to move a patient's existing appointment to the canceled slot. Is there a RadFlow API for this, or does it require human action?
4. **What is the Twilio number setup?** Is there a dedicated number for SMS that can receive inbound messages? Or would a new Twilio number / messaging service be needed?
5. **Should the wave scheduler be in-process or external?** An in-process async scheduler (APScheduler) is simpler but doesn't survive process restarts. An external job queue (Celery, Temporal) is more reliable but adds infrastructure. Given wave delays of only 10 minutes, process restart risk is low but non-zero.
6. **What happens to the existing scheduling agent's dispatcher when a backfill call is active?** If the platform still has a 1-concurrent-call limit, a backfill escalation call would block scheduling calls (and vice versa). Should there be per-agent concurrency limits?
7. **Is there a test/staging RadFlow environment?** Building and testing the cancellation trigger and appointment rescheduling APIs requires a non-production integration target.
