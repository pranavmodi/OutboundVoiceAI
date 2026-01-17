"""Settings API endpoints."""
from dataclasses import asdict
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
    oldest_wait_threshold_seconds: int
    stable_polls_required: int


class SystemSettingsRequest(BaseModel):
    system_enabled: bool
    business_hours: BusinessHoursRequest
    queue_thresholds: QueueThresholdsRequest


class SystemEnabledRequest(BaseModel):
    enabled: bool


class SystemSettingsResponse(BaseModel):
    system_enabled: bool
    business_hours: BusinessHoursRequest
    queue_thresholds: QueueThresholdsRequest
    can_make_calls: bool
    is_within_business_hours: bool


def settings_to_response(provider) -> SystemSettingsResponse:
    """Convert settings to response model."""
    settings = provider.get_settings()
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
            oldest_wait_threshold_seconds=settings.queue_thresholds.oldest_wait_threshold_seconds,
            stable_polls_required=settings.queue_thresholds.stable_polls_required,
        ),
        can_make_calls=provider.can_make_outbound_call(),
        is_within_business_hours=provider.is_within_business_hours(),
    )


@router.get("", response_model=SystemSettingsResponse)
def get_settings():
    """Get current system settings."""
    provider = get_settings_provider()
    return settings_to_response(provider)


@router.put("", response_model=SystemSettingsResponse)
def update_settings(request: SystemSettingsRequest):
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
            oldest_wait_threshold_seconds=request.queue_thresholds.oldest_wait_threshold_seconds,
            stable_polls_required=request.queue_thresholds.stable_polls_required,
        ),
    )

    provider.update_settings(settings)
    return settings_to_response(provider)


@router.put("/system-enabled", response_model=SystemSettingsResponse)
def set_system_enabled(request: SystemEnabledRequest):
    """Toggle system on/off."""
    provider = get_settings_provider()
    provider.set_system_enabled(request.enabled)
    return settings_to_response(provider)


@router.put("/business-hours", response_model=SystemSettingsResponse)
def update_business_hours(request: BusinessHoursRequest):
    """Update business hours settings."""
    provider = get_settings_provider()

    business_hours = BusinessHours(
        start_time=request.start_time,
        end_time=request.end_time,
        enabled=request.enabled,
        timezone=request.timezone,
    )

    provider.update_business_hours(business_hours)
    return settings_to_response(provider)


@router.put("/queue-thresholds", response_model=SystemSettingsResponse)
def update_queue_thresholds(request: QueueThresholdsRequest):
    """Update queue thresholds."""
    provider = get_settings_provider()

    thresholds = QueueThresholds(
        calls_waiting_threshold=request.calls_waiting_threshold,
        oldest_wait_threshold_seconds=request.oldest_wait_threshold_seconds,
        stable_polls_required=request.stable_polls_required,
    )

    provider.update_queue_thresholds(thresholds)
    return settings_to_response(provider)


@router.get("/timezones", response_model=List[str])
def get_timezones():
    """Get list of available timezones."""
    return COMMON_TIMEZONES
