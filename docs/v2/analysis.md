# V2 Intake Agent Analysis: Integration vs. Separate App

This document analyzes the v2 MediFlow AI Patient Intake Agent specification against the existing OutboundVoiceAI application, evaluates whether v2 should be a separate app or integrated into the existing one, identifies new features needed, and presents the pros and cons of both approaches.

---

## 1. Current App Functionality (v1 Summary)

The OutboundVoiceAI app is a queue-gated outbound calling system for Precise Imaging. Its core loop:

1. **Polls FreePBX** every 10 seconds. When the scheduling queue has few waiting calls and agents are available, it selects a patient to dial.
2. **Dials via Twilio** (or a web-based simulator) using OpenAI Realtime or Gemini Live for conversational AI.
3. **Simple conversation**: greets patient, checks if they are available to schedule. If yes, transfers to a human scheduling queue (language-routed: EN/ES/ZH). If no, sends SMS callback link. If no answer, leaves voicemail and sends SMS.
4. **Tracks attempts** per patient (AI + human), with per-status max attempts (Ordered / No Show / Needs to Reschedule). On max attempts reached, posts HL7 status to RadFlow.
5. **Integrates with RadFlow360** for patient data and outcome write-back.
6. **Dashboard** shows queue state, active call transcript, call history, dispatcher decisions, KPIs, and audit log.

**Tech stack**: FastAPI + Next.js + PostgreSQL + Twilio + OpenAI Realtime / Gemini Live + WebSockets. No Temporal — uses a custom async dispatcher loop with state machine.

---

## 2. How v2 Relates to the Existing Functionality

The v2 spec is a direct extension of the v1 call flow, not a separate workflow. The relationship by phase:

| Phase | v1 (Current) | v2 (Spec) |
|-------|-------------|-----------|
| Queue gating | Dispatcher polls, checks thresholds | **Same** — preserved unchanged |
| Dialing | Twilio outbound call | **Same** |
| No answer | Voicemail + SMS | **Same** — FR-1 explicitly preserves v1 behavior |
| Greeting | "Hi, this is Ashley..." | Extended with consent disclosure + identity verification (name + DOB) |
| After connect | Ask if available, then transfer or SMS | **New branch**: check intake status; if incomplete, run intake flow; then transfer |
| Transfer | Language-routed to FreePBX queue | **Same** destination, but now with structured handoff payload |
| Post-call | Log outcome, update RadFlow, SMS | **Same** + persist workflow state for multi-call resume |

The critical insight: **v2 inserts a new phase between "patient answers" and "transfer to scheduler."** When intake is already complete, v2 behaves identically to v1. When intake is incomplete, the agent runs through identity verification, mode selection (portal vs. voice), intake capture, then transfers.

The spec states explicitly: "All v1 behavior is preserved when a patient has no outstanding intake items — the agent transfers immediately as it does today."

---

## 3. New Features Required for v2

### 3.1 Major New Capabilities

1. **Identity verification** — Name + DOB matching against the order record before any PHI is discussed.
2. **Intake status engine** — Query backend for outstanding tasks across four categories: demographics, prescreen, photo ID, signed lien.
3. **Question configuration system** — Versioned, per-tenant, per-modality question sets with branching logic, skip conditions (`skipIf`), and confirmation rules (`confirmBeforeSave`).
4. **Voice-mode intake capture** — Read questions verbatim from configuration, capture answers (boolean / number / height_ft_in / freetext), confirm numeric and free-text answers before saving.
5. **Portal copilot mode** — Send SMS with portal link, subscribe to real-time portal events via event bus, narrate TODO completion to patient while they work through the portal.
6. **Structured handoff payload** — Transfer reason enum (`INTAKE_COMPLETE`, `PORTAL_REFUSED_FOR_ID_OR_LIEN`, `IDENTITY_VERIFICATION_FAILED`, `PATIENT_REQUESTED_HUMAN`, `TECHNICAL_FAILURE`, `PATIENT_DROPPED_BEFORE_COMPLETE`), captured data summary, call summary, transcript URI.
7. **Multi-call resume** — Persist workflow state so the next call picks up at the first incomplete step. Requires re-verification but does not re-ask captured fields.
8. **Consent and recording disclosure** — Legal-reviewed opening script delivered before identity verification begins.
9. **Refusal behaviors** — Scripted refusals for medical advice, prompt extraction, appointment booking, lien modification, with transfer to human on persistence.
10. **Inactivity and timeout handling** — 45-second silence re-engagement, 10-minute portal inactivity check, 30-day workflow staleness close.

