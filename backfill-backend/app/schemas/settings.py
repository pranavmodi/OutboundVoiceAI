from datetime import datetime, time

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SmsProviderMode = Literal["mock", "twilio"]


class SettingsOut(BaseModel):
    id: int
    enabled: bool
    minimum_cancellation_notice_hours: int
    sms_batch_size_per_wave: int
    delay_between_waves_minutes: int
    max_waves: int
    ai_call_escalation_enabled: bool
    ai_call_quantity_per_wave: int
    allowed_contact_days: str
    contact_window_start: time
    contact_window_end: time
    contact_window_timezone: str
    use_shared_holiday_calendar: bool
    agent_blackout_dates: list[str] | None
    same_facility_required: bool
    same_cpt_required: bool
    exclude_no_show_enabled: bool
    campaign_timeout_minutes: int | None
    late_response_closeout_enabled: bool
    allowed_sms_template_id: int | None
    allowed_voice_template_id: int | None
    closeout_message_template_id: int | None
    sms_provider: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    enabled: bool
    minimum_cancellation_notice_hours: int = Field(ge=1)
    sms_batch_size_per_wave: int = Field(ge=1)
    delay_between_waves_minutes: int = Field(ge=0)
    max_waves: int = Field(ge=1)
    ai_call_escalation_enabled: bool
    ai_call_quantity_per_wave: int = Field(ge=1)
    allowed_contact_days: str
    contact_window_start: time
    contact_window_end: time
    contact_window_timezone: str
    use_shared_holiday_calendar: bool
    agent_blackout_dates: list[str] | None = None
    same_facility_required: bool
    same_cpt_required: bool
    exclude_no_show_enabled: bool
    campaign_timeout_minutes: int | None = None
    late_response_closeout_enabled: bool
    allowed_sms_template_id: int | None = None
    allowed_voice_template_id: int | None = None
    closeout_message_template_id: int | None = None
    sms_provider: SmsProviderMode

    @field_validator("campaign_timeout_minutes")
    @classmethod
    def validate_campaign_timeout(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("campaign_timeout_minutes must be at least 1 when set")
        return value

    @model_validator(mode="after")
    def validate_contact_window(self) -> "SettingsUpdate":
        if self.contact_window_end == self.contact_window_start:
            raise ValueError("contact_window_end must differ from contact_window_start")
        return self
