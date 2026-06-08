# RadFlow Cancellation Webhook Contract

This is the push-event contract the Cancellation Backfill backend should expose for RadFlow appointment cancellations. It is the integration detail behind the cancellation trigger in `cancellation-backfill-spec.md`.

## Endpoint

Production URL:

```text
POST https://<backfill-backend-public-host>/api/integrations/radflow/appointment-cancellations
```

Staging URL:

```text
POST https://<backfill-backend-staging-host>/api/integrations/radflow/appointment-cancellations
```

The exact host will be provided after deployment. The path should remain stable across staging and production.

## Authentication

Use bearer token authentication.

Required headers:

```text
Content-Type: application/json
Authorization: Bearer <shared webhook token>
X-RadFlow-Event-Id: <stable unique event id>
```

Receiver requirements:

- Reject missing auth headers.
- Verify the bearer token using a constant-time comparison.
- Treat `X-RadFlow-Event-Id` as the idempotency key.

Backfill backend env to support this:

```text
RADFLOW_CANCELLATION_WEBHOOK_TOKEN=<shared webhook token>
```

## Request Body

```json
{
  "eventType": "appointment.cancelled",
  "eventId": "evt_20260528_123456789",
  "occurredAt": "2026-05-28T18:42:15Z",
  "appointment": {
    "appointmentId": "APT-123456",
    "status": "Canceled",
    "previousStatus": "Scheduled",
    "canceledAt": "2026-05-28T18:42:15Z",
    "startDateTime": "2026-05-30T17:00:00-07:00",
    "timezone": "America/Los_Angeles",
    "facilityId": "FAC-001",
    "facilityName": "Precise Imaging - Beverly Hills",
    "cptCode": "74183",
    "procedureDescription": "MRI Abdomen with and without contrast"
  },
  "patient": {
    "patientId": "PAT-987654",
    "patientName": "Jane Doe",
    "phone": "+13105551212"
  },
  "metadata": {
    "sourceSystem": "RadFlow",
    "tenantId": "precise",
    "changeReason": "Patient canceled"
  }
}
```

## Field Requirements

| Field | Required | Notes |
|---|---:|---|
| `eventType` | Yes | Must be `appointment.cancelled`. |
| `eventId` | Yes | Stable unique event ID for idempotency and retries. |
| `occurredAt` | Yes | When RadFlow emitted or recorded the event. ISO-8601. |
| `appointment.appointmentId` | Yes | Canceled appointment identifier. |
| `appointment.status` | Yes | Current appointment status, expected `Canceled`. |
| `appointment.previousStatus` | Preferred | Helps ignore non-scheduled cancellations. |
| `appointment.canceledAt` | Yes | Cancellation timestamp. ISO-8601. |
| `appointment.startDateTime` | Yes | Original exam slot date/time. Must include offset or pair with `timezone`. |
| `appointment.timezone` | Yes | IANA timezone, for example `America/Los_Angeles`. |
| `appointment.facilityId` | Yes | Stable facility identifier used for candidate matching. |
| `appointment.facilityName` | Preferred | Display name for UI and patient messaging. |
| `appointment.cptCode` | Yes | CPT/procedure code used for same-exam matching. |
| `appointment.procedureDescription` | Preferred | Useful for audit/UI, not used for matching. |
| `patient.patientId` | Yes | Patient whose appointment was canceled. |
| `patient.patientName` | Preferred | UI/audit display. |
| `patient.phone` | Preferred | UI/audit display; not used for candidate matching. |

## Response Semantics

Success:

```json
{
  "status": "accepted",
  "eventId": "evt_20260528_123456789",
  "campaignId": "bf_abc123"
}
```

No campaign created because the cancellation is not eligible:

```json
{
  "status": "ignored",
  "eventId": "evt_20260528_123456789",
  "reason": "cancellation_inside_min_notice_window"
}
```

Duplicate event:

```json
{
  "status": "duplicate",
  "eventId": "evt_20260528_123456789"
}
```

Recommended HTTP statuses:

| HTTP status | Meaning |
|---:|---|
| 202 | Event accepted, duplicate, or intentionally ignored after successful validation. |
| 400 | Invalid JSON or missing required body fields. |
| 401 | Missing authentication headers. |
| 403 | Invalid bearer token. |
| 409 | Conflicting duplicate payload for same event ID. |
| 500 | Transient server error; RadFlow should retry. |

## Retry Behavior

RadFlow should retry on network errors, timeouts, and `5xx` responses.

Recommended retry schedule:

```text
1 minute, 5 minutes, 15 minutes, 1 hour
```

Do not retry `2xx`, `4xx`, or `409` responses unless requested manually.

## Follow-On APIs Still Needed

This webhook only tells the backfill service that a slot was canceled. The full agent also needs:

- An API to query scheduled candidate appointments filtered by `facilityId`, `cptCode`, and scheduled status.
- Candidate fields: appointment ID, patient ID, scheduled datetime, contact info, no-show flag, opt-out/suppression state.
- An API to atomically reschedule the winning patient into the freed slot, returning a clear failure if the slot is no longer available.
