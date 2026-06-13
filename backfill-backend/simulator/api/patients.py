from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.appointment_data import Patient
from simulator.schemas import PatientCreate, PatientOut

router = APIRouter(prefix="/patients", tags=["simulator-patients"])


@router.get("", response_model=list[PatientOut])
async def list_patients(session: AsyncSession = Depends(get_db)) -> list[Patient]:
    result = await session.execute(select(Patient).order_by(Patient.name))
    return list(result.scalars().all())


@router.post("", response_model=PatientOut, status_code=201)
async def create_patient(
    body: PatientCreate,
    session: AsyncSession = Depends(get_db),
) -> Patient:
    row = Patient(
        name=body.name,
        phone=body.phone,
        sms_opt_out=body.sms_opt_out,
        no_show_flag=body.no_show_flag,
        suppressed=body.suppressed,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row
