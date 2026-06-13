from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.services.settings_service import get_or_create_settings, settings_to_out, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings(session: AsyncSession = Depends(get_db)) -> SettingsOut:
    row = await get_or_create_settings(session)
    return settings_to_out(row)


@router.put("", response_model=SettingsOut)
async def put_settings(
    body: SettingsUpdate,
    session: AsyncSession = Depends(get_db),
) -> SettingsOut:
    row = await get_or_create_settings(session)
    updated = await update_settings(session, row, body)
    return settings_to_out(updated)
