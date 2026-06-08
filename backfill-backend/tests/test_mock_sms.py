"""Mock SMS store and API tests."""
import unittest

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from mock_sms import store


class MockSmsTests(unittest.TestCase):
    def setUp(self) -> None:
        if not settings.backfill_simulator_enabled:
            self.skipTest("BACKFILL_SIMULATOR_ENABLED=false")
        self.client = TestClient(app)

    def test_list_messages_empty_campaign(self) -> None:
        response = self.client.get("/api/mock-sms/campaigns/1/messages")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_record_outbound_visible_in_list(self) -> None:
        store.record_outbound(
            campaign_id=99901,
            candidate_id=1,
            patient_id=13,
            patient_name="Test",
            from_number="MOCK",
            to_number="+15551234",
            body="Hello",
            provider_message_id="SM_sim_test_list",
        )
        response = self.client.get("/api/mock-sms/campaigns/99901/messages")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["direction"], "outbound")


if __name__ == "__main__":
    unittest.main()
