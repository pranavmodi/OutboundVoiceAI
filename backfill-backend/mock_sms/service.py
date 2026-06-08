"""Mock SMS send/receive — delegates interest handling to inbound_sms_service."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.appointment_data import Patient
from app.models.backfill import BackfillCampaign, BackfillCandidate
from app.models.enums import CampaignStatus, CandidateEligibilityStatus
from app.services.inbound_sms_service import handle_inbound_sms
from mock_sms import store


def mock_from_number() -> str:
    return settings.twilio_sms_from_number or "MOCK-SENDER"


async def simulate_reply(
    session: AsyncSession,
    *,
    campaign_id: int,
    body: str,
    patient_id: int | None,
) -> tuple[str, int | None, int | None, str | None]:
    campaign = await session.get(BackfillCampaign, campaign_id)
    if campaign is None:
        return "not_found", None, None, "Campaign not found"
    if campaign.campaign_status != CampaignStatus.RUNNING.value:
        return "campaign_not_running", campaign_id, None, f"Campaign is {campaign.campaign_status}"

    if patient_id is not None:
        candidate = await session.scalar(
            select(BackfillCandidate).where(
                BackfillCandidate.backfill_campaign_id == campaign_id,
                BackfillCandidate.patient_id == patient_id,
            )
        )
    else:
        candidate = await session.scalar(
            select(BackfillCandidate)
            .where(
                BackfillCandidate.backfill_campaign_id == campaign_id,
                BackfillCandidate.eligibility_status == CandidateEligibilityStatus.ELIGIBLE.value,
                BackfillCandidate.current_contact_status.in_(
                    [
                        CandidateEligibilityStatus.TEXT_SENT.value,
                        CandidateEligibilityStatus.CALL_PLACED.value,
                    ]
                ),
            )
            .order_by(BackfillCandidate.rank_order.asc(), BackfillCandidate.id.asc())
            .limit(1)
        )

    if candidate is None:
        return "no_candidate", campaign_id, None, "No eligible contacted candidate"

    if candidate.current_contact_status not in {
        CandidateEligibilityStatus.TEXT_SENT.value,
        CandidateEligibilityStatus.CALL_PLACED.value,
    }:
        return (
            "already_responded",
            campaign_id,
            candidate.id,
            f"Patient already responded ({candidate.current_contact_status})",
        )

    patient = await session.get(Patient, candidate.patient_id)
    if patient is None or not patient.phone:
        return "no_phone", campaign_id, candidate.id, "Patient has no phone"

    message_sid = store.new_provider_id()
    store.record_inbound(
        campaign_id=campaign_id,
        candidate_id=candidate.id,
        patient_id=patient.id,
        patient_name=patient.name,
        from_number=patient.phone,
        to_number=mock_from_number(),
        body=body,
        provider_message_id=message_sid,
    )

    result = await handle_inbound_sms(
        session,
        from_number=patient.phone,
        body=body,
        message_sid=message_sid,
        payload={"simulated": True, "mock_sms": True, "campaign_id": campaign_id},
    )
    return result.status, result.campaign_id, result.candidate_id, result.message
