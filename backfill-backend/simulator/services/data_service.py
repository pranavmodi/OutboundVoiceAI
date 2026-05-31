"""Dev simulator — delete appointments/patients and clear bootstrap demo seed."""
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_data import Appointment, Facility, Patient
from app.models.backfill import BackfillCampaign, BackfillCandidate
from simulator.fixtures.demo_seed import DEMO_FACILITY_NAME, DEMO_PATIENT_NAMES


async def delete_appointment(session: AsyncSession, appointment_id: int) -> None:
    appt = await session.get(Appointment, appointment_id)
    if appt is None:
        raise ValueError(f"Appointment {appointment_id} not found")

    campaign_ids = (
        await session.scalars(
            select(BackfillCampaign.id).where(
                BackfillCampaign.cancelled_appointment_id == appointment_id
            )
        )
    ).all()
    for cid in campaign_ids:
        campaign = await session.get(BackfillCampaign, cid)
        if campaign is not None:
            await session.delete(campaign)

    await session.execute(
        update(BackfillCampaign)
        .where(BackfillCampaign.filled_by_appointment_id == appointment_id)
        .values(filled_by_appointment_id=None)
    )
    await session.execute(
        delete(BackfillCandidate).where(BackfillCandidate.appointment_id == appointment_id)
    )
    await session.delete(appt)
    await session.flush()


async def clear_demo_data(session: AsyncSession) -> dict:
    """Remove bootstrap demo patients/appointments; keep manually created rows."""
    demo_patients = (
        await session.scalars(select(Patient).where(Patient.name.in_(DEMO_PATIENT_NAMES)))
    ).all()
    if not demo_patients:
        return {"message": "No demo patients found.", "deleted_appointments": 0, "deleted_patients": 0}

    demo_patient_ids = [p.id for p in demo_patients]
    demo_appointments = (
        await session.scalars(
            select(Appointment).where(Appointment.patient_id.in_(demo_patient_ids))
        )
    ).all()

    deleted_appts = 0
    for appt in demo_appointments:
        await delete_appointment(session, appt.id)
        deleted_appts += 1

    for patient in demo_patients:
        await session.delete(patient)

    demo_facility = await session.scalar(
        select(Facility).where(Facility.name == DEMO_FACILITY_NAME)
    )
    if demo_facility is not None:
        appt_at_facility = await session.scalar(
            select(Appointment.id)
            .where(Appointment.facility_id == demo_facility.id)
            .limit(1)
        )
        if appt_at_facility is None:
            await session.delete(demo_facility)

    await session.flush()
    return {
        "message": f"Removed demo data ({deleted_appts} appointments, {len(demo_patients)} patients).",
        "deleted_appointments": deleted_appts,
        "deleted_patients": len(demo_patients),
    }
