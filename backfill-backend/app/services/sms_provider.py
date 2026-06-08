"""SMS provider abstraction for backfill wave execution."""
from functools import lru_cache
from typing import Any
from uuid import uuid4

from app.config import settings
from app.services.sms_runtime import get_effective_sms_provider


@lru_cache(maxsize=1)
def _twilio_client() -> Any:
    from twilio.rest import Client

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("Twilio is not configured")
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_offer_sms(
    *,
    to_number: str,
    message_body: str,
    campaign_id: int | None = None,
    candidate_id: int | None = None,
    patient_id: int | None = None,
    patient_name: str | None = None,
) -> str:
    """Dispatch backfill offer SMS and return provider message id."""
    if get_effective_sms_provider() == "twilio":
        if not settings.twilio_sms_from_number:
            raise RuntimeError("TWILIO_SMS_FROM_NUMBER is not configured")
        message = _twilio_client().messages.create(
            to=to_number,
            from_=settings.twilio_sms_from_number,
            body=message_body,
        )
        return message.sid

    from mock_sms.store import new_provider_id, record_outbound

    provider_message_id = new_provider_id()
    if campaign_id is not None:
        record_outbound(
            campaign_id=campaign_id,
            candidate_id=candidate_id,
            patient_id=patient_id,
            patient_name=patient_name,
            from_number=settings.twilio_sms_from_number or "MOCK-SENDER",
            to_number=to_number,
            body=message_body,
            provider_message_id=provider_message_id,
        )
    return provider_message_id
