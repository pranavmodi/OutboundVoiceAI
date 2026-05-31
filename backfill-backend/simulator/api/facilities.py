from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.appointment_data import Facility
from simulator.schemas import FacilityCreate, FacilityOut

router = APIRouter(prefix="/facilities", tags=["simulator-facilities"])


@router.get("", response_model=list[FacilityOut])
async def list_facilities(session: AsyncSession = Depends(get_db)) -> list[Facility]:
    result = await session.execute(select(Facility).order_by(Facility.name))
    return list(result.scalars().all())


@router.post("", response_model=FacilityOut, status_code=201)
async def create_facility(
    body: FacilityCreate,
    session: AsyncSession = Depends(get_db),
) -> Facility:
    row = Facility(name=body.name, timezone=body.timezone)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row
