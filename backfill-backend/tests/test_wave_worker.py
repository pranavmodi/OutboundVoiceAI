"""Unit tests for wave worker scheduling helpers."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.wave_worker import (
    _allowed_weekdays,
    _build_wave_sms_message,
    _campaign_delay_minutes,
    _campaign_max_waves,
    _is_contact_allowed_now,
    _is_wave_due,
    _blackout_dates,
    _settings_value,
)


class WaveWorkerHelperTests(unittest.TestCase):
    def test_settings_value_uses_default_on_invalid(self) -> None:
        self.assertEqual(_settings_value(None, "max_waves", 3), 3)
        self.assertEqual(_settings_value({"max_waves": "abc"}, "max_waves", 3), 3)
        self.assertEqual(_settings_value({"max_waves": 0}, "max_waves", 3), 3)

    def test_settings_value_reads_positive_int(self) -> None:
        self.assertEqual(_settings_value({"max_waves": "5"}, "max_waves", 3), 5)

    def test_campaign_snapshot_settings(self) -> None:
        campaign = SimpleNamespace(settings_snapshot={"max_waves": 7, "delay_between_waves_minutes": 12})
        self.assertEqual(_campaign_max_waves(campaign), 7)
        self.assertEqual(_campaign_delay_minutes(campaign), 12)

    def test_wave_due_on_first_wave(self) -> None:
        campaign = SimpleNamespace(last_wave_at=None, settings_snapshot={"delay_between_waves_minutes": 10})
        self.assertTrue(_is_wave_due(campaign, datetime.now(timezone.utc)))

    def test_wave_due_after_delay(self) -> None:
        now = datetime.now(timezone.utc)
        campaign = SimpleNamespace(
            last_wave_at=now - timedelta(minutes=11),
            settings_snapshot={"delay_between_waves_minutes": 10},
        )
        self.assertTrue(_is_wave_due(campaign, now))

    def test_wave_not_due_before_delay(self) -> None:
        now = datetime.now(timezone.utc)
        campaign = SimpleNamespace(
            last_wave_at=now - timedelta(minutes=5),
            settings_snapshot={"delay_between_waves_minutes": 10},
        )
        self.assertFalse(_is_wave_due(campaign, now))

    def test_allowed_weekdays_parse(self) -> None:
        weekdays = _allowed_weekdays({"allowed_contact_days": "mon,wed,fri"})
        self.assertEqual(weekdays, {0, 2, 4})

    def test_blackout_dates_parse(self) -> None:
        dates = _blackout_dates({"agent_blackout_dates": ["2026-07-04", "bad"]})
        self.assertEqual({d.isoformat() for d in dates}, {"2026-07-04"})

    def test_contact_allowed_within_window(self) -> None:
        campaign = SimpleNamespace(
            settings_snapshot={
                "allowed_contact_days": "mon,tue,wed,thu,fri,sat,sun",
                "contact_window_start": "08:00:00",
                "contact_window_end": "18:00:00",
                "contact_window_timezone": "UTC",
                "agent_blackout_dates": [],
            }
        )
        now = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(_is_contact_allowed_now(campaign, now))

    def test_contact_blocked_outside_window(self) -> None:
        campaign = SimpleNamespace(
            settings_snapshot={
                "allowed_contact_days": "mon,tue,wed,thu,fri,sat,sun",
                "contact_window_start": "08:00:00",
                "contact_window_end": "18:00:00",
                "contact_window_timezone": "UTC",
                "agent_blackout_dates": [],
            }
        )
        now = datetime(2026, 6, 2, 19, 0, tzinfo=timezone.utc)
        self.assertFalse(_is_contact_allowed_now(campaign, now))

    def test_contact_blocked_on_blackout_date(self) -> None:
        campaign = SimpleNamespace(
            settings_snapshot={
                "allowed_contact_days": "mon,tue,wed,thu,fri,sat,sun",
                "contact_window_start": "08:00:00",
                "contact_window_end": "18:00:00",
                "contact_window_timezone": "UTC",
                "agent_blackout_dates": ["2026-06-02"],
            }
        )
        now = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
        self.assertFalse(_is_contact_allowed_now(campaign, now))

    def test_sms_message_contains_campaign_and_wave(self) -> None:
        campaign = SimpleNamespace(id=42)
        body = _build_wave_sms_message(campaign, wave_number=3)
        self.assertIn("Campaign 42", body)
        self.assertIn("Wave 3", body)


if __name__ == "__main__":
    unittest.main()
