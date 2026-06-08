"""SMS webhook auth and shape tests."""
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

os.environ["TWILIO_WEBHOOK_AUTH_ENABLED"] = "false"

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402


class SmsWebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        settings.twilio_webhook_auth_enabled = False

    @patch("app.api.webhooks_sms.handle_inbound_sms", new_callable=AsyncMock)
    def test_inbound_accepts_form_payload(self, mock_handle) -> None:
        from app.services.inbound_sms_service import InboundResult

        mock_handle.return_value = InboundResult(status="orphan_reply", message="No match")
        response = self.client.post(
            "/api/webhooks/sms/inbound",
            data={"From": "+13105551212", "Body": "YES", "MessageSid": "SM123"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("status", body)
        self.assertIn(
            body["status"],
            {
                "orphan_reply",
                "processed",
                "unrecognized_reply",
                "winner",
                "lost_slot",
                "declined",
                "already_winner",
                "already_lost",
            },
        )

    def test_status_callback_accepts_payload(self) -> None:
        response = self.client.post(
            "/api/webhooks/sms/status",
            data={"MessageSid": "SM123", "MessageStatus": "delivered"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")

    def test_inbound_requires_signature_when_enabled(self) -> None:
        settings.twilio_webhook_auth_enabled = True
        settings.twilio_auth_token = "test-token"
        settings.backfill_public_base_url = "https://example.com"
        response = self.client.post(
            "/api/webhooks/sms/inbound",
            data={"From": "+13105551212", "Body": "YES", "MessageSid": "SM123"},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
