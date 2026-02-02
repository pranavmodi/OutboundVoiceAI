"""Settings API endpoints."""
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from app.models import BusinessHours, QueueThresholds, SystemSettings
from app.providers import get_settings_provider
from app.providers.settings_provider import COMMON_TIMEZONES


router = APIRouter(prefix="/api/settings", tags=["settings"])


# Pydantic models for request/response
class BusinessHoursRequest(BaseModel):
    start_time: str
    end_time: str
    enabled: bool
    timezone: str


class QueueThresholdsRequest(BaseModel):
    calls_waiting_threshold: int
    holdtime_threshold_seconds: int
    stable_polls_required: int


class SourceRequest(BaseModel):
    source: str


class SystemSettingsRequest(BaseModel):
    system_enabled: bool
    business_hours: BusinessHoursRequest
    queue_thresholds: QueueThresholdsRequest
    allow_live_calls: bool = False
    allowed_phones: List[str] = []
    queue_source: str = "simulation"
    patient_source: str = "simulation"


class SystemEnabledRequest(BaseModel):
    enabled: bool


class AllowLiveCallsRequest(BaseModel):
    allowed: bool


class AllowedPhonesRequest(BaseModel):
    phones: List[str]


class SystemSettingsResponse(BaseModel):
    system_enabled: bool
    business_hours: BusinessHoursRequest
    queue_thresholds: QueueThresholdsRequest
    allow_live_calls: bool
    allowed_phones: List[str]
    queue_source: str
    patient_source: str
    can_make_calls: bool
    is_within_business_hours: bool


async def settings_to_response(provider) -> SystemSettingsResponse:
    """Convert settings to response model."""
    settings = await provider.get_settings()
    return SystemSettingsResponse(
        system_enabled=settings.system_enabled,
        business_hours=BusinessHoursRequest(
            start_time=settings.business_hours.start_time,
            end_time=settings.business_hours.end_time,
            enabled=settings.business_hours.enabled,
            timezone=settings.business_hours.timezone,
        ),
        queue_thresholds=QueueThresholdsRequest(
            calls_waiting_threshold=settings.queue_thresholds.calls_waiting_threshold,
            holdtime_threshold_seconds=settings.queue_thresholds.holdtime_threshold_seconds,
            stable_polls_required=settings.queue_thresholds.stable_polls_required,
        ),
        allow_live_calls=settings.allow_live_calls,
        allowed_phones=settings.allowed_phones,
        queue_source=settings.queue_source,
        patient_source=settings.patient_source,
        can_make_calls=await provider.can_make_outbound_call(),
        is_within_business_hours=await provider.is_within_business_hours(),
    )


@router.get("", response_model=SystemSettingsResponse)
async def get_settings():
    """Get current system settings."""
    provider = get_settings_provider()
    return await settings_to_response(provider)


@router.put("", response_model=SystemSettingsResponse)
async def update_settings(request: SystemSettingsRequest):
    """Update all system settings."""
    provider = get_settings_provider()

    settings = SystemSettings(
        system_enabled=request.system_enabled,
        business_hours=BusinessHours(
            start_time=request.business_hours.start_time,
            end_time=request.business_hours.end_time,
            enabled=request.business_hours.enabled,
            timezone=request.business_hours.timezone,
        ),
        queue_thresholds=QueueThresholds(
            calls_waiting_threshold=request.queue_thresholds.calls_waiting_threshold,
            holdtime_threshold_seconds=request.queue_thresholds.holdtime_threshold_seconds,
            stable_polls_required=request.queue_thresholds.stable_polls_required,
        ),
        allow_live_calls=request.allow_live_calls,
        allowed_phones=request.allowed_phones,
        queue_source=request.queue_source,
        patient_source=request.patient_source,
    )

    await provider.update_settings(settings)
    return await settings_to_response(provider)


@router.put("/system-enabled", response_model=SystemSettingsResponse)
async def set_system_enabled(request: SystemEnabledRequest):
    """Toggle system on/off."""
    provider = get_settings_provider()
    await provider.set_system_enabled(request.enabled)
    return await settings_to_response(provider)


@router.put("/business-hours", response_model=SystemSettingsResponse)
async def update_business_hours(request: BusinessHoursRequest):
    """Update business hours settings."""
    provider = get_settings_provider()

    business_hours = BusinessHours(
        start_time=request.start_time,
        end_time=request.end_time,
        enabled=request.enabled,
        timezone=request.timezone,
    )

    await provider.update_business_hours(business_hours)
    return await settings_to_response(provider)


@router.put("/queue-thresholds", response_model=SystemSettingsResponse)
async def update_queue_thresholds(request: QueueThresholdsRequest):
    """Update queue thresholds."""
    provider = get_settings_provider()

    thresholds = QueueThresholds(
        calls_waiting_threshold=request.calls_waiting_threshold,
        holdtime_threshold_seconds=request.holdtime_threshold_seconds,
        stable_polls_required=request.stable_polls_required,
    )

    await provider.update_queue_thresholds(thresholds)
    return await settings_to_response(provider)


@router.put("/allow-live-calls", response_model=SystemSettingsResponse)
async def set_allow_live_calls(request: AllowLiveCallsRequest):
    """Toggle live Twilio calls on/off."""
    provider = get_settings_provider()
    await provider.set_allow_live_calls(request.allowed)
    return await settings_to_response(provider)


@router.put("/allowed-phones", response_model=SystemSettingsResponse)
async def update_allowed_phones(request: AllowedPhonesRequest):
    """Update the phone number allowlist for live calls."""
    provider = get_settings_provider()
    await provider.update_allowed_phones(request.phones)
    return await settings_to_response(provider)


@router.put("/queue-source", response_model=SystemSettingsResponse)
async def set_queue_source(request: SourceRequest):
    """Switch queue data source between simulation and live FreePBX."""
    from app.providers import set_queue_source as _set_queue_source

    if request.source not in ("simulation", "live"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="source must be 'simulation' or 'live'")
    provider = get_settings_provider()
    await provider.set_queue_source(request.source)
    _set_queue_source(request.source)
    return await settings_to_response(provider)


@router.put("/patient-source", response_model=SystemSettingsResponse)
async def set_patient_source(request: SourceRequest):
    """Switch patient data source between simulation and live RadFlow."""
    from app.providers import set_patient_source as _set_patient_source

    if request.source not in ("simulation", "live"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="source must be 'simulation' or 'live'")
    provider = get_settings_provider()
    await provider.set_patient_source(request.source)
    _set_patient_source(request.source)
    return await settings_to_response(provider)


@router.get("/timezones", response_model=List[str])
async def get_timezones():
    """Get list of available timezones."""
    return COMMON_TIMEZONES
