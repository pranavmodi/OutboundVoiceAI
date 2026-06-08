"""Response processor — snapshot helpers and optional DB integration."""
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from app.models.enums import CampaignStatus, CandidateEligibilityStatus
from app.services.response_processor import _snapshot_flag


class SnapshotFlagTests(unittest.TestCase):
    def test_defaults_true_when_missing(self) -> None:
        self.assertTrue(_snapshot_flag(None, "late_response_closeout_enabled"))

    def test_reads_false_from_snapshot(self) -> None:
        self.assertFalse(
            _snapshot_flag({"late_response_closeout_enabled": False}, "late_response_closeout_enabled")
        )


class ResponseProcessorConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    """Simulate two interested candidates where only one should win."""

    async def test_second_interest_loses_after_campaign_filled(self) -> None:
        from app.db import AsyncSessionLocal
        from app.models.appointment_data import Appointment, Facility, Patient
        from app.models.backfill import BackfillCampaign, BackfillCandidate
        from app.services.response_processor import handle_interest

        db_url = os.environ.get("BACKFILL_DATABASE_URL", "")
        if not db_url or ("localhost" not in db_url and "127.0.0.1" not in db_url):
            self.skipTest("Set BACKFILL_DATABASE_URL to a local postgres for integration test")

        open_slot_at = datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            facility = Facility(name="Test Facility RP", timezone="UTC")
            session.add(facility)
            await session.flush()

            cancelled_patient = Patient(name="Cancelled Patient", phone="+15550000001")
            winner_patient = Patient(name="Winner Patient", phone="+15550000002")
            loser_patient = Patient(name="Loser Patient", phone="+15550000003")
            session.add_all([cancelled_patient, winner_patient, loser_patient])
            await session.flush()

            cancelled_appt = Appointment(
                patient_id=cancelled_patient.id,
                facility_id=facility.id,
                cpt_code="MRI_TEST",
                status="canceled",
                scheduled_start_at=open_slot_at,
                cancelled_at=datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc),
            )
            winner_appt = Appointment(
                patient_id=winner_patient.id,
                facility_id=facility.id,
                cpt_code="MRI_TEST",
                status="scheduled",
                scheduled_start_at=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
            )
            loser_appt = Appointment(
                patient_id=loser_patient.id,
                facility_id=facility.id,
                cpt_code="MRI_TEST",
                status="scheduled",
                scheduled_start_at=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
            )
            session.add_all([cancelled_appt, winner_appt, loser_appt])
            await session.flush()

            campaign = BackfillCampaign(
                cancelled_appointment_id=cancelled_appt.id,
                cancelled_patient_id=cancelled_patient.id,
                facility_id=facility.id,
                cpt_code="MRI_TEST",
                open_slot_start_at=open_slot_at,
                cancellation_at=datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc),
                min_notice_hours_applied=24,
                campaign_status=CampaignStatus.RUNNING.value,
                settings_snapshot={"late_response_closeout_enabled": False},
            )
            session.add(campaign)
            await session.flush()

            winner_candidate = BackfillCandidate(
                backfill_campaign_id=campaign.id,
                patient_id=winner_patient.id,
                appointment_id=winner_appt.id,
                facility_id=facility.id,
                cpt_code="MRI_TEST",
                scheduled_appointment_at=winner_appt.scheduled_start_at,
                rank_order=1,
                eligibility_status=CandidateEligibilityStatus.ELIGIBLE.value,
                current_contact_status=CandidateEligibilityStatus.TEXT_SENT.value,
            )
            loser_candidate = BackfillCandidate(
                backfill_campaign_id=campaign.id,
                patient_id=loser_patient.id,
                appointment_id=loser_appt.id,
                facility_id=facility.id,
                cpt_code="MRI_TEST",
                scheduled_appointment_at=loser_appt.scheduled_start_at,
                rank_order=2,
                eligibility_status=CandidateEligibilityStatus.ELIGIBLE.value,
                current_contact_status=CandidateEligibilityStatus.TEXT_SENT.value,
            )
            session.add_all([winner_candidate, loser_candidate])
            await session.commit()

            campaign_id = campaign.id
            winner_id = winner_candidate.id
            loser_id = loser_candidate.id
            winner_patient_id = winner_patient.id
            winner_appt_id = winner_appt.id

        with mock.patch("app.services.response_processor.send_offer_sms", return_value="SM_CLOSEOUT"):
            async with AsyncSessionLocal() as session:
                first = await handle_interest(session, candidate_id=winner_id)
                await session.commit()
                self.assertEqual(first.outcome, "winner")

            async with AsyncSessionLocal() as session:
                second = await handle_interest(session, candidate_id=loser_id)
                await session.commit()
                self.assertEqual(second.outcome, "lost_slot")

            async with AsyncSessionLocal() as session:
                refreshed = await session.get(BackfillCampaign, campaign_id)
                assert refreshed is not None
                self.assertEqual(refreshed.campaign_status, CampaignStatus.FILLED.value)
                self.assertEqual(refreshed.filled_by_patient_id, winner_patient_id)

                loser = await session.get(BackfillCandidate, loser_id)
                assert loser is not None
                self.assertTrue(loser.lost_slot_flag)
                self.assertEqual(loser.current_contact_status, CandidateEligibilityStatus.LOST_SLOT.value)

                winner_appt_row = await session.get(Appointment, winner_appt_id)
                assert winner_appt_row is not None
                self.assertEqual(winner_appt_row.scheduled_start_at, open_slot_at)


if __name__ == "__main__":
    unittest.main()
