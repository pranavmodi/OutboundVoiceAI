"""Inbound SMS handling for YES/NO responses."""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_data import Patient
from app.models.backfill import BackfillCandidate, BackfillCampaign
from app.models.enums import ActionChannel, CampaignStatus, CandidateEligibilityStatus
from app.services.audit_service import log_action
from app.services.response_processor import handle_decline, handle_interest


def normalize_phone(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")


def parse_sms_intent(body: str | None) -> str:
    text = (body or "").strip().lower()
    if not text:
        return "unknown"
    if text in {"yes", "y", "interested"}:
        return "yes"
    if text in {"no", "n", "decline", "stop"}:
        return "no"
    return "unknown"


@dataclass
class InboundResult:
    status: str
    campaign_id: int | None = None
    candidate_id: int | None = None
    message: str | None = None


async def _find_candidate_for_phone(session: AsyncSession, from_number: str) -> tuple[BackfillCandidate, BackfillCampaign] | None:
    normalized = normalize_phone(from_number)
    if not normalized:
        return None
    result = await session.execute(
        select(BackfillCandidate, BackfillCampaign, Patient)
        .join(BackfillCampaign, BackfillCampaign.id == BackfillCandidate.backfill_campaign_id)
        .join(Patient, Patient.id == BackfillCandidate.patient_id)
        .where(
            BackfillCampaign.campaign_status == CampaignStatus.RUNNING.value,
            Patient.phone.is_not(None),
        )
        .order_by(
            BackfillCampaign.last_wave_at.desc().nullslast(),
            BackfillCandidate.rank_order.asc(),
            BackfillCampaign.id.desc(),
        )
    )
    for candidate, campaign, patient in result.all():
        if normalize_phone(patient.phone) != normalized:
            continue
        if candidate.current_contact_status not in {
            CandidateEligibilityStatus.TEXT_SENT.value,
            CandidateEligibilityStatus.CALL_PLACED.value,
        }:
            continue
        return candidate, campaign
    return None


async def handle_inbound_sms(
    session: AsyncSession,
    *,
    from_number: str,
    body: str | None,
    message_sid: str | None,
    payload: dict | None = None,
) -> InboundResult:
    match = await _find_candidate_for_phone(session, from_number=from_number)
    if match is None:
        return InboundResult(status="orphan_reply", message="No matching running campaign candidate")
    candidate, campaign = match
    intent = parse_sms_intent(body)
    if intent == "unknown":
        await log_action(
            session,
            campaign_id=campaign.id,
            candidate_id=candidate.id,
            action_type="SmsInboundReceived",
            outcome="Unrecognized",
            channel=ActionChannel.SMS.value,
            provider_message_id=message_sid,
            payload=payload,
        )
        return InboundResult(
            status="unrecognized_reply",
            campaign_id=campaign.id,
            candidate_id=candidate.id,
            message="Reply not recognized",
        )

    if intent == "yes":
        result = await handle_interest(
            session,
            candidate_id=candidate.id,
            channel=ActionChannel.SMS.value,
            provider_message_id=message_sid,
            payload=payload,
        )
        return InboundResult(
            status=result.outcome,
            campaign_id=result.campaign_id,
            candidate_id=result.candidate_id,
            message=result.message,
        )

    decline = await handle_decline(
        session,
        candidate_id=candidate.id,
        channel=ActionChannel.SMS.value,
        provider_message_id=message_sid,
        payload=payload,
    )
    return InboundResult(
        status="declined",
        campaign_id=decline.campaign_id,
        candidate_id=decline.candidate_id,
        message=decline.message,
    )
