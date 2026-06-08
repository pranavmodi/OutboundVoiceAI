"""Atomic winner assignment and late-response handling — M2 Phase 5."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_data import Appointment, Patient
from app.models.backfill import BackfillCampaign, BackfillCandidate
from app.models.enums import ActionChannel, AppointmentStatus, CampaignStatus, CandidateEligibilityStatus
from app.services.appointment_booking_service import reschedule_winner_into_open_slot
from app.services.audit_service import log_action
from app.services.sms_provider import send_offer_sms

InterestOutcome = Literal[
    "winner",
    "lost_slot",
    "already_winner",
    "already_lost",
    "declined",
    "campaign_not_running",
    "candidate_invalid",
    "booking_failed",
]

DEFAULT_CLOSEOUT_MESSAGE = (
    "Thank you for your interest. This appointment slot has already been filled."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_flag(snapshot: dict[str, Any] | None, key: str, default: bool = True) -> bool:
    if not snapshot:
        return default
    value = snapshot.get(key, default)
    return bool(value) if value is not None else default


@dataclass
class InterestResult:
    outcome: InterestOutcome
    campaign_id: int
    candidate_id: int
    message: str


@dataclass
class DeclineResult:
    campaign_id: int
    candidate_id: int
    message: str


async def _lock_campaign(session: AsyncSession, campaign_id: int) -> BackfillCampaign | None:
    result = await session.execute(
        select(BackfillCampaign)
        .where(BackfillCampaign.id == campaign_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _open_slot_available(session: AsyncSession, campaign: BackfillCampaign) -> bool:
    open_slot = await session.get(Appointment, campaign.cancelled_appointment_id)
    if open_slot is None:
        return False
    return open_slot.status == AppointmentStatus.CANCELED.value


async def _maybe_send_closeout_sms(
    session: AsyncSession,
    *,
    campaign: BackfillCampaign,
    candidate: BackfillCandidate,
    patient: Patient,
) -> None:
    if not _snapshot_flag(campaign.settings_snapshot, "late_response_closeout_enabled", True):
        return
    if not patient.phone:
        return
    try:
        provider_message_id = send_offer_sms(
            to_number=patient.phone,
            message_body=DEFAULT_CLOSEOUT_MESSAGE,
            campaign_id=campaign.id,
            candidate_id=candidate.id,
            patient_id=patient.id,
            patient_name=patient.name,
        )
        await log_action(
            session,
            campaign_id=campaign.id,
            candidate_id=candidate.id,
            action_type="CloseoutSmsSent",
            outcome="Sent",
            channel=ActionChannel.SMS.value,
            provider_message_id=provider_message_id,
            payload={"to": patient.phone},
        )
    except Exception as exc:
        await log_action(
            session,
            campaign_id=campaign.id,
            candidate_id=candidate.id,
            action_type="CloseoutSmsFailed",
            outcome=str(exc)[:64],
            channel=ActionChannel.SMS.value,
        )


async def _mark_lost_slot(
    session: AsyncSession,
    *,
    campaign: BackfillCampaign,
    candidate: BackfillCandidate,
    patient: Patient,
    message: str,
    send_closeout: bool,
    channel: str,
    provider_message_id: str | None,
    payload: dict | None,
    log_response: bool = True,
) -> InterestResult:
    now = _utcnow()
    candidate.interested_flag = True
    candidate.lost_slot_flag = True
    candidate.response_at = now
    candidate.current_contact_status = CandidateEligibilityStatus.LOST_SLOT.value
    if log_response:
        await log_action(
            session,
            campaign_id=campaign.id,
            candidate_id=candidate.id,
            action_type="ResponseReceived",
            outcome="LostSlot",
            channel=channel,
            provider_message_id=provider_message_id,
            payload=payload,
        )
    if send_closeout:
        await _maybe_send_closeout_sms(session, campaign=campaign, candidate=candidate, patient=patient)
    await session.flush()
    return InterestResult(
        outcome="lost_slot",
        campaign_id=campaign.id,
        candidate_id=candidate.id,
        message=message,
    )


async def handle_interest(
    session: AsyncSession,
    *,
    candidate_id: int,
    channel: str = ActionChannel.SMS.value,
    provider_message_id: str | None = None,
    payload: dict | None = None,
) -> InterestResult:
    """Assign a single winner or mark a late responder as LostSlot."""
    candidate = await session.get(BackfillCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")

    patient = await session.get(Patient, candidate.patient_id)
    if patient is None:
        return InterestResult(
            outcome="candidate_invalid",
            campaign_id=candidate.backfill_campaign_id,
            candidate_id=candidate.id,
            message="Patient not found for candidate",
        )

    if candidate.won_slot_flag or (
        candidate.current_contact_status == CandidateEligibilityStatus.SELECTED_WINNER.value
    ):
        return InterestResult(
            outcome="already_winner",
            campaign_id=candidate.backfill_campaign_id,
            candidate_id=candidate.id,
            message="Candidate already selected as winner",
        )

    if candidate.lost_slot_flag or (
        candidate.current_contact_status == CandidateEligibilityStatus.LOST_SLOT.value
    ):
        return InterestResult(
            outcome="already_lost",
            campaign_id=candidate.backfill_campaign_id,
            candidate_id=candidate.id,
            message="Candidate already marked as lost slot",
        )

    campaign = await _lock_campaign(session, candidate.backfill_campaign_id)
    if campaign is None:
        return InterestResult(
            outcome="campaign_not_running",
            campaign_id=candidate.backfill_campaign_id,
            candidate_id=candidate.id,
            message="Campaign not found",
        )

    if campaign.campaign_status != CampaignStatus.RUNNING.value:
        return await _mark_lost_slot(
            session,
            campaign=campaign,
            candidate=candidate,
            patient=patient,
            message="Campaign is no longer running; slot already filled or closed",
            send_closeout=True,
            channel=channel,
            provider_message_id=provider_message_id,
            payload=payload,
        )

    if not await _open_slot_available(session, campaign):
        campaign.campaign_status = CampaignStatus.CLOSED_SLOT_NO_LONGER_AVAILABLE.value
        campaign.closed_reason = "Open slot is no longer available"
        campaign.ended_at = _utcnow()
        await log_action(
            session,
            campaign_id=campaign.id,
            action_type="CampaignClosed",
            outcome=CampaignStatus.CLOSED_SLOT_NO_LONGER_AVAILABLE.value,
        )
        return await _mark_lost_slot(
            session,
            campaign=campaign,
            candidate=candidate,
            patient=patient,
            message="Open slot is no longer available",
            send_closeout=True,
            channel=channel,
            provider_message_id=provider_message_id,
            payload=payload,
        )

    await log_action(
        session,
        campaign_id=campaign.id,
        candidate_id=candidate.id,
        action_type="ResponseReceived",
        outcome="Interested",
        channel=channel,
        provider_message_id=provider_message_id,
        payload=payload,
    )

    booking = await reschedule_winner_into_open_slot(
        session,
        campaign=campaign,
        candidate=candidate,
    )
    if not booking.success:
        return await _mark_lost_slot(
            session,
            campaign=campaign,
            candidate=candidate,
            patient=patient,
            message=booking.message,
            send_closeout=True,
            channel=channel,
            provider_message_id=provider_message_id,
            payload=payload,
            log_response=False,
        )

    now = _utcnow()
    candidate.interested_flag = True
    candidate.won_slot_flag = True
    candidate.response_at = now
    candidate.current_contact_status = CandidateEligibilityStatus.SELECTED_WINNER.value

    campaign.campaign_status = CampaignStatus.FILLED.value
    campaign.filled_by_patient_id = candidate.patient_id
    campaign.filled_by_appointment_id = booking.winner_appointment_id or candidate.appointment_id
    campaign.closed_reason = "Slot filled by patient response"
    campaign.ended_at = now

    await log_action(
        session,
        campaign_id=campaign.id,
        candidate_id=candidate.id,
        action_type="WinnerAssigned",
        outcome=CampaignStatus.FILLED.value,
        channel=channel,
        provider_message_id=provider_message_id,
        payload={
            "filled_by_patient_id": candidate.patient_id,
            "filled_by_appointment_id": campaign.filled_by_appointment_id,
        },
    )
    await log_action(
        session,
        campaign_id=campaign.id,
        candidate_id=candidate.id,
        action_type="CampaignClosed",
        outcome=CampaignStatus.FILLED.value,
    )
    await session.flush()

    return InterestResult(
        outcome="winner",
        campaign_id=campaign.id,
        candidate_id=candidate.id,
        message="Winner assigned and campaign filled",
    )


async def handle_decline(
    session: AsyncSession,
    *,
    candidate_id: int,
    channel: str = ActionChannel.SMS.value,
    provider_message_id: str | None = None,
    payload: dict | None = None,
) -> DeclineResult:
    """Mark a candidate as declined — no further outreach in this campaign."""
    candidate = await session.get(BackfillCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")

    now = _utcnow()
    candidate.declined_flag = True
    candidate.response_at = now
    candidate.current_contact_status = CandidateEligibilityStatus.DECLINED.value
    await log_action(
        session,
        campaign_id=candidate.backfill_campaign_id,
        candidate_id=candidate.id,
        action_type="ResponseReceived",
        outcome="Declined",
        channel=channel,
        provider_message_id=provider_message_id,
        payload=payload,
    )
    await session.flush()
    return DeclineResult(
        campaign_id=candidate.backfill_campaign_id,
        candidate_id=candidate.id,
        message="Declined",
    )
