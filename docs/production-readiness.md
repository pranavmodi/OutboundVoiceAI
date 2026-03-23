# Production Readiness — Switchover Checklist

Issues and fixes required before switching from simulation/mock mode to live production systems.

Last updated: 2026-03-23

---

## Critical Issues (will break things if not fixed)

### 1. Twilio webhook URLs may point to wrong host

**File:** `app/services/call_orchestrator.py:262-264`

**Issue:** When placing a Twilio call, the system builds webhook URLs (TwiML, status callbacks, media stream WebSocket) using `PUBLIC_BASE_URL`. If not set, it falls back to `NEXT_PUBLIC_API_URL`, then `http://localhost:8000`.

**Current .env state:** `PUBLIC_BASE_URL` is not set, but `NEXT_PUBLIC_API_URL=https://outbound.mediflow360.com` is set, so Twilio will use `https://outbound.mediflow360.com/api/twilio/twiml/...`. This works **only if that domain routes to the backend API**, not just the frontend. If the frontend and backend are served from different hosts, Twilio webhooks will hit the frontend and fail.

**What happens if not fixed:** Twilio places the call and the patient's phone rings, but when they answer there is no audio — the TwiML webhook fails, the media stream WebSocket never connects (30-second timeout), and the call is marked FAILED. AMD voicemail detection and carrier failure callbacks also silently stop working.

**Fix:** Set `PUBLIC_BASE_URL` explicitly to the backend's externally reachable URL. Verify that this URL can serve both HTTPS (for TwiML/status webhooks) and WSS (for media stream WebSocket at `/ws/twilio-media/`).

---

### 2. Live patient provider ignores retry controls

**File:** `app/providers/patient_provider.py:394-401`

**Issue:** `LivePatientProvider.get_outbound_queue()` accepts `max_attempts` and `min_hours_between` parameters but does not use them. It fetches the full patient list from RadFlow and only sorts by priority — no filtering.

**What happens if not fixed:** The system may call the same patient multiple times in rapid succession with no cooldown, and continue calling patients who have already reached the max attempt limit. This violates the retry controls in the requirements (max 3 attempts, 6-8 hours between).

