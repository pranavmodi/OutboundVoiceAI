"""Milestone 6.1 — unit tests for candidate eligibility rules."""
import unittest
from datetime import date, datetime, time, timezone

from app.models.appointment_data import Appointment, Patient
from app.models.backfill import BackfillAgentSettings
from app.models.enums import CandidateEligibilityStatus
from app.services.campaign_service import _evaluate_row
from app.services.settings_service import settings_snapshot


class _Settings:
    exclude_no_show_enabled = True


class CampaignRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.open_slot = datetime(2026, 6, 11, 13, 0, tzinfo=timezone.utc)
        self.canceled = Appointment(
            id=18,
            patient_id=1,
            facility_id=1,
            cpt_code="MRI_BRAIN",
            status="canceled",
            scheduled_start_at=self.open_slot,
        )
        self.patient = Patient(
            id=2,
            name="Tin",
            phone="+15551000002",
            sms_opt_out=False,
            no_show_flag=False,
            suppressed=False,
        )

    def test_excludes_appointment_before_open_slot(self) -> None:
        before = Appointment(
            id=17,
            patient_id=2,
            facility_id=1,
            cpt_code="MRI_BRAIN",
            status="scheduled",
            scheduled_start_at=datetime(2026, 6, 9, 16, 0, tzinfo=timezone.utc),
        )
        status, reason = _evaluate_row(before, self.patient, self.canceled, _Settings())
        self.assertEqual(status, CandidateEligibilityStatus.EXCLUDED_NOT_AFTER_OPEN_SLOT.value)
        self.assertIn("open slot", reason or "")

    def test_eligible_when_scheduled_after_open_slot(self) -> None:
        after = Appointment(
            id=20,
            patient_id=2,
            facility_id=1,
            cpt_code="MRI_BRAIN",
            status="scheduled",
            scheduled_start_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        )
        status, reason = _evaluate_row(after, self.patient, self.canceled, _Settings())
        self.assertEqual(status, CandidateEligibilityStatus.ELIGIBLE.value)
        self.assertIsNone(reason)

    def test_excludes_same_datetime_as_open_slot(self) -> None:
        same_time = Appointment(
            id=21,
            patient_id=3,
            facility_id=1,
            cpt_code="MRI_BRAIN",
            status="scheduled",
            scheduled_start_at=self.open_slot,
        )
        status, _ = _evaluate_row(same_time, self.patient, self.canceled, _Settings())
        self.assertEqual(status, CandidateEligibilityStatus.EXCLUDED_NOT_AFTER_OPEN_SLOT.value)

    def test_excludes_sms_opt_out(self) -> None:
        after = Appointment(
            id=22,
            patient_id=2,
            facility_id=1,
            cpt_code="MRI_BRAIN",
            status="scheduled",
            scheduled_start_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        )
        self.patient.sms_opt_out = True

        status, reason = _evaluate_row(after, self.patient, self.canceled, _Settings())
        self.assertEqual(status, CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value)
        self.assertEqual(reason, "SMS opt-out")

    def test_excludes_suppressed_patient(self) -> None:
        after = Appointment(
            id=23,
            patient_id=2,
            facility_id=1,
            cpt_code="MRI_BRAIN",
            status="scheduled",
            scheduled_start_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        )
        self.patient.suppressed = True

        status, reason = _evaluate_row(after, self.patient, self.canceled, _Settings())
        self.assertEqual(status, CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value)
        self.assertEqual(reason, "Suppressed by backfill suppression rules")

    def test_settings_snapshot_contains_m1_runtime_settings(self) -> None:
        settings = BackfillAgentSettings(
            id=1,
            enabled=True,
            minimum_cancellation_notice_hours=36,
            sms_batch_size_per_wave=4,
            delay_between_waves_minutes=15,
            max_waves=5,
            ai_call_escalation_enabled=False,
            ai_call_quantity_per_wave=2,
            allowed_contact_days="mon,wed,fri",
            contact_window_start=time(9, 30),
            contact_window_end=time(17, 15),
            contact_window_timezone="America/New_York",
            use_shared_holiday_calendar=False,
            agent_blackout_dates=[date(2026, 7, 4).isoformat()],
            same_facility_required=True,
            same_cpt_required=True,
            exclude_no_show_enabled=False,
            campaign_timeout_minutes=90,
            late_response_closeout_enabled=False,
            allowed_sms_template_id=11,
            allowed_voice_template_id=22,
            closeout_message_template_id=33,
        )

        snapshot = settings_snapshot(settings)

        expected_keys = {
            "enabled",
            "minimum_cancellation_notice_hours",
            "sms_batch_size_per_wave",
            "delay_between_waves_minutes",
            "max_waves",
            "ai_call_escalation_enabled",
            "ai_call_quantity_per_wave",
            "allowed_contact_days",
            "contact_window_start",
            "contact_window_end",
            "contact_window_timezone",
            "use_shared_holiday_calendar",
            "agent_blackout_dates",
            "same_facility_required",
            "same_cpt_required",
            "exclude_no_show_enabled",
            "campaign_timeout_minutes",
            "late_response_closeout_enabled",
            "allowed_sms_template_id",
            "allowed_voice_template_id",
            "closeout_message_template_id",
        }
        self.assertEqual(set(snapshot), expected_keys)
        self.assertEqual(snapshot["minimum_cancellation_notice_hours"], 36)
        self.assertEqual(snapshot["contact_window_start"], "09:30:00")
        self.assertEqual(snapshot["allowed_sms_template_id"], 11)


if __name__ == "__main__":
    unittest.main()
