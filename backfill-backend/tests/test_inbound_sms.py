"""Inbound SMS helper tests."""
import unittest

from app.services.inbound_sms_service import normalize_phone, parse_sms_intent


class InboundSmsHelperTests(unittest.TestCase):
    def test_normalize_phone(self) -> None:
        self.assertEqual(normalize_phone(" +1 (310) 555-1212 "), "+13105551212")

    def test_parse_yes_variants(self) -> None:
        self.assertEqual(parse_sms_intent("YES"), "yes")
        self.assertEqual(parse_sms_intent("y"), "yes")

    def test_parse_no_variants(self) -> None:
        self.assertEqual(parse_sms_intent("NO"), "no")
        self.assertEqual(parse_sms_intent("stop"), "no")

    def test_parse_unknown(self) -> None:
        self.assertEqual(parse_sms_intent("maybe later"), "unknown")


if __name__ == "__main__":
    unittest.main()