**Fix:** After fetching from RadFlow, apply the same filters the simulation provider uses: skip patients where `attempt_count >= max_attempts`, and skip patients where `last_attempt_at` is within the cooldown window. This requires local state tracking (see issue #3).

---

### 3. Live patient provider is read-only — no state tracking

**File:** `app/providers/patient_provider.py:403-418`

**Issue:** `LivePatientProvider.update_patient_after_call()` and `mark_patient_invalid_number()` are no-ops — they log a message but don't persist anything. There is no local database table and no write-back to RadFlow.

**What happens if not fixed:**
- `ai_called_before` is never set to `True`, so patients never move from high-priority bucket 1 to lower bucket 2. The same patient keeps getting picked first.
- `attempt_count` is never incremented locally, compounding issue #2.
- `mark_patient_invalid_number()` has no effect — disconnected numbers are retried on the next poll.
- No record of what happened on each call outside of the local call log.

**Fix:** Add a local state table (e.g., `patient_call_state`) that tracks `patient_id`, `attempt_count`, `last_attempt_at`, `last_outcome`, `ai_called_before`, and `invalid_number`. The live provider should merge this local state with the RadFlow API data on each fetch, and persist outcomes after each call.

---

### 4. SSL verification disabled on RadFlow patient API

**File:** `app/providers/patient_provider.py:340`

**Issue:** The HTTP client is created with `verify=False`, which disables TLS certificate validation.

**What happens if not fixed:** Patient data (names, phone numbers, order IDs) travels over the network without verifying the server's identity. A man-in-the-middle could intercept or modify patient data.

**Fix:** Change to `verify=True` (the default). If RadFlow uses a self-signed or internal CA certificate, provide the CA bundle path via the `verify` parameter instead of disabling verification entirely.

---

## High Severity (will cause noticeable problems)

### 5. ~~Email crashes if SMTP is not configured~~ — RESOLVED

**File:** `app/services/email_notification_service.py:54,62`

**Status:** SMTP is fully configured in `.env` (Gmail SMTP with app password, recipient `scheduling@precisemri.com`). No action needed.

---

### 6. SMS callback number not configured

**File:** `app/services/twilio_sms_service.py:59-77`

**Issue:** SMS messages are built using `PRECISE_CALLBACK_NUMBER` env var. If it's not set, the message falls back to: *"Please call our office using the number previously shared with you."*

**What happens if not fixed:** Patients who receive a voicemail follow-up SMS or a "not available" SMS get a message without a phone number to call back. For patients who have never contacted Precise Imaging before, this is confusing and unhelpful.

**Fix:** Set `PRECISE_CALLBACK_NUMBER` (e.g., `800-558-2223`) and optionally `PRECISE_MAIN_NUMBER` as a secondary number.

---

### 7. Database credentials are weak

**File:** `app/db/base.py`, `.env`

**Issue:** `DATABASE_URL` is set in `.env` and matches the hardcoded default: `postgresql://precise:password@10.254.99.40:5432/outboundvoice`. The password is `password`. The database is on an internal IP, which limits exposure, but the credentials are trivially guessable.

**What happens if not fixed:** Anyone with network access to `10.254.99.40` can connect to the database with `precise/password` and read/modify call logs, patient data, and system settings.

**Fix:** Change the database password to something strong. If this is the intended production database, update both the DB server and the `.env` file. If there's a separate production database, set the correct `DATABASE_URL`.

---

### 8. ~~CORS blocks production frontend~~ — RESOLVED

**File:** `app/main.py:60-68`

**Status:** `CORS_ORIGINS` is set in `.env` to `https://outbound.mediflow360.com,http://localhost:3002,http://127.0.0.1:3002`. Production domain is included. No action needed.

---

## Medium Severity (could cause intermittent issues)

### 9. Single FreePBX poll failure blocks all outbound for 30+ seconds

**File:** `app/providers/queue_provider.py:239-244`

**Issue:** When an HTTP request to FreePBX fails (timeout, network blip, 500 error), the provider immediately sets `ami_connected=False`, `outbound_allowed=False`, and resets the stable polls counter to 0. Recovery requires 3 consecutive successful polls (30 seconds at the default 10-second interval).

**What happens if not fixed:** A brief network hiccup causes outbound calling to pause for at least 30 seconds. If the network is flaky, outbound calling may rarely reach the stability threshold and effectively stay disabled.

**Fix:** Consider tolerating 1-2 consecutive failures before disabling outbound (a "failure hysteresis" to match the existing success hysteresis). Or reduce stable_polls_required for recovery vs. initial startup.

---

### 10. FreePBX polling timeout is tight (5 seconds)

**File:** `app/providers/queue_provider.py:212`

**Issue:** The HTTP client timeout is 5 seconds. Under network load or if FreePBX is slow to respond, polls may time out frequently.

**What happens if not fixed:** Frequent timeouts trigger issue #9, causing outbound calling to be paused repeatedly.

**Fix:** Increase timeout to 10-15 seconds, or use separate connect/read timeouts (e.g., connect=5s, read=15s).

---

### 11. RadFlow API failure serves stale patient data

**File:** `app/providers/patient_provider.py:385`

**Issue:** If the RadFlow API call fails, the provider returns the last cached response (up to 60 seconds old). If the API stays down, the cache eventually goes stale but is still served.

**What happens if not fixed:** During an API outage, the system continues calling patients from an increasingly stale list. New patients won't appear, and patients who should have been removed (e.g., already scheduled) may still be called.

**Fix:** Add a maximum staleness threshold. If the cache is older than a configurable limit (e.g., 5 minutes), stop returning it and treat the patient list as empty (which blocks outbound calling via the "no candidate" path).

---

### 12. Web-mode callbacks persist after switching to Twilio mode

**File:** `app/services/dispatcher.py:281-298`

**Issue:** When the dispatcher starts a call in web mode, it wires up orchestrator callbacks for WebSocket broadcasting to the dashboard. If the call mode is later switched to Twilio, these callbacks remain attached.

**What happens if not fixed:** Dashboard may receive unexpected updates or audio data from Twilio calls that was intended for the browser audio path. Unlikely to crash but may cause confusing UI behavior.

**Fix:** Clear and re-wire orchestrator callbacks when call mode changes, or ensure callbacks are mode-aware.

---

## Low Severity (minor issues)

### 13. FreePBX polled over HTTP, not HTTPS

**File:** `app/providers/queue_provider.py:16`

**Issue:** Queue status is fetched over plain HTTP (`http://10.254.99.40:2001/queuestatus.php`).

**What happens if not fixed:** Queue data (agent counts, call counts) is transmitted unencrypted on the network. Not a patient data risk, but a defense-in-depth concern.

**Fix:** Use HTTPS if FreePBX supports it. If it's strictly internal network with no exposure, this is acceptable.

---

### 14. Two separate gates required for live Twilio calls

**File:** `app/services/twilio_voice_service.py:139`, `app/services/call_orchestrator.py:198`

**Issue:** Two independent guards must both be enabled: the `ALLOW_TWILIO_CALLS=true` env var (checked in `twilio_voice_service.py`) and the `allow_live_calls` database setting (checked in `call_orchestrator.py`). There's also the `allowed_phones` whitelist.

**Current .env state:** `ALLOW_TWILIO_CALLS=true` is set. The `allow_live_calls` DB setting and `allowed_phones` list must still be configured via the Operator Console.

**What happens if not fixed:** Forgetting to enable one of the two gates results in calls failing with no obvious error message to the user. The env var gate produces a RuntimeError, while the settings gate produces a UI error.

**Fix:** Not a bug — this is defense in depth. But document it clearly so operators know both must be enabled. Consider surfacing a dashboard warning when one is enabled but not the other.

---

### 15. Provider sources default to "simulation" on fresh startup

**File:** `app/providers/queue_provider.py:253`, `app/providers/patient_provider.py:427`

**Issue:** Both `queue_source` and `patient_source` default to `"simulation"`. The setting is persisted in the database, so once switched to "live" it stays, but a fresh database will start in simulation mode.

**What happens if not fixed:** After a fresh deployment or database reset, the system uses mock queue data and sample patients instead of real FreePBX and RadFlow data. Calls may go out to test patients or not go out at all.

**Fix:** After deployment, switch both sources to "live" via the Operator Console or API. For fully automated deployments, seed the database with `queue_source="live"` and `patient_source="live"`.

---

## Production Environment Variables

| Variable | Required | .env Status | Action Needed |
|---|---|---|---|
| `PUBLIC_BASE_URL` | Yes | **NOT SET** — falls back to `NEXT_PUBLIC_API_URL` | Set explicitly to backend URL |
| `ALLOW_TWILIO_CALLS` | Yes | `true` | None |
| `TWILIO_ACCOUNT_SID` | Yes | Set (personal account) | Switch to Precise creds for production |
| `TWILIO_AUTH_TOKEN` | Yes | Set (personal account) | Switch to Precise creds for production |
| `TWILIO_FROM_NUMBER` | Yes | `+14437752452` (personal) | Switch to `+18005582223` for production |
| `OPENAI_API_KEY` | Yes | Set | None |
| `DATABASE_URL` | Yes | Set (`10.254.99.34`, password=`password`) | Strengthen password |
| `SMTP_HOST` | Yes | `smtp.gmail.com` | None |
| `SMTP_PORT` | No | `587` | None |
| `SMTP_USERNAME` | Yes | Set | None |
| `SMTP_PASSWORD` | Yes | Set (app password) | None |
| `SMTP_FROM_EMAIL` | Yes | Set | None |
| `EMAIL_NOTIFICATION_RECIPIENT` | Yes | `scheduling@precisemri.com` | None |
| `PRECISE_CALLBACK_NUMBER` | Yes | **NOT SET** | Set to `800-558-2223` |
| `PRECISE_MAIN_NUMBER` | No | **NOT SET** | Optional |
| `CORS_ORIGINS` | Yes | Set (includes production domain) | None |
| `FREEPBX_QUEUE_URL` | No | Uses default `10.254.99.40:2001` | Verify correct for production |
| `LANGUAGE_QUEUE_MAP` | Yes | **NOT SET** — defaults to `scheduling_en/es` | Set to `{"en":"9006","es":"9009"}` (confirm with Danny) |
| `QUEUE_TRANSFER_TARGETS` | Yes | **NOT SET** | Set SIP/PSTN targets per queue (needs Danny) |
| `CALLLIST_API_URL` | No | Set (`app.radflow360.com`) | None |
| `CALLLIST_API_USER` | Yes | Set (`Chatbot`) | None |
| `CALLLIST_API_PASSWORD` | Yes | Set | None |

## Database Settings (via API or Operator Console)

| Setting | Default | Production Value |
|---|---|---|
| `queue_source` | `simulation` | `live` |
| `patient_source` | `simulation` | `live` |
| `call_mode` | `web` | `twilio` |
| `allow_live_calls` | `false` | `true` |
| `allowed_phones` | `[]` | Whitelist of patient phones (or all) |
| `system_enabled` | `true` | `true` |
| `business_hours.enabled` | `false` | `true` |
| `mock_mode` | `false` | `false` |