### 3.2 New Integrations

| Integration | Purpose |
|-------------|---------|
| `GET /api/intake/status/{orderId}` | Return outstanding intake tasks |
| `GET /api/patient/{patientId}` | Return current demographic fields for gap analysis |
| `POST /api/intake/capture` | Persist a single captured field (idempotent on orderId + fieldId) |
| `GET /api/preq/config` | Return active question config for tenant and modality group |
| `POST /portal/intake-session` | Create portal session, return tokenized URL for SMS |
| `POST /api/call/transfer` | Hand off call to scheduling queue with handoff payload |
| Portal event bus | Subscribe to real-time TODO completion events per orderId |

### 3.3 New Data Models

- **Question configuration schema** — Fields with types (boolean, number, height_ft_in, freetext), prompts, skip conditions, branches, modality group scoping.
- **Intake status schema** — Outstanding tasks by category (DEMOGRAPHICS, PRESCREEN, PHOTO_ID, SIGNED_LIEN) with field-level granularity.
- **Handoff payload schema** — Call metadata, captured data summary, outstanding items, transfer reason, transcript URI.
- **Workflow state** — Per-order state spanning multiple calls: identity verified, mode selected, captured fields map, portal session ID, completed steps.

### 3.4 Enhanced Voice AI

- System prompt expands significantly to cover: identity verification flow, intake question reading constraints (verbatim wording), portal navigation knowledge (TODO layout, 2FA flow, common failures), refusal behaviors, emergency script.
- New function tools replace current simple tools:
  - Current: `check_transfer_availability`, `transfer_to_scheduler`, `send_sms`, `end_call`
  - v2: `read-intake-status`, `read-patient`, `save-field`, `send-portal-sms`, `subscribe-portal-events`, `transfer-to-human`
- Three modality groups at launch: RADIATION (X-ray, CT), MR_NON_CONTRAST, MR_CONTRAST. Config-driven so new groups need no code change.

---

## 4. Integration vs. Separate App

### Option A: Integrate into the Existing App

**Pros:**

1. **The v2 flow is a superset of v1.** It adds a conditional intake phase after the patient answers and before the transfer. When intake is already complete, the flow is identical to v1. This is a branch in the same call flow, not a different flow.
2. **Shared infrastructure with zero duplication.** Twilio integration, voice AI services (OpenAI / Gemini), dispatcher and queue gating, WebSocket audio streaming, SMS sending, call recording, dashboard — all of this would need to be rebuilt from scratch in a separate app.
3. **Single operational surface.** One dashboard, one dispatcher, one set of settings, one audit trail. Operators see all calls in one place.
4. **Patient state stays unified.** Attempt tracking, cooldowns, RadFlow sync, call history — all in one database. No cross-app coordination needed.
5. **The queue gating logic is complex and battle-tested.** The 3-poll stability check, business hours with holidays, language-based agent availability, concurrent call limits — rewriting this is pure waste.
6. **Incremental rollout is cleaner.** Feature flag per patient or tenant: if intake items exist, run v2 flow; otherwise v1. Same code path, same monitoring.

**Cons:**

