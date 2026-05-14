# V2 Intake Agent — Milestone Plan

A 3-milestone breakdown of the v2 intake agent rollout. Each milestone is independently shippable behind feature flags. v1 behavior is preserved unchanged until we are ready to flip flags on.

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

**Goal:** introduce the v2 entry point, identity verification, and a structured handoff — without doing any intake yet.

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
3. **Internal QA calls** — staff dial in as test patients with flag forced ON. Verify consent script reads correctly, identity flow handles right/wrong DOB, handoff payload arrives at scheduler with correct reason code.
4. **Canary 1% of one tenant for 3 days.** Watch: v1 regression rate (should be 0), identity verification success rate, handoff payload completeness. Rollback = flip master flag off.
5. **Exit criteria:** zero v1 regressions, ≥95% identity-verification success on real patients, handoff payload audited end-to-end at scheduler.

---

## Milestone 2 — Voice-Mode Intake Capture

**Goal:** the agent can actually complete intake by voice, then transfer.

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

Each milestone follows the same pattern: **off → shadow → internal QA → 1% canary → 5% canary → tenant-wide → all tenants**. Flags stay independent so M2 can ship to one tenant while M3 is still in QA, and any milestone can be rolled back without affecting the others.
