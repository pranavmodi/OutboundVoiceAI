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
    # Legacy combined counter — retained so old code paths keep working during
    # rollout. Priority logic now uses ai_attempt_count + human_attempt_count.
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    human_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_by: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    priority_bucket: Mapped[int] = mapped_column(Integer, default=4)
    # RadFlow lifecycle status: Ordered / No Show / Needs to Reschedule / Couldnt Schedule
    radflow_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Set when HL7 "Couldnt Schedule" POST succeeds — prevents duplicate sends
    hl7_sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_patients_status_attempts", "radflow_status", "ai_attempt_count", "human_attempt_count", "due_by"),
        Index("ix_patients_phone", "phone"),
    )


class CallLogRow(Base):
    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False)
    patient_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority_bucket: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(32), default="in_progress")
    call_status: Mapped[str] = mapped_column(String(32), default="in_progress")
    call_disposition: Mapped[str] = mapped_column(String(32), default="in_progress")
    mock_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_provider: Mapped[str] = mapped_column(String(20), default="openai")
    # Audio recording (stored on disk, metadata only in DB)
    recording_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recording_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    recording_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recording_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recording_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    transfer_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_success: Mapped[bool] = mapped_column(Boolean, default=False)
    voicemail_left: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_callback_time: Mapped[str | None] = mapped_column(String(255), nullable=True)
    queue_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_call_logs_patient_id", "patient_id"),
        Index("ix_call_logs_started_at", "started_at"),
        Index("ix_call_logs_outcome", "outcome"),
        Index("ix_call_logs_call_status", "call_status"),
        Index("ix_call_logs_call_disposition", "call_disposition"),
    )


class SystemSettingsRow(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    business_hours: Mapped[dict] = mapped_column(JSONB, nullable=False)
    queue_thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dispatcher_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    allow_live_calls: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_phones: Mapped[list] = mapped_column(JSONB, default=list)
    queue_source: Mapped[str] = mapped_column(String(20), default="simulation")
    patient_source: Mapped[str] = mapped_column(String(20), default="simulation")
    active_scenario_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("simulation_scenarios.id", ondelete="SET NULL"), nullable=True
    )
    call_mode: Mapped[str] = mapped_column(String(20), default="web")
    mock_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    mock_phone: Mapped[str] = mapped_column(String(32), default="")
    voice_provider: Mapped[str] = mapped_column(String(20), default="openai")
    daily_report: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
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


class PatientCallStateRow(Base):
    """Local call state for live-mode patients (RadFlow is read-only)."""
    __tablename__ = "patient_call_state"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Legacy combined counter, kept for rollout compatibility.
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # AI-only attempt count — authoritative going forward.  Human attempts
    # in live mode are derived from the RadFlow VM+CB fields at fetch time.
    ai_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_called_before: Mapped[bool] = mapped_column(Boolean, default=False)
    invalid_number: Mapped[bool] = mapped_column(Boolean, default=False)
    hl7_sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_patient_call_state_updated", "updated_at"),
    )


class AuditEventRow(Base):
    """Log of every external API call the system makes on behalf of a patient."""
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    patient_name: Mapped[str] = mapped_column(String(255), default="")
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)  # radflow | hl7 | sms | email | slack
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # post_outcome | post_hl7_status | send_sms | send_email | send_slack
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success | failed | skipped
    request_summary: Mapped[str] = mapped_column(Text, default="")
    request_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_patient_id", "patient_id"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_call_id", "call_id"),
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
