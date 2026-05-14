# V2 Intake Agent — Milestone Plan

A 3-milestone breakdown of the v2 intake agent build. M1 and M2 are **engineering phases of a single client release** — they're flag-gated independently for safe internal staging, but neither is intended to reach general availability on its own (see [Client spec constraints](#client-spec-constraints) below). M3 ships as a v2.1 follow-on. v1 behavior is preserved unchanged until the combined M1+M2 release flips flags on for real patients.

---

## Client spec constraints

The MediFlow v2 spec (`spec.txt` in this folder, Section 1.3 — original `spec.docx`) **explicitly prohibits phased intake rollouts**:

> "Ship all capabilities together as a single release to preserve patient experience; **no partial or phased intake flows.**"

Section 1.1 pins the success definition:

> "...schedulers receive **only intake-complete patients** and can focus on appointment placement."

### Implications for this plan

- **M1 alone cannot ship to GA.** Verify-identity-then-route-to-human is not in the allowed `transferReason` enum (Section 8) — the spec has no "intake deferred to human" reason. M1's value is the safety scaffolding; the visible-to-patients release is M1+M2 together.
- **M1 may run in shadow mode and via `/admin/v2-test` for internal QA.** Both are pre-production and don't violate Section 1.3.
- **The master flag flips for real patients only when M2 is also ready.** Until then, every "v2 mode" run is either internal QA or a shadow-mode log line.
- **M3 (portal copilot, multi-call resume) is a separate v2.1 release window.** Same "single release" rule applied to portal-mode work — landing portal alone would itself be a partial intake change.

### Allowed `transferReason` enum (spec Section 8)

Every transfer in M1+M2 must use one of these exact strings:

| transferReason | Trigger | Milestone |
|---|---|---|
| `INTAKE_ALREADY_COMPLETE` | Intake complete at FR-3 (= our internal `NO_INTAKE_NEEDED` — rename pending) | M1 |
| `IDENTITY_VERIFICATION_FAILED` | DOB mismatch twice | M1 |
| `PATIENT_REQUESTED_HUMAN` | Patient asks | M1 |
| `TECHNICAL_FAILURE` | LLM / portal / backend / Twilio error | M2 |
| `INTAKE_COMPLETE` | All artifacts captured during the call | M2 |
| `PATIENT_DROPPED_BEFORE_COMPLETE` | Patient hung up | M2 (and M3 resume) |
| `PORTAL_REFUSED_FOR_ID_OR_LIEN` | Patient refused portal for photo ID / lien | M3 |

Note: `app/models/handoff.py` includes `V1_FALLBACK` as an internal safety reason that's never sent to the scheduler — it's purely a log marker if the v2 code path fails through to v1. That's fine; it doesn't violate the spec because no `V1_FALLBACK` payload reaches the scheduling queue.

### Naming alignment to do

| Our code | Spec | Action |
|---|---|---|
| `NO_INTAKE_NEEDED` | `INTAKE_ALREADY_COMPLETE` | Rename before M2 — easier now than after the scheduler consumer is written |
| `V1_FALLBACK` | (not in spec) | Keep as internal-only; never emit on a transfer the scheduler sees |

---

## Feature flag layout (set up in Milestone 1, used throughout)

```
intake_v2.master_enabled          # global kill switch, default OFF
intake_v2.tenant_allowlist        # which tenants can opt in
intake_v2.order_canary_pct        # % of eligible orders to route through v2
intake_v2.mode.voice_capture      # M2 voice intake on/off
intake_v2.mode.portal_copilot     # M3 portal mode on/off
intake_v2.multi_call_resume       # M3 Temporal-backed resume on/off
```

Decision rule at runtime: if any flag is OFF or the order isn't in the canary, the call takes the **exact v1 code path**. v2 code is dead until flags flip.

---

## Milestone 1 — Foundation & Safe Branch Point

**Goal:** build the safe branch point — feature flags, identity verification, the structured handoff schema, and shadow-mode wiring — so the M2 voice flow has solid ground to stand on.

