"""SQLAlchemy ORM table models."""
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Boolean, Text, Index, CheckConstraint,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PatientRow(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="en")
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_created: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    intake_status: Mapped[str] = mapped_column(String(20), default="complete")
    has_called_in_before: Mapped[bool] = mapped_column(Boolean, default=False)
    has_abandoned_before: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_called_before: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_by: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    priority_bucket: Mapped[int] = mapped_column(Integer, default=4)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_patients_priority_due", "priority_bucket", "due_by"),
        Index("ix_patients_phone", "phone"),
    )


class CallLogRow(Base):
    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), ForeignKey("patients.patient_id"), nullable=False)
    patient_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority_bucket: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(32), default="in_progress")
    transfer_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_success: Mapped[bool] = mapped_column(Boolean, default=False)
    voicemail_left: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    queue_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_call_logs_patient_id", "patient_id"),
        Index("ix_call_logs_started_at", "started_at"),
        Index("ix_call_logs_outcome", "outcome"),
    )


class SystemSettingsRow(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    business_hours: Mapped[dict] = mapped_column(JSONB, nullable=False)
    queue_thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False)
    allow_live_calls: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_phones: Mapped[list] = mapped_column(JSONB, default=list)
    queue_source: Mapped[str] = mapped_column(String(20), default="simulation")
    patient_source: Mapped[str] = mapped_column(String(20), default="simulation")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_settings"),
    )


class DispatcherEventRow(Base):
    __tablename__ = "dispatcher_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        Index("ix_dispatcher_events_timestamp", "timestamp"),
        Index("ix_dispatcher_events_decision", "decision"),
    )


class QueueStateSnapshotRow(Base):
    __tablename__ = "queue_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)
    global_calls_waiting: Mapped[int] = mapped_column(Integer, default=0)
    global_max_holdtime: Mapped[int] = mapped_column(Integer, default=0)
    global_agents_available: Mapped[int] = mapped_column(Integer, default=0)
    outbound_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    stable_polls_count: Mapped[int] = mapped_column(Integer, default=0)
    ami_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    queues: Mapped[list] = mapped_column(JSONB, default=list)

    __table_args__ = (
        Index("ix_queue_state_snapshots_timestamp", "timestamp"),
    )


class SimulationScenarioRow(Base):
    __tablename__ = "simulation_scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    ami_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    queues: Mapped[list] = mapped_column(JSONB, default=list)
    patients: Mapped[list] = mapped_column(JSONB, default=list)
    dispatcher: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)
