from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.agent import AgentStatusOut
from app.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status", response_model=AgentStatusOut)
async def get_agent_status(session: AsyncSession = Depends(get_db)) -> AgentStatusOut:
    settings = await get_or_create_settings(session)
    return AgentStatusOut(
        enabled=settings.enabled,
        status="ok",
        service="backfill-backend",
    )
