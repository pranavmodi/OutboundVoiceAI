from datetime import datetime

from pydantic import BaseModel


class CampaignOut(BaseModel):
    id: int
    cancelled_appointment_id: int
    cancelled_patient_id: int
    cancelled_patient_name: str | None = None
    facility_id: int
    facility_name: str | None = None
    cpt_code: str
    open_slot_start_at: datetime
    cancellation_at: datetime
    campaign_status: str
    started_at: datetime
    ended_at: datetime | None
    closed_reason: str | None
    filled_by_patient_id: int | None = None
    filled_by_patient_name: str | None = None
    filled_by_appointment_id: int | None = None
    candidate_count: int = 0
    eligible_count: int = 0

    model_config = {"from_attributes": True}


class CampaignListResponse(BaseModel):
    items: list[CampaignOut]
    total: int
    page: int
    page_size: int


class CandidateOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str | None = None
    appointment_id: int
    scheduled_appointment_at: datetime
    rank_order: int
    eligibility_status: str
    exclusion_reason: str | None
    wave_number_first_contacted: int | None = None
    last_contacted_at: datetime | None = None
    current_contact_status: str | None = None
    interested_flag: bool | None = None
    declined_flag: bool | None = None
    no_response_flag: bool | None = None
    won_slot_flag: bool | None = None
    lost_slot_flag: bool | None = None
    response_at: datetime | None = None

    model_config = {"from_attributes": True}


class CampaignDetailOut(CampaignOut):
    candidates: list[CandidateOut] = []


class TimelineEntryOut(BaseModel):
    id: int
    attempted_at: datetime
    action_type: str
    patient_id: int | None = None
    patient_name: str | None = None
    channel: str
    wave_number: int | None = None
    outcome: str | None = None
    provider_message_id: str | None = None

    model_config = {"from_attributes": True}
