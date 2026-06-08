"""In-memory mock SMS thread store (dev only)."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MockSmsMessage:
    id: str
    direction: str
    campaign_id: int
    candidate_id: int | None
    patient_id: int | None
    patient_name: str | None
    from_number: str
    to_number: str
    body: str
    created_at: datetime = field(default_factory=_utcnow)


_lock = Lock()
_messages: list[MockSmsMessage] = []


def record_outbound(
    *,
    campaign_id: int,
    candidate_id: int | None,
    patient_id: int | None,
    patient_name: str | None,
    from_number: str,
    to_number: str,
    body: str,
    provider_message_id: str,
) -> MockSmsMessage:
    msg = MockSmsMessage(
        id=provider_message_id,
        direction="outbound",
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        patient_id=patient_id,
        patient_name=patient_name,
        from_number=from_number,
        to_number=to_number,
        body=body,
    )
    with _lock:
        _messages.append(msg)
    return msg


def record_inbound(
    *,
    campaign_id: int,
    candidate_id: int | None,
    patient_id: int | None,
    patient_name: str | None,
    from_number: str,
    to_number: str,
    body: str,
    provider_message_id: str,
) -> MockSmsMessage:
    msg = MockSmsMessage(
        id=provider_message_id,
        direction="inbound",
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        patient_id=patient_id,
        patient_name=patient_name,
        from_number=from_number,
        to_number=to_number,
        body=body,
    )
    with _lock:
        _messages.append(msg)
    return msg


def list_for_campaign(campaign_id: int) -> list[MockSmsMessage]:
    with _lock:
        return [m for m in _messages if m.campaign_id == campaign_id]


def new_provider_id() -> str:
    return f"SM_sim_{uuid4().hex[:12]}"
