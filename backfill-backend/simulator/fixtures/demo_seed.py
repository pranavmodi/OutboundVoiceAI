"""Bootstrap demo dataset — Alice/Bob/Carol/Dave scenario for local QA."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_data import Appointment, Facility, Patient
from app.models.enums import AppointmentStatus

DEMO_FACILITY_NAME = "Precise Imaging — Demo"
DEMO_PATIENT_NAMES = frozenset(
    {"Alice Canceled", "Bob Far Out", "Carol Mid", "Dave No-Show"}
)
DEMO_CPT = "MRI_BRAIN"


async def create_demo_dataset(session: AsyncSession) -> dict:
    facility = Facility(name=DEMO_FACILITY_NAME, timezone="America/Los_Angeles")
    session.add(facility)
    await session.flush()

    patients = [
        Patient(name="Alice Canceled", phone="+15551000001"),
        Patient(name="Bob Far Out", phone="+15551000002"),
        Patient(name="Carol Mid", phone="+15551000003"),
        Patient(name="Dave No-Show", phone="+15551000004", no_show_flag=True),
    ]
    session.add_all(patients)
    await session.flush()

    now = datetime.now(timezone.utc)
    canceled_slot = now + timedelta(days=5)
    bob_slot = now + timedelta(days=30)
    carol_slot = now + timedelta(days=14)

    appointments = [
        Appointment(
            patient_id=patients[0].id,
            facility_id=facility.id,
            cpt_code=DEMO_CPT,
            scheduled_start_at=canceled_slot,
            status=AppointmentStatus.SCHEDULED.value,
        ),
        Appointment(
            patient_id=patients[1].id,
            facility_id=facility.id,
            cpt_code=DEMO_CPT,
            scheduled_start_at=bob_slot,
            status=AppointmentStatus.SCHEDULED.value,
        ),
        Appointment(
            patient_id=patients[2].id,
            facility_id=facility.id,
            cpt_code=DEMO_CPT,
            scheduled_start_at=carol_slot,
            status=AppointmentStatus.SCHEDULED.value,
        ),
        Appointment(
            patient_id=patients[3].id,
            facility_id=facility.id,
            cpt_code=DEMO_CPT,
            scheduled_start_at=now + timedelta(days=20),
            status=AppointmentStatus.SCHEDULED.value,
        ),
    ]
    session.add_all(appointments)
    await session.flush()

    return {
        "message": "Demo data created. Cancel Alice's appointment (first in list) to start a campaign.",
        "created": True,
        "facility_id": facility.id,
        "appointment_to_cancel_id": appointments[0].id,
    }
