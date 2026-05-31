import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.deps import get_db
from app.schemas.radflow import RadflowCancellationEvent, RadflowWebhookResponse
from app.services.radflow_webhook_service import handle_radflow_cancellation

router = APIRouter(tags=["integrations-radflow"])


def verify_radflow_webhook(
    authorization: str | None = Header(None),
    x_radflow_event_id: str | None = Header(None, alias="X-RadFlow-Event-Id"),
) -> str:
    if not settings.radflow_webhook_enabled:
        raise HTTPException(status_code=503, detail="RadFlow webhook is disabled")
    if not settings.radflow_webhook_token:
        raise HTTPException(status_code=503, detail="RadFlow webhook token is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, settings.radflow_webhook_token):
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    if not x_radflow_event_id or not x_radflow_event_id.strip():
        raise HTTPException(status_code=400, detail="X-RadFlow-Event-Id header is required")
    return x_radflow_event_id.strip()


@router.post(
    "/appointment-cancellations",
    response_model=RadflowWebhookResponse,
    summary="RadFlow appointment cancellation webhook",
)
async def radflow_appointment_cancellation(
    body: RadflowCancellationEvent,
    session: AsyncSession = Depends(get_db),
    radflow_event_id: str = Depends(verify_radflow_webhook),
) -> RadflowWebhookResponse:
    return await handle_radflow_cancellation(session, body, radflow_event_id)
