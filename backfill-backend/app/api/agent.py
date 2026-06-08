from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.deps import get_db
from app.schemas.agent import AgentStatusOut
from app.services.settings_service import get_or_create_settings
from app.services.sms_runtime import get_effective_sms_provider, is_mock_sms_mode

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status", response_model=AgentStatusOut)
async def get_agent_status(session: AsyncSession = Depends(get_db)) -> AgentStatusOut:
    agent_settings = await get_or_create_settings(session)
    sms_provider = get_effective_sms_provider()
    return AgentStatusOut(
        enabled=agent_settings.enabled,
        status="ok",
        service="backfill-backend",
        sms_provider=sms_provider,
        sms_mode=sms_provider,
        mock_sms_enabled=is_mock_sms_mode(),
    )
