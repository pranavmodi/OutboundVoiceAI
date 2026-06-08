"""Winner booking — local DB projection or external appointment API."""
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.appointment_data import Appointment
from app.models.backfill import BackfillCampaign, BackfillCandidate
from app.models.enums import AppointmentStatus


@dataclass
class BookingResult:
    success: bool
    winner_appointment_id: int | None = None
    message: str = ""


async def _local_reschedule(
    session: AsyncSession,
    *,
    campaign: BackfillCampaign,
    candidate: BackfillCandidate,
) -> BookingResult:
    """Move the winner's appointment into the canceled open slot (dev/simulator)."""
    open_slot = await session.get(Appointment, campaign.cancelled_appointment_id)
    if open_slot is None:
        return BookingResult(success=False, message="Canceled open-slot appointment not found")
    if open_slot.status != AppointmentStatus.CANCELED.value:
        return BookingResult(success=False, message="Open slot is no longer available")

    winner_appt = await session.get(Appointment, candidate.appointment_id)
    if winner_appt is None:
        return BookingResult(success=False, message="Winner appointment not found")
    if winner_appt.status != AppointmentStatus.SCHEDULED.value:
        return BookingResult(success=False, message="Winner appointment is not schedulable")

    winner_appt.scheduled_start_at = campaign.open_slot_start_at
    await session.flush()
    return BookingResult(
        success=True,
        winner_appointment_id=winner_appt.id,
        message="Winner rescheduled into open slot (local projection)",
    )


async def _http_reschedule(
    session: AsyncSession,
    *,
    campaign: BackfillCampaign,
    candidate: BackfillCandidate,
) -> BookingResult:
    base = settings.backfill_appointment_api_base_url.rstrip("/")
    token = settings.backfill_appointment_api_token
    if not base:
        return BookingResult(success=False, message="Appointment API base URL is not configured")

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {
        "campaignId": campaign.id,
        "cancelledAppointmentId": campaign.cancelled_appointment_id,
        "winnerAppointmentId": candidate.appointment_id,
        "winnerPatientId": candidate.patient_id,
        "targetStartDateTime": campaign.open_slot_start_at.isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base}/reschedule", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        return BookingResult(success=False, message=f"Appointment API request failed: {exc}")

    if response.status_code >= 400:
        detail = response.text[:200] if response.text else response.reason_phrase
        return BookingResult(
            success=False,
            message=f"Appointment API rejected reschedule ({response.status_code}): {detail}",
        )

    data = response.json() if response.content else {}
    winner_id = data.get("winnerAppointmentId") or candidate.appointment_id
    if isinstance(winner_id, str) and winner_id.isdigit():
        winner_id = int(winner_id)

    # Refresh local projection when API succeeds.
    winner_appt = await session.get(Appointment, candidate.appointment_id)
    if winner_appt is not None and winner_appt.status == AppointmentStatus.SCHEDULED.value:
        winner_appt.scheduled_start_at = campaign.open_slot_start_at
        await session.flush()

    return BookingResult(
        success=True,
        winner_appointment_id=int(winner_id) if winner_id is not None else candidate.appointment_id,
        message="Winner rescheduled via appointment API",
    )


async def reschedule_winner_into_open_slot(
    session: AsyncSession,
    *,
    campaign: BackfillCampaign,
    candidate: BackfillCandidate,
) -> BookingResult:
    """Reschedule the winning candidate into the campaign's open slot."""
    if settings.backfill_appointment_api_base_url.strip():
        return await _http_reschedule(session, campaign=campaign, candidate=candidate)
    return await _local_reschedule(session, campaign=campaign, candidate=candidate)
