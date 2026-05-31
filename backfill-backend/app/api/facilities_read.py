"""Read-only facility list for campaign filters (production-safe).

Facilities are populated by RadFlow webhook upserts or the dev simulator.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.appointment_data import Facility
from simulator.schemas import FacilityOut

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=list[FacilityOut])
async def list_facilities(session: AsyncSession = Depends(get_db)) -> list[Facility]:
    result = await session.execute(select(Facility).order_by(Facility.name))
    return list(result.scalars().all())
