"""RadFlow webhook — auth, validation, and idempotency (DB tests optional)."""
import os
import unittest

from fastapi.testclient import TestClient

os.environ["RADFLOW_WEBHOOK_TOKEN"] = "test-webhook-token"
os.environ["RADFLOW_WEBHOOK_ENABLED"] = "true"

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

settings.radflow_webhook_token = "test-webhook-token"
settings.radflow_webhook_enabled = True

SAMPLE_BODY = {
    "eventType": "appointment.cancelled",
    "eventId": "evt_test_001",
    "occurredAt": "2026-05-28T18:42:15Z",
    "appointment": {
        "appointmentId": "APT-TEST-001",
        "status": "Canceled",
        "previousStatus": "Scheduled",
        "canceledAt": "2026-05-28T18:42:15Z",
        "startDateTime": "2026-05-30T17:00:00-07:00",
        "timezone": "America/Los_Angeles",
        "facilityId": "FAC-TEST-001",
        "facilityName": "Test Facility",
        "cptCode": "74183",
        "procedureDescription": "MRI test",
    },
    "patient": {
        "patientId": "PAT-TEST-001",
        "patientName": "Test Patient",
        "phone": "+13105551212",
    },
    "metadata": {"sourceSystem": "RadFlow", "tenantId": "test"},
}

WEBHOOK_PATH = "/api/integrations/radflow/appointment-cancellations"


class RadflowWebhookAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_missing_auth_returns_401(self) -> None:
        response = self.client.post(
            WEBHOOK_PATH,
            json=SAMPLE_BODY,
            headers={"X-RadFlow-Event-Id": "evt_auth_001"},
        )
        self.assertEqual(response.status_code, 401)

    def test_invalid_token_returns_401(self) -> None:
        response = self.client.post(
            WEBHOOK_PATH,
            json=SAMPLE_BODY,
            headers={
                "Authorization": "Bearer wrong-token",
                "X-RadFlow-Event-Id": "evt_auth_002",
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_missing_event_id_header_returns_400(self) -> None:
        response = self.client.post(
            WEBHOOK_PATH,
            json=SAMPLE_BODY,
            headers={"Authorization": "Bearer test-webhook-token"},
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_body_returns_422(self) -> None:
        response = self.client.post(
            WEBHOOK_PATH,
            json={"eventType": "appointment.cancelled"},
            headers={
                "Authorization": "Bearer test-webhook-token",
                "X-RadFlow-Event-Id": "evt_auth_003",
            },
        )
        self.assertEqual(response.status_code, 422)


class RadflowWebhookServiceTests(unittest.TestCase):
    def test_map_cancel_messages(self) -> None:
        from app.services.radflow_webhook_service import _map_cancel_message

        class _Camp:
            id = 1

        status, _ = _map_cancel_message(_Camp(), "Appointment canceled; campaign created.")
        self.assertEqual(status, "campaign_created")

        status, _ = _map_cancel_message(None, "Campaign already exists for this appointment.")
        self.assertEqual(status, "campaign_exists")

        status, _ = _map_cancel_message(
            None, "Cancellation is only 9.0h before exam; minimum is 24h."
        )
        self.assertEqual(status, "ineligible")


if __name__ == "__main__":
    unittest.main()
