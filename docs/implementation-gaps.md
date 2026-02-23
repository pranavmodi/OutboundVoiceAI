# Implementation Gaps — Requirements Audit

Audit performed against all 70 test scenarios and the requirements document.
Date: 2026-02-23

---

## Functional Gaps

### Gap 1: Preferred Callback Time Not Captured

**Requirement:** Scenario 36 (Patient not available), Requirements §Call Outcomes — Outcome 3

> "AI asks for preferred callback time (optional)"
> "Invite patient to reply with preferred callback time"

**Current behavior:** The AI system prompt instructs the agent to "ask for permission to note a better callback time" conversationally, but there is no mechanism to record or store it. The `end_call` tool has no `preferred_callback_time` parameter, and neither `CallLog` nor `Patient` models have a field for it.

**Impact:** The AI asks the question but the answer is lost — it only appears in the transcript. Scheduling staff reviewing the call log would have to read the transcript manually.

**Suggested fix:**
- Add an optional `preferred_callback_time` string parameter to the `end_call` tool definition
- Add a `preferred_callback_time` field to `CallLog`
- Persist the value when the AI provides it
- Surface it in the dashboard call detail view

---

### Gap 2: Holiday Calendar Not Implemented

**Requirement:** Requirements §Business Hours Enforcement, next-milestone.md Feature 6

> "Holiday calendar support required"

**Current behavior:** `is_within_business_hours()` only checks time-of-day and day-of-week. There is no holiday data source, no holiday model, and no check against holidays.

**Impact:** The system will place calls on holidays that fall within normal business hours (e.g., Christmas on a weekday).

**Suggested fix:**
- Add a `holidays` table or configuration (list of dates)
- Check holidays in `is_within_business_hours()`
- Expose holiday management in the dashboard settings

---

### Gap 3: Document Upload Instructions Missing from AI Prompt

**Requirement:** Scenario 51 (Patient asks how to upload documents), Requirements §AI Agent Capabilities — Allowed Topics

> "How to upload ID/documents"

**Current behavior:** The system prompt includes patient portal URL (`portal.preciseimaging.com`) but does not include specific instructions on how to upload documents or ID through the portal.

**Impact:** If a patient asks "How do I upload my ID?", the AI can only point to the portal generically rather than giving step-by-step guidance.

**Suggested fix:**
- Add a "How to Upload Documents" section to the `SYSTEM_INSTRUCTIONS` knowledge base with steps (e.g., log in to portal, navigate to Documents section, click Upload, select files)

---

## Logging / Observability Gaps

### Gap 4: No "system_disabled_during_call" Log Event

**Requirement:** Scenario 69 (System disabled during active call)

> "Log: system_disabled_during_call"

**Current behavior:** When an admin disables the system while a call is in progress, the active call runs to completion (correct behavior), but no special event is logged indicating the system was disabled mid-call. The dispatcher simply stops dispatching.

**Impact:** No audit trail that a call was in progress when the system was disabled.

**Suggested fix:**
- In the settings update handler (or dispatcher `stop()`), check if a call is active and log a `system_disabled_during_call` event to the call transcript

---

### Gap 5: No "hours_ended_during_call" Log Event

**Requirement:** Scenario 70 (Business hours end during active call)

> Expected: call completes normally, with logged note that hours ended

**Current behavior:** Same as Gap 4 — the call completes normally but no event is logged noting that business hours ended while the call was active.

**Impact:** No audit trail for after-hours call completion.

**Suggested fix:**
- In the dispatcher tick, if a call is active and business hours have just ended, log a `business_hours_ended_during_call` event

---

## Minor / Defensive Gaps

### Gap 6: Stale Queue State at Transfer Time

**Requirement:** Scenario 45 (Transfer requested, AMI now disconnected)

**Current behavior:** When the AI requests a transfer, `TransferService.execute_transfer()` reads queue state from the provider, which returns the last-polled snapshot (updated every 10 seconds by the dispatcher). If AMI disconnects between polls, the transfer check may use stale data showing AMI as connected.

**Impact:** A transfer could be attempted against a stale queue snapshot. The window is small (up to 10 seconds) and the actual Twilio transfer would likely still succeed or fail gracefully, but the safety check is not real-time.

**Suggested fix:**
- Force a fresh `queue_provider.poll()` inside `execute_transfer()` before checking capacity
- Or accept the race window as tolerable given the 10-second poll interval

---

### Gap 7: Wrong-Number Detection Uses Fragile Regex Heuristics

**File:** `app/services/transfer_service.py:71-83` (`looks_like_wrong_number_signal()`)

**Current behavior:** The only regex-driven decision logic in the call flow runs against patient transcript lines immediately before a transfer is attempted. If a match is found, the transfer is canceled and the call ends as `WRONG_NUMBER`. The patterns are:

```
r"\bnot me\b"
r"\bthis is(?:n't| not) [a-z]+\b"
r"\byou have the wrong\b"
r"\bno one (?:by|with) (?:that|this) name\b"
r"\bdon'?t know (?:who|them|that person)\b"
```

Plus plain substring checks for "wrong number" and "wrong person".

**Impact:** These heuristics are the sole server-side safety net preventing a transfer after the patient has indicated wrong number. They duplicate intent the AI model is already expected to handle (the AI prompt says to call `end_call(reason="wrong_number")`). The regex approach is brittle:
- False negatives: "I'm not that person", "you've got the wrong guy", "nobody here by that name" would not match.
- False positives: "this isn't right" could match `this is(?:n't| not) [a-z]+`.
- Transcription errors from Whisper can break word-boundary matches.

No other next-step decisions use regex. Voicemail detection (`looks_like_voicemail_signal`) and disconnected-number detection (`looks_like_disconnected_or_invalid`) use plain substring matching. All other call-flow routing comes from AI tool calls, Twilio status callbacks, or numeric queue thresholds.

**Suggested fix:**
- Treat the regex check as a backup safety net, not the primary detection mechanism — the AI model should be the authoritative wrong-number detector
- Expand patterns to cover more phrasings (e.g., "wrong guy", "nobody here by that name", "never heard of them")
- Consider a lightweight LLM classification pass on the last few transcript lines instead of regex, for higher accuracy
- Add logging when the regex catches a wrong-number that the AI missed, to measure how often the safety net fires

---

### Gap 8: AI Cannot Proactively Indicate Queue Unavailability

**Requirement:** Scenario 58 (Off-topic question, transfer not safe)

> Expected: AI says "Our team is currently busy, but I can send you a text with our main number to call back."

**Current behavior:** The AI always offers transfer when it can't answer a question. It calls `transfer_to_scheduler`, and the backend discovers the queue is unavailable, sends a fallback SMS, and ends the call as `CALLBACK_REQUESTED`. The patient hears the AI say it will transfer, then gets told it can't.

**Impact:** Slightly awkward conversational flow — the AI promises a transfer before knowing it will fail. The outcome is correct (SMS sent, call ended), but the patient experience could be smoother.

**Suggested fix:**
- Expose a `check_transfer_availability` tool that the AI can call before promising a transfer
- Or add queue status context to the AI session (e.g., periodic updates about queue availability so the AI can proactively adjust its language)
