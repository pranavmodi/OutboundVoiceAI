from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_db
from app.models.appointment_data import Appointment, Facility, Patient
from app.models.enums import AppointmentStatus
from app.services.campaign_service import cancel_appointment_and_maybe_campaign
from simulator.schemas import (
    AppointmentCancelRequest,
    AppointmentCreate,
    AppointmentOut,
    CancelAppointmentResult,
)
from simulator.services.data_service import delete_appointment

router = APIRouter(prefix="/appointments", tags=["simulator-appointments"])


def _to_out(appt: Appointment) -> AppointmentOut:
    patient_name = appt.patient.name if appt.patient else None
    facility_name = appt.facility.name if appt.facility else None
    return AppointmentOut(
        id=appt.id,
        patient_id=appt.patient_id,
        patient_name=patient_name,
        facility_id=appt.facility_id,
        facility_name=facility_name,
        cpt_code=appt.cpt_code,
        status=appt.status,
        scheduled_start_at=appt.scheduled_start_at,
        cancelled_at=appt.cancelled_at,
    )


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(session: AsyncSession = Depends(get_db)) -> list[AppointmentOut]:
    result = await session.execute(
        select(Appointment)
        .options(selectinload(Appointment.patient), selectinload(Appointment.facility))
        .order_by(Appointment.scheduled_start_at.desc())
    )
    return [_to_out(a) for a in result.scalars().all()]


@router.post("", response_model=AppointmentOut, status_code=201)
async def create_appointment(
    body: AppointmentCreate,
    session: AsyncSession = Depends(get_db),
) -> AppointmentOut:
    patient = await session.get(Patient, body.patient_id)
    facility = await session.get(Facility, body.facility_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")

    appt = Appointment(
        patient_id=body.patient_id,
        facility_id=body.facility_id,
        cpt_code=body.cpt_code.strip().upper(),
        scheduled_start_at=body.scheduled_start_at,
        status=AppointmentStatus.SCHEDULED.value,
    )
    session.add(appt)
    await session.flush()
    await session.refresh(appt, attribute_names=["patient", "facility"])
    return _to_out(appt)


@router.post("/{appointment_id}/cancel", response_model=CancelAppointmentResult)
async def cancel_appointment(
    appointment_id: int,
    body: AppointmentCancelRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> CancelAppointmentResult:
    """Dev-only cancel trigger — same campaign rules as the RadFlow webhook."""
    try:
        appt, campaign, message = await cancel_appointment_and_maybe_campaign(
            session,
            appointment_id,
            body.cancelled_at if body else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return CancelAppointmentResult(
        appointment_id=appt.id,
        cancelled=appt.status == AppointmentStatus.CANCELED.value,
        campaign_created=campaign is not None,
        campaign_id=campaign.id if campaign else None,
        message=message,
    )


@router.delete("/{appointment_id}", status_code=204)
async def remove_appointment(
    appointment_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    try:
        await delete_appointment(session, appointment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
