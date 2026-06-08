"""Cancellation trigger and candidate selection — spec trigger + candidate rules."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_data import Appointment, Facility, Patient
from app.models.backfill import BackfillCampaign, BackfillCandidate
from app.models.enums import (
    AppointmentStatus,
    CampaignStatus,
    CandidateEligibilityStatus,
)
from app.services.audit_service import log_action
from app.services.settings_service import get_or_create_settings, settings_snapshot
from app.services.suppression_service import get_sms_suppression_reason


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hours_between(start: datetime, end: datetime) -> float:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return (end - start).total_seconds() / 3600.0


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _existing_campaign(session: AsyncSession, appointment_id: int) -> BackfillCampaign | None:
    result = await session.execute(
        select(BackfillCampaign).where(BackfillCampaign.cancelled_appointment_id == appointment_id)
    )
    return result.scalar_one_or_none()


async def cancel_appointment_and_maybe_campaign(
    session: AsyncSession,
    appointment_id: int,
    cancelled_at: datetime | None = None,
) -> tuple[Appointment, BackfillCampaign | None, str]:
    """Mark appointment canceled and create backfill campaign when eligible."""
    settings = await get_or_create_settings(session)
    appt = await _require_appointment(session, appointment_id)
    when = cancelled_at or _utcnow()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    if not settings.enabled:
        appt.status = AppointmentStatus.CANCELED.value
        appt.cancelled_at = when
        await session.flush()
        return appt, None, "Agent disabled; appointment canceled but no campaign created."

    existing = await _existing_campaign(session, appointment_id)
    if existing is not None:
        return appt, existing, "Campaign already exists for this appointment."

    notice_hours = _hours_between(when, appt.scheduled_start_at)
    if notice_hours < settings.minimum_cancellation_notice_hours:
        return (
            appt,
            None,
            f"Cancellation is only {notice_hours:.1f}h before exam; "
            f"minimum is {settings.minimum_cancellation_notice_hours}h.",
        )

    appt.status = AppointmentStatus.CANCELED.value
    appt.cancelled_at = when
    await session.flush()

    campaign = BackfillCampaign(
        cancelled_appointment_id=appt.id,
        cancelled_patient_id=appt.patient_id,
        facility_id=appt.facility_id,
        cpt_code=appt.cpt_code,
        open_slot_start_at=appt.scheduled_start_at,
        cancellation_at=when,
        min_notice_hours_applied=settings.minimum_cancellation_notice_hours,
        campaign_status=CampaignStatus.PENDING.value,
        settings_snapshot=settings_snapshot(settings),
    )
    session.add(campaign)
    await session.flush()

    await log_action(
        session,
        campaign_id=campaign.id,
        action_type="CampaignCreated",
        outcome="Created",
        payload={"cancelled_appointment_id": appt.id, "notice_hours": notice_hours},
    )

    eligible_count = await _build_candidates(session, campaign, appt, settings)

    if eligible_count == 0:
        campaign.campaign_status = CampaignStatus.CLOSED_NO_CANDIDATES.value
        evaluated = await session.scalar(
            select(func.count())
            .select_from(BackfillCandidate)
            .where(BackfillCandidate.backfill_campaign_id == campaign.id)
        )
        if not evaluated:
            campaign.closed_reason = (
                "No scheduled appointments at this facility with the same CPT code"
            )
        else:
            campaign.closed_reason = "No eligible candidates"
        campaign.ended_at = _utcnow()
        await log_action(
            session,
            campaign_id=campaign.id,
            action_type="CampaignClosed",
            outcome=CampaignStatus.CLOSED_NO_CANDIDATES.value,
        )
        return appt, campaign, "Campaign created but closed: no eligible candidates."

    campaign.campaign_status = CampaignStatus.RUNNING.value
    await log_action(
        session,
        campaign_id=campaign.id,
        action_type="CandidatesBuilt",
        outcome=f"{eligible_count} eligible",
    )
    return appt, campaign, "Appointment canceled; campaign created."


async def stop_campaign_manually(session: AsyncSession, campaign_id: int) -> BackfillCampaign:
    """Close a running campaign — spec manual stop; wave engine respects in M2."""
    campaign = await session.get(BackfillCampaign, campaign_id)
    if campaign is None:
        raise ValueError("Campaign not found")
    if campaign.campaign_status != CampaignStatus.RUNNING.value:
        raise ValueError(
            f"Only running campaigns can be stopped (current status: {campaign.campaign_status})"
        )

    campaign.campaign_status = CampaignStatus.CLOSED_MANUALLY.value
    campaign.closed_reason = "Stopped manually by admin"
    campaign.ended_at = _utcnow()
    await log_action(
        session,
        campaign_id=campaign.id,
        action_type="CampaignClosed",
        outcome=CampaignStatus.CLOSED_MANUALLY.value,
    )
    await session.flush()
    return campaign


async def _require_appointment(session: AsyncSession, appointment_id: int) -> Appointment:
    appt = await session.get(Appointment, appointment_id)
    if appt is None:
        raise ValueError(f"Appointment {appointment_id} not found")
    return appt


async def _build_candidates(
    session: AsyncSession,
    campaign: BackfillCampaign,
    canceled_appt: Appointment,
    settings,
) -> int:
    """Evaluate scheduled appointments at same facility + CPT; persist ranked rows.

    Only appointments strictly after the open slot (date + time) can be eligible —
    spec: contact later-scheduled patients who may move into an earlier freed slot.
    """
    result = await session.execute(
        select(Appointment, Patient)
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(
            Appointment.facility_id == canceled_appt.facility_id,
            Appointment.cpt_code == canceled_appt.cpt_code,
            Appointment.status == AppointmentStatus.SCHEDULED.value,
        )
        .order_by(Appointment.scheduled_start_at.desc(), Appointment.id.asc())
    )
    rows = result.all()

    rank = 0
    eligible_count = 0
    for appt, patient in rows:
        status, reason = _evaluate_row(appt, patient, canceled_appt, settings)
        if status == CandidateEligibilityStatus.ELIGIBLE.value:
            rank += 1
            eligible_count += 1
            rank_order = rank
        else:
            rank_order = 9999

        session.add(
            BackfillCandidate(
                backfill_campaign_id=campaign.id,
                patient_id=patient.id,
                appointment_id=appt.id,
                facility_id=appt.facility_id,
                cpt_code=appt.cpt_code,
                scheduled_appointment_at=appt.scheduled_start_at,
                rank_order=rank_order,
                eligibility_status=status,
                exclusion_reason=reason,
            )
        )

    await session.flush()
    return eligible_count


def _evaluate_row(
    appt: Appointment,
    patient: Patient,
    canceled_appt: Appointment,
    settings,
) -> tuple[str, str | None]:
    if appt.id == canceled_appt.id:
        return CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value, "Same as canceled slot"

    open_slot_at = _as_utc(canceled_appt.scheduled_start_at)
    candidate_at = _as_utc(appt.scheduled_start_at)
    if candidate_at <= open_slot_at:
        return (
            CandidateEligibilityStatus.EXCLUDED_NOT_AFTER_OPEN_SLOT.value,
            "Scheduled appointment is on or before the open slot date and time",
        )

    if settings.exclude_no_show_enabled and patient.no_show_flag:
        return CandidateEligibilityStatus.EXCLUDED_NO_SHOW.value, "Patient has no-show flag"

    suppression_reason = get_sms_suppression_reason(patient)
    if suppression_reason:
        return CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value, suppression_reason

    if not patient.phone:
        return CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value, "Missing phone number"

    return CandidateEligibilityStatus.ELIGIBLE.value, None