**M1 alone is internal-validation only.** It does not ship to real patients without M2 (see [Client spec constraints](#client-spec-constraints)).

### Scope

- Feature flag system (above) wired into `CallOrchestrator`.
- Consent + recording disclosure script at call start (only when v2 flag is on).
- Identity verification: name + DOB match against the order.
- New API: `GET /api/intake/status/{orderId}` — read-only, just reports outstanding tasks.
- Structured handoff payload schema with initial reasons: `V1_FALLBACK`, `IDENTITY_VERIFICATION_FAILED`, `PATIENT_REQUESTED_HUMAN`, `NO_INTAKE_NEEDED`.
- Branch: if intake exists → log it and transfer to human with handoff payload. If no intake → fall through to v1 transfer. Either way, no intake is captured yet.

### Verification plan

1. **Shadow mode in prod (1 week).** Flag OFF for everyone; log what *would* have happened (would v2 have triggered? would identity have verified?). Confirms intake-status API and identity logic are reliable before any real patient hears a difference.
2. **Unit + integration tests** for: flag evaluation matrix (all combinations), identity match (correct, mismatch, missing DOB), handoff payload schema validation.
3. **Internal QA calls via `/admin/v2-test`** — staff drive scenarios as synthetic test patients. Verify consent script reads correctly, identity flow handles right/wrong DOB, handoff payload constructed correctly with the right reason code, gate decisions logged accurately.
4. ~~Canary 1% of one tenant for 3 days~~ — **skipped for M1 alone.** Real-patient canary waits for M1+M2 because the spec forbids partial intake flows in production (Section 1.3). M1's "ready for canary" state means *ready to be combined with M2 for canary*.
5. **Exit criteria:** zero v1 regressions, gate decisions stable in shadow-mode logs for 1 week, ≥95% identity-verification success in internal QA, handoff payload schema validated against scheduler-side parser, M1+M2 transfer-reason enum alignment audited. **Ready-to-merge-with-M2, not ready-to-ship-alone.**

---

## Milestone 2 — Voice-Mode Intake Capture

**Goal:** the agent can actually complete intake by voice, then transfer. **M1+M2 together is the GA release** that satisfies the client spec's "single release" requirement (Section 1.3).

### Scope

- `QuestionConfigService` — versioned, per-tenant, per-modality (RADIATION, MR_NON_CONTRAST, MR_CONTRAST). Config-driven, no code change for new question sets.
- `IntakeService` — captures fields with idempotent writes (`POST /api/intake/capture`).
- New voice AI tools: `read-intake-status`, `read-patient`, `save-field`, `transfer-to-human`.
- Voice intake flow: verbatim question reading, type-aware capture (boolean / number / height_ft_in / freetext), confirm-before-save for numeric and freetext.
- Refusal scripts (medical advice, appointment booking, lien modification) with escalation to human.
- 45-second silence re-engagement.
- New handoff reasons: `INTAKE_COMPLETE`, `PATIENT_DROPPED_BEFORE_COMPLETE`, `TECHNICAL_FAILURE`.
- Dispatcher concurrency bumped to 2–3 (calls now run 15–20 min, gated by `intake_v2.master_enabled`).

### Verification plan

1. **Question config replay tests.** Run each modality's question set through a scripted patient (yes-path, no-path, all skip conditions). Assert every field saved matches expected.
2. **Idempotency tests.** Drop and resume mid-call (network kill); confirm `save-field` doesn't double-write.
3. **Internal QA — full intake by voice** for all three modality groups. Verify: questions read verbatim, confirmation prompts on numeric/freetext, refusals trigger correctly, 45s silence re-engages.
4. **Concurrency load test.** Force 3 simultaneous v2 calls; confirm dispatcher doesn't starve v1 patients in the queue.
5. **Canary 5% of eligible orders for 1 week** (`mode.voice_capture` = ON, `mode.portal_copilot` = OFF). Track: intake completion rate, average call duration, drop rate vs. v1, captured-field accuracy spot-checked against transcripts.
6. **Exit criteria:** ≥80% of started v2 calls reach `INTAKE_COMPLETE`, no v1 queue starvation, audit of 50 random captured-field sets shows ≥98% accuracy.

---

## Milestone 3 — Portal Copilot & Multi-Call Resume

**Goal:** offer the SMS portal as an alternative to voice, and survive across calls.

### Scope

- `POST /portal/intake-session` — create tokenized portal URL, send via SMS.
- Portal event bus subscription — agent narrates TODO completion in real time.
- New voice AI tools: `send-portal-sms`, `subscribe-portal-events`.
- Temporal workflows for per-order state: identity-verified, mode selected, captured fields, portal session ID, completed steps.
- Multi-call resume: next call re-verifies identity, then skips already-captured fields.
- 10-minute portal inactivity check, 30-day workflow staleness close.
- Final handoff reason: `PORTAL_REFUSED_FOR_ID_OR_LIEN`.

### Verification plan

1. **Temporal workflow tests** (deterministic replay): start workflow, kill worker mid-intake, restart, confirm state resumes correctly. Test 30-day expiry.
2. **Portal event-bus tests** — simulate portal completion events, assert agent narrates correctly and marks fields complete without re-asking.
3. **Internal QA dual-mode runs:** start in voice → switch to portal mid-call; start in portal → patient drops, call back, resume from portal session.
4. **Canary 5% with portal flag ON for 1 week.** Track: portal-vs-voice selection rate, portal completion rate, resume-call success rate (next call truly skips captured fields), 10-min inactivity behavior.
5. **Stale workflow audit.** After 30 days, confirm long-idle workflows close cleanly and re-trigger as fresh on next call.
6. **Exit criteria:** ≥90% of resume calls correctly skip prior fields, portal completion rate ≥60% of patients who choose it, zero stuck workflows after 30-day cutoff.

---

## Rollout sequencing across milestones

The standard rollout pattern is **off → shadow → internal QA → 1% canary → 5% canary → tenant-wide → all tenants**. Spec-compliance adjustments per Section 1.3 ("no partial or phased intake flows"):

- **M1 stops at internal QA.** No real-patient canary stage for M1 alone — verify-and-route is not a spec-permitted production state.
- **M1+M2 ride the rollout pattern together** from 1% canary onward, as the single client v2.0 release.
- **M3 is its own release window** — once M1+M2 is GA-stable, M3 starts a fresh shadow → canary cycle. Adding portal mode mid-release would itself be a partial intake change.
- **Flags stay independent** so each can be rolled back without affecting the others. Independence of flags is for safety (rollback granularity), not for shippable release scope.

### Quick decision rubric

| Flag combination | Stage |
|---|---|
| All flags OFF | Production (default). |
| `master_enabled=true` only, scoped to `tenant=TEST` | `/admin/v2-test` QA. Synthetic patients only. |
| `master_enabled=true`, real tenant, low canary, M2 flags OFF | **NOT ALLOWED** in prod — violates spec. Only for internal-shadow on a non-prod env. |
| `master_enabled=true`, real tenant, low canary, M2 flags ON | M1+M2 canary. The first spec-compliant production state. |
| All M1+M2 flags ON tenant-wide | M1+M2 GA. |
| M3 flags also ON | M3 canary (after M1+M2 GA stable). |
