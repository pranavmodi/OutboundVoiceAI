"""Twilio SMS inbound/status webhooks."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.deps import get_db
from app.services.inbound_sms_service import handle_inbound_sms

router = APIRouter(prefix="/webhooks/sms", tags=["webhooks-sms"])


def _validate_twilio_signature(request: Request, form_data: dict[str, str], signature: str | None) -> None:
    if not settings.twilio_webhook_auth_enabled:
        return
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=503, detail="Twilio auth token not configured")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Twilio-Signature")
    if not settings.backfill_public_base_url:
        raise HTTPException(status_code=503, detail="BACKFILL_PUBLIC_BASE_URL is required")
    from twilio.request_validator import RequestValidator

    validator = RequestValidator(settings.twilio_auth_token)
    url = f"{settings.backfill_public_base_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    valid = validator.validate(url, form_data, signature)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")


@router.post("/inbound")
async def inbound_sms(
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_twilio_signature: str | None = Header(None, alias="X-Twilio-Signature"),
):
    form = await request.form()
    data = {k: str(v) for k, v in form.multi_items()}
    _validate_twilio_signature(request, data, x_twilio_signature)
    result = await handle_inbound_sms(
        session,
        from_number=data.get("From", ""),
        body=data.get("Body"),
        message_sid=data.get("MessageSid"),
        payload=data,
    )
    return JSONResponse(
        {
            "status": result.status,
            "campaign_id": result.campaign_id,
            "candidate_id": result.candidate_id,
            "message": result.message,
        }
    )


@router.post("/status")
async def sms_status_callback(
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_twilio_signature: str | None = Header(None, alias="X-Twilio-Signature"),
):
    form = await request.form()
    data = {k: str(v) for k, v in form.multi_items()}
    _validate_twilio_signature(request, data, x_twilio_signature)
    _ = session
    return JSONResponse({"status": "accepted", "message_sid": data.get("MessageSid")})
