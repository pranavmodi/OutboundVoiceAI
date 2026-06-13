"""Backfill campaign domain tables — spec § Data Model."""
from datetime import datetime, time, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ActionChannel, CampaignStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BackfillAgentSettings(Base):
    """Singleton agent configuration (id=1). Editable from Settings tab."""

    __tablename__ = "backfill_agent_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    minimum_cancellation_notice_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    sms_batch_size_per_wave: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    delay_between_waves_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_waves: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    ai_call_escalation_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_call_quantity_per_wave: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    allowed_contact_days: Mapped[str] = mapped_column(
        String(32), default="mon,tue,wed,thu,fri", nullable=False
    )
    contact_window_start: Mapped[time] = mapped_column(Time, default=time(8, 0), nullable=False)
    contact_window_end: Mapped[time] = mapped_column(Time, default=time(18, 0), nullable=False)
    contact_window_timezone: Mapped[str] = mapped_column(
        String(64), default="America/Los_Angeles", nullable=False
    )
    use_shared_holiday_calendar: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    agent_blackout_dates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    same_facility_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    same_cpt_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    exclude_no_show_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    campaign_timeout_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    late_response_closeout_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_sms_template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_voice_template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closeout_message_template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class BackfillCampaign(Base):
    __tablename__ = "backfill_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_type: Mapped[str] = mapped_column(String(64), default="CancellationBackfill", nullable=False)
    cancelled_appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id"), nullable=False
    )
    cancelled_patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    cpt_code: Mapped[str] = mapped_column(String(32), nullable=False)
    open_slot_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancellation_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    min_notice_hours_applied: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign_status: Mapped[str] = mapped_column(
        String(64), default=CampaignStatus.PENDING.value, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_by_patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    filled_by_appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id"), nullable=True
    )
    closed_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_system_flag: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_wave_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_wave_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings_snapshot: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, doc="Agent settings frozen at campaign creation"
    )

    candidates: Mapped[list["BackfillCandidate"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    action_logs: Mapped[list["BackfillActionLog"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("cancelled_appointment_id", name="uq_campaign_cancelled_appointment"),
        Index("ix_backfill_campaigns_status", "campaign_status"),
        Index("ix_backfill_campaigns_started_at", "started_at"),
    )


class BackfillCandidate(Base):
    __tablename__ = "backfill_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    backfill_campaign_id: Mapped[int] = mapped_column(
        ForeignKey("backfill_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    cpt_code: Mapped[str] = mapped_column(String(32), nullable=False)
    scheduled_appointment_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rank_order: Mapped[int] = mapped_column(Integer, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(64), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wave_number_first_contacted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_contact_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interested_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    declined_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    no_response_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    won_slot_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    lost_slot_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped["BackfillCampaign"] = relationship(back_populates="candidates")

    __table_args__ = (
        Index("ix_backfill_candidates_campaign_rank", "backfill_campaign_id", "rank_order"),
        UniqueConstraint(
            "backfill_campaign_id", "appointment_id", name="uq_candidate_campaign_appointment"
        ),
    )


class BackfillActionLog(Base):
    __tablename__ = "backfill_action_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    backfill_campaign_id: Mapped[int] = mapped_column(
        ForeignKey("backfill_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    backfill_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("backfill_candidates.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(32), default=ActionChannel.SYSTEM.value, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transcript_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_response_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    wave_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    campaign: Mapped["BackfillCampaign"] = relationship(back_populates="action_logs")

    __table_args__ = (Index("ix_backfill_action_logs_campaign_at", "backfill_campaign_id", "attempted_at"),)
