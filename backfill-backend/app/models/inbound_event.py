"""Inbound integration events — RadFlow webhook idempotency."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BackfillInboundEvent(Base):
    __tablename__ = "backfill_inbound_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    radflow_event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    appointment_external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("backfill_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    result_status: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_backfill_inbound_events_appointment_external", "appointment_external_id"),
    )
