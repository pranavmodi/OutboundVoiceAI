"""Central audit writer — milestone 3.7."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backfill import BackfillActionLog
from app.models.enums import ActionChannel


async def log_action(
    session: AsyncSession,
    *,
    campaign_id: int,
    action_type: str,
    outcome: str | None = None,
    candidate_id: int | None = None,
    payload: dict | None = None,
    channel: str = ActionChannel.SYSTEM.value,
    wave_number: int | None = None,
    provider_message_id: str | None = None,
) -> None:
    session.add(
        BackfillActionLog(
            backfill_campaign_id=campaign_id,
            backfill_candidate_id=candidate_id,
            channel=channel,
            action_type=action_type,
            outcome=outcome,
            provider_message_id=provider_message_id,
            raw_response_payload=payload,
            wave_number=wave_number,
        )
    )
