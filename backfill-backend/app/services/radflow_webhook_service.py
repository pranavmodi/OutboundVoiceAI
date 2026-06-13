"""RadFlow cancellation webhook — upsert projection and trigger campaign logic."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_data import Appointment, Facility, Patient
from app.models.enums import AppointmentStatus
from app.models.inbound_event import BackfillInboundEvent
from app.schemas.radflow import RadflowCancellationEvent, RadflowWebhookResponse, RadflowWebhookStatus
from app.services.campaign_service import cancel_appointment_and_maybe_campaign

RADFLOW_EVENT_TYPE = "appointment.cancelled"
CANCELED_STATUSES = {"canceled", "cancelled"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: datetime, fallback_tz: str | None = None) -> datetime:
    if value.tzinfo is None:
        if fallback_tz:
            value = value.replace(tzinfo=ZoneInfo(fallback_tz))
        else:
            value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_canceled_status(value: str) -> bool:
    return value.strip().lower() in CANCELED_STATUSES


async def get_inbound_event(
    session: AsyncSession, radflow_event_id: str
) -> BackfillInboundEvent | None:
    result = await session.execute(
        select(BackfillInboundEvent).where(
            BackfillInboundEvent.radflow_event_id == radflow_event_id
        )
    )
    return result.scalar_one_or_none()


def response_from_stored(event: BackfillInboundEvent) -> RadflowWebhookResponse:
    body = event.response_body
    return RadflowWebhookResponse.model_validate(body)


async def _get_by_external_id(
    session: AsyncSession, model: type[Facility] | type[Patient] | type[Appointment], external_id: str
):
    result = await session.execute(
        select(model).where(model.external_id == external_id)  # type: ignore[attr-defined]
    )
    return result.scalar_one_or_none()


async def _upsert_facility(session: AsyncSession, payload) -> Facility:
    facility = await _get_by_external_id(session, Facility, payload.facility_id)
    if facility is None:
        facility = Facility(
            external_id=payload.facility_id,
            name=payload.facility_name or payload.facility_id,
            timezone=payload.timezone,
        )
        session.add(facility)
    else:
        if payload.facility_name:
            facility.name = payload.facility_name
        facility.timezone = payload.timezone
    await session.flush()
    return facility


async def _upsert_patient(session: AsyncSession, payload) -> Patient:
    patient = await _get_by_external_id(session, Patient, payload.patient_id)
    display_name = payload.patient_name or payload.patient_id
    if patient is None:
        patient = Patient(
            external_id=payload.patient_id,
            name=display_name,
            phone=payload.phone,
        )
        session.add(patient)
    else:
        patient.name = display_name
        if payload.phone:
            patient.phone = payload.phone
    await session.flush()
    return patient


async def _upsert_appointment(
    session: AsyncSession,
    event: RadflowCancellationEvent,
    facility: Facility,
    patient: Patient,
) -> Appointment:
    appt_payload = event.appointment
    scheduled_start = _parse_datetime(appt_payload.start_date_time, appt_payload.timezone)
    canceled_at = _parse_datetime(appt_payload.canceled_at, appt_payload.timezone)

    appt = await _get_by_external_id(session, Appointment, appt_payload.appointment_id)
    if appt is None:
        appt = Appointment(
            external_id=appt_payload.appointment_id,
            patient_id=patient.id,
            facility_id=facility.id,
            cpt_code=appt_payload.cpt_code.strip().upper(),
            scheduled_start_at=scheduled_start,
            status=AppointmentStatus.CANCELED.value,
            cancelled_at=canceled_at,
            procedure_description=appt_payload.procedure_description,
        )
        session.add(appt)
    else:
        appt.patient_id = patient.id
        appt.facility_id = facility.id
        appt.cpt_code = appt_payload.cpt_code.strip().upper()
        appt.scheduled_start_at = scheduled_start
        appt.status = AppointmentStatus.CANCELED.value
        appt.cancelled_at = canceled_at
        if appt_payload.procedure_description:
            appt.procedure_description = appt_payload.procedure_description
    await session.flush()
    return appt


async def _store_inbound_event(
    session: AsyncSession,
    radflow_event_id: str,
    appointment_external_id: str,
    response: RadflowWebhookResponse,
) -> None:
    session.add(
        BackfillInboundEvent(
            radflow_event_id=radflow_event_id,
            appointment_external_id=appointment_external_id,
            campaign_id=response.campaign_id,
            result_status=response.status,
            response_body=response.model_dump(mode="json"),
        )
    )
    await session.flush()


def _map_cancel_message(campaign, message: str) -> tuple[RadflowWebhookStatus, str]:
    lower = message.lower()
    if "agent disabled" in lower:
        return "agent_disabled", message
    if "already exists" in lower:
        return "campaign_exists", message
    if "minimum is" in lower or ("only" in lower and "before exam" in lower):
        return "ineligible", message
    if campaign is not None:
        return "campaign_created", message
    return "ineligible", message


async def handle_radflow_cancellation(
    session: AsyncSession,
    event: RadflowCancellationEvent,
    radflow_event_id: str,
) -> RadflowWebhookResponse:
    """Process RadFlow cancellation; idempotent on radflow_event_id."""
    existing = await get_inbound_event(session, radflow_event_id)
    if existing is not None:
        return response_from_stored(existing)

    appt_external = event.appointment.appointment_id

    if event.event_type != RADFLOW_EVENT_TYPE:
        response = RadflowWebhookResponse(
            status="ignored_event_type",
            event_id=radflow_event_id,
            appointment_external_id=appt_external,
            message=f"Unsupported eventType: {event.event_type}",
        )
        await _store_inbound_event(session, radflow_event_id, appt_external, response)
        return response

    if not _is_canceled_status(event.appointment.status):
        response = RadflowWebhookResponse(
            status="ineligible",
            event_id=radflow_event_id,
            appointment_external_id=appt_external,
            message=f"Appointment status is not canceled: {event.appointment.status}",
        )
        await _store_inbound_event(session, radflow_event_id, appt_external, response)
        return response

    facility = await _upsert_facility(session, event.appointment)
    patient = await _upsert_patient(session, event.patient)
    appt = await _upsert_appointment(session, event, facility, patient)

    if appt.status != AppointmentStatus.CANCELED.value:
        appt.status = AppointmentStatus.CANCELED.value
        appt.cancelled_at = _parse_datetime(event.appointment.canceled_at, event.appointment.timezone)
        await session.flush()

    _, campaign, message = await cancel_appointment_and_maybe_campaign(
        session,
        appt.id,
        cancelled_at=appt.cancelled_at,
    )

    status, msg = _map_cancel_message(campaign, message)

    response = RadflowWebhookResponse(
        status=status,
        event_id=radflow_event_id,
        appointment_external_id=appt_external,
        appointment_id=appt.id,
        campaign_id=campaign.id if campaign else None,
        message=msg,
    )
    await _store_inbound_event(session, radflow_event_id, appt_external, response)
    return response