1. **Codebase complexity increases significantly.** The voice service prompt goes from ~180 lines to potentially 500+. New services for intake capture, question configuration, portal copilot add substantial code.
2. **Call duration changes.** v1 calls are 2-3 minutes. v2 calls could be 15-20 minutes. This affects the dispatcher's concurrency model (currently limited to 1 active call at a time).
3. **Backend API divergence.** Current app talks to RadFlow360. The spec references "MediFlow backend" with different API endpoints. If these are different systems, adapter work is needed. (Though the spec likely refers to the same system under a different name — "MediFlow 360" vs "RadFlow360".)
4. **Temporal requirement.** The spec calls for Temporal workflows for multi-call resume. Current app uses custom async loops. Adding Temporal is significant infrastructure work, though it would benefit both v1 and v2.
5. **Risk of regressions.** Touching the voice service and call orchestrator could break v1 behavior during development.

### Option B: Separate App

**Pros:**

1. **Clean slate.** Can design for v2 requirements from the start — Temporal, structured intake, portal integration — without legacy constraints.
2. **No regression risk** to v1 during development.
3. **Independent deployment and scaling.** v2 calls are longer and heavier; can scale independently.
4. **Can choose different tech stack** if needed (though there is no strong reason to).

**Cons:**

1. **Massive duplication.** Rebuilding from scratch: Twilio voice integration, OpenAI / Gemini voice services, audio transcoding (mulaw to PCM), WebSocket streaming, SMS service, dispatcher with queue gating, FreePBX polling, business hours logic, patient selection with priority and attempt tracking, call recording, dashboard, settings management, audit logging. This is roughly 80% of the existing app.
2. **Two dispatchers competing for the same queue.** Both apps would be polling FreePBX and dialing patients. Cross-app coordination needed to avoid: calling the same patient from both systems, double-counting agent availability, conflicting queue evaluations.
3. **Split operational view.** Operators need two dashboards. KPIs span two systems. Debugging requires checking both.
4. **Patient state fragmentation.** Attempt counts, call history, and outcomes would live in two databases. RadFlow write-back would need two sources of truth.
5. **Double the maintenance burden.** Two deployments, two sets of dependencies, two CI pipelines, two sets of Twilio webhooks, two monitoring configurations.

---

## 5. Recommendation

**Integrate into the existing app.** The v2 spec is unambiguously an extension of the v1 call flow — it adds a conditional intake phase after the patient answers and before the transfer. Building this as a separate app would mean duplicating roughly 80% of the existing infrastructure to avoid touching roughly 20% of the code that needs to change.

### Suggested Implementation Approach

1. **Abstract the call flow into phases.** The current `CallOrchestrator` handles a flat flow. Refactor to support: `greet → verify_identity → check_intake → [intake_flow | v1_flow] → transfer`. The v1 path is the "intake already complete" branch.

2. **Add intake services as new modules.** `IntakeService`, `QuestionConfigService`, `PortalCopilotService` — these are new service files alongside the existing ones, not modifications to the voice service itself.

3. **Extend the voice AI tools.** Add new function tools (`save-field`, `send-portal-sms`, `subscribe-portal-events`, etc.) to the system prompt. The voice service infrastructure (WebSocket, audio, transcoding) stays unchanged.

4. **Add Temporal for multi-call state.** This benefits both v1 and v2. V1 could use it for better retry and resume tracking. V2 requires it for cross-call state persistence.

5. **Feature-flag the intake flow.** After identity verification, check intake status. If no outstanding tasks, fall through to v1 behavior. Zero risk to existing v1 patients.

### Key Risks to Mitigate

- **Longer call durations affecting concurrency.** The dispatcher's 1-concurrent-call model may need to increase to 2-3 for v2 calls, since a 15-minute intake call would block all other outbound dialing under the current model.
- **Voice prompt complexity.** Consider modular prompt composition where v2-specific sections (intake questions, portal navigation, refusal scripts) are injected only when intake items exist, keeping v1 calls lightweight.
- **Backend API naming.** Clarify whether "MediFlow 360" in the spec and "RadFlow360" in the current integration are the same system. If different, build an adapter layer so the intake APIs can be swapped independently.
