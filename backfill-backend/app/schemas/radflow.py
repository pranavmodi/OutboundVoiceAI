"""RadFlow appointment cancellation webhook — production contract."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RadflowAppointmentPayload(BaseModel):
    appointment_id: str = Field(alias="appointmentId", min_length=1)
    status: str = Field(min_length=1)
    previous_status: str | None = Field(default=None, alias="previousStatus")
    canceled_at: datetime = Field(alias="canceledAt")
    start_date_time: datetime = Field(alias="startDateTime")
    timezone: str = Field(min_length=1)
    facility_id: str = Field(alias="facilityId", min_length=1)
    facility_name: str | None = Field(default=None, alias="facilityName")
    cpt_code: str = Field(alias="cptCode", min_length=1)
    procedure_description: str | None = Field(default=None, alias="procedureDescription")


class RadflowPatientPayload(BaseModel):
    patient_id: str = Field(alias="patientId", min_length=1)
    patient_name: str | None = Field(default=None, alias="patientName")
    phone: str | None = None


class RadflowMetadataPayload(BaseModel):
    source_system: str | None = Field(default=None, alias="sourceSystem")
    tenant_id: str | None = Field(default=None, alias="tenantId")
    change_reason: str | None = Field(default=None, alias="changeReason")


class RadflowCancellationEvent(BaseModel):
    event_type: str = Field(alias="eventType", min_length=1)
    event_id: str = Field(alias="eventId", min_length=1)
    occurred_at: datetime = Field(alias="occurredAt")
    appointment: RadflowAppointmentPayload
    patient: RadflowPatientPayload
    metadata: RadflowMetadataPayload | None = None

    model_config = {"populate_by_name": True}


RadflowWebhookStatus = Literal[
    "campaign_created",
    "campaign_exists",
    "ineligible",
    "agent_disabled",
    "ignored_event_type",
]


class RadflowWebhookResponse(BaseModel):
    status: RadflowWebhookStatus
    event_id: str
    appointment_external_id: str
    appointment_id: int | None = None
    campaign_id: int | None = None
    message: str
