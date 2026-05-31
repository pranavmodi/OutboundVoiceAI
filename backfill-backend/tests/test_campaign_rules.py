"""Milestone 6.1 — unit tests for candidate eligibility rules."""
import unittest
from datetime import datetime, timezone

from app.models.appointment_data import Appointment, Patient
from app.models.enums import CandidateEligibilityStatus
from app.services.campaign_service import _evaluate_row


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


if __name__ == "__main__":
    unittest.main()
