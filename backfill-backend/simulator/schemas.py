"""Pydantic schemas for the dev simulator API."""
from datetime import datetime

from pydantic import BaseModel, Field


class FacilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    timezone: str = "America/Los_Angeles"


class FacilityOut(BaseModel):
    id: int
    name: str
    timezone: str

    model_config = {"from_attributes": True}


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = None
    sms_opt_out: bool = False
    no_show_flag: bool = False
    suppressed: bool = False


class PatientOut(BaseModel):
    id: int
    name: str
    phone: str | None
    sms_opt_out: bool
    no_show_flag: bool
    suppressed: bool

    model_config = {"from_attributes": True}


class AppointmentCreate(BaseModel):
    patient_id: int
    facility_id: int
    cpt_code: str = Field(min_length=1, max_length=32)
    scheduled_start_at: datetime


class AppointmentOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str | None = None
    facility_id: int
    facility_name: str | None = None
    cpt_code: str
    status: str
    scheduled_start_at: datetime
    cancelled_at: datetime | None

    model_config = {"from_attributes": True}


class AppointmentCancelRequest(BaseModel):
    cancelled_at: datetime | None = None


class CancelAppointmentResult(BaseModel):
    appointment_id: int
    cancelled: bool
    campaign_created: bool
    campaign_id: int | None = None
    message: str
