"""Load or clear the local demo dataset."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.appointment_data import Facility
from app.services.settings_service import get_or_create_settings
from simulator.fixtures.demo_seed import create_demo_dataset
from simulator.services.data_service import clear_demo_data

router = APIRouter(prefix="/bootstrap", tags=["simulator-bootstrap"])


@router.post("/demo")
async def load_demo_data(session: AsyncSession = Depends(get_db)) -> dict:
    await get_or_create_settings(session)

    existing = await session.scalar(select(func.count()).select_from(Facility))
    if existing and existing > 0:
        return {"message": "Data already exists; bootstrap skipped.", "created": False}

    return await create_demo_dataset(session)


@router.post("/clear-demo")
async def remove_demo_data(session: AsyncSession = Depends(get_db)) -> dict:
    return await clear_demo_data(session)
