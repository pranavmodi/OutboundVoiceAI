"""Local appointment projection for dev simulation.

Production will populate these rows via RadFlow API or sync; M1 uses seed data.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AppointmentStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Los_Angeles")

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="facility")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sms_opt_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    no_show_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suppressed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Simulates shared outbound suppression rules",
    )

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="patient")


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    cpt_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=AppointmentStatus.SCHEDULED.value,
        nullable=False,
    )
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    procedure_description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    patient: Mapped["Patient"] = relationship(back_populates="appointments")
    facility: Mapped["Facility"] = relationship(back_populates="appointments")

    __table_args__ = (
        Index("ix_appointments_facility_cpt_status", "facility_id", "cpt_code", "status"),
        Index("ix_appointments_scheduled_start", "scheduled_start_at"),
    )
