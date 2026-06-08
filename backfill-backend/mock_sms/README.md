# Mock SMS (dev only)

Simulates outbound and inbound SMS when `BACKFILL_SMS_PROVIDER=mock`. **Not mounted in production** — use `BACKFILL_SMS_PROVIDER=twilio`.

## Flow

1. Cancel appointment → campaign **Running** → wave worker calls `send_offer_sms` → message stored in memory + `SmsSent` log.
2. UI: `GET /api/mock-sms/campaigns/{id}/messages` shows the thread.
3. Dev clicks **Patient replies YES/NO** → `POST /api/mock-sms/campaigns/{id}/reply` → same handler as Twilio inbound → **Interested** / **Declined**.

## API

| Method | Path |
|--------|------|
| GET | `/api/mock-sms/campaigns/{campaign_id}/messages` |
| POST | `/api/mock-sms/campaigns/{campaign_id}/reply` `{ "body": "yes", "patient_id": null }` |

## Local `.env`

```env
BACKFILL_SMS_PROVIDER=mock
BACKFILL_WAVE_WORKER_ENABLED=true
```

Restart backfill backend after changing provider.
