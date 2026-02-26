"""Settings API endpoints."""
import logging
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from app.models import BusinessHours, HolidayEntry, QueueThresholds, DispatcherSettings, SystemSettings
from app.providers import get_settings_provider
from app.providers.settings_provider import COMMON_TIMEZONES

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/settings", tags=["settings"])


# Pydantic models for request/response
class HolidayRequest(BaseModel):
    date: str  # YYYY-MM-DD
    name: str
    recurring: bool = True


class BusinessHoursRequest(BaseModel):
    start_time: str
    end_time: str
    enabled: bool
    timezone: str
    days_of_week: List[int] = [0, 1, 2, 3, 4]  # Mon-Fri (0=Mon, 6=Sun)
    holidays: List[HolidayRequest] = []


class QueueThresholdsRequest(BaseModel):
    calls_waiting_threshold: int
    holdtime_threshold_seconds: int
    stable_polls_required: int


class DispatcherSettingsRequest(BaseModel):
    poll_interval: int = 10
    dispatch_timeout: int = 30
    max_attempts: int = 3
    min_hours_between: int = 6


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
    dispatcher_settings: DispatcherSettingsRequest
    allow_live_calls: bool
    allowed_phones: List[str]
    queue_source: str
    patient_source: str
    active_scenario_id: str | None
    call_mode: str
    mock_mode: bool
    mock_phone: str
    can_make_calls: bool
    is_within_business_hours: bool


class ActiveScenarioRequest(BaseModel):
    scenario_id: str


class CallModeRequest(BaseModel):
    call_mode: str  # "web" or "twilio"


class MockModeRequest(BaseModel):
    enabled: bool
    mock_phone: str = ""


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
            days_of_week=settings.business_hours.days_of_week,
            holidays=[
                HolidayRequest(
                    date=h.date,
                    name=h.name,
                    recurring=h.recurring,
                )
                for h in settings.business_hours.holidays
            ],
        ),
        queue_thresholds=QueueThresholdsRequest(
            calls_waiting_threshold=settings.queue_thresholds.calls_waiting_threshold,
            holdtime_threshold_seconds=settings.queue_thresholds.holdtime_threshold_seconds,
            stable_polls_required=settings.queue_thresholds.stable_polls_required,
        ),
        dispatcher_settings=DispatcherSettingsRequest(
            poll_interval=settings.dispatcher_settings.poll_interval,
            dispatch_timeout=settings.dispatcher_settings.dispatch_timeout,
            max_attempts=settings.dispatcher_settings.max_attempts,
            min_hours_between=settings.dispatcher_settings.min_hours_between,
        ),
        allow_live_calls=settings.allow_live_calls,
        allowed_phones=settings.allowed_phones,
        queue_source=settings.queue_source,
        patient_source=settings.patient_source,
        active_scenario_id=settings.active_scenario_id,
        call_mode=settings.call_mode,
        mock_mode=settings.mock_mode,
        mock_phone=settings.mock_phone,
        can_make_calls=await provider.can_make_outbound_call(),
        is_within_business_hours=await provider.is_within_business_hours(),
    )


async def activate_scenario(scenario_id: str) -> None:
    """Load a scenario from DB and apply it to mock providers.

    1. Loads scenario from DB
    2. Calls MockQueueProvider.reset_with_config(queues, ami_connected)
    3. Calls SimulationPatientProvider.reset_with_patients(patients)
    4. Calls call_log_provider.reset()
    5. Calls dispatcher.restart()
    """
    from sqlalchemy import select
    from app.db import AsyncSessionLocal
    from app.db.models import SimulationScenarioRow
    from app.providers import get_mock_queue_provider, get_simulation_patient_provider, get_call_log_provider
    from app.services.dispatcher import get_dispatcher

    print(f"[ACTIVATE_SCENARIO] Activating scenario: {scenario_id}")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SimulationScenarioRow).where(SimulationScenarioRow.id == scenario_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            print(f"[ACTIVATE_SCENARIO] Scenario not found: {scenario_id}")
            raise ValueError(f"Scenario not found: {scenario_id}")

        patient_count = len(row.patients or [])
        queue_count = len(row.queues or [])
        print(f"[ACTIVATE_SCENARIO] Loading scenario '{row.label}': {patient_count} patients, {queue_count} queues")

        for p in (row.patients or []):
            print(f"[ACTIVATE_SCENARIO] - Patient from DB: {p.get('name')}, {p.get('phone')}")

        # 1. Reset queue provider
        queue_provider = get_mock_queue_provider()
        queue_provider.reset_with_config(
            queues_config=row.queues or [],
            ami_connected=row.ami_connected,
        )

        # 2. Reset patient provider
        patient_provider = get_simulation_patient_provider()
        await patient_provider.reset_with_patients(
            patient_dicts=row.patients or []
        )

        # 3. Clear call logs
        call_log_provider = get_call_log_provider()
        await call_log_provider.reset()

        # 4. Restart dispatcher
        get_dispatcher().restart()

        print(f"[ACTIVATE_SCENARIO] Scenario '{row.label}' activated successfully")


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
            days_of_week=request.business_hours.days_of_week,
            holidays=[
                HolidayEntry(
                    date=h.date,
                    name=h.name,
                    recurring=h.recurring,
                )
                for h in request.business_hours.holidays
            ],
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
        days_of_week=request.days_of_week,
        holidays=[
            HolidayEntry(
                date=h.date,
                name=h.name,
                recurring=h.recurring,
            )
            for h in request.holidays
        ],
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


@router.put("/dispatcher", response_model=SystemSettingsResponse)
async def update_dispatcher_settings(request: DispatcherSettingsRequest):
    """Update dispatcher settings and apply immediately."""
    from app.services.dispatcher import get_dispatcher

    provider = get_settings_provider()

    dispatcher_settings = DispatcherSettings(
        poll_interval=request.poll_interval,
        dispatch_timeout=request.dispatch_timeout,
        max_attempts=request.max_attempts,
        min_hours_between=request.min_hours_between,
    )

    await provider.update_dispatcher_settings(dispatcher_settings)

    # Apply to running dispatcher immediately
    get_dispatcher().update_config(
        poll_interval=request.poll_interval,
        dispatch_timeout=request.dispatch_timeout,
        max_attempts=request.max_attempts,
        min_hours_between=request.min_hours_between,
    )

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
    """Switch queue data source between simulation and live FreePBX.

    When switching TO 'simulation', auto-loads the active scenario.
    """
    from app.providers import set_queue_source as _set_queue_source
    from fastapi import HTTPException

    if request.source not in ("simulation", "live"):
        raise HTTPException(status_code=400, detail="source must be 'simulation' or 'live'")

    provider = get_settings_provider()
    current_settings = await provider.get_settings()
    was_simulation = current_settings.queue_source == "simulation"

    await provider.set_queue_source(request.source)
    _set_queue_source(request.source)

    # When switching TO simulation, activate the scenario
    if request.source == "simulation" and not was_simulation:
        active_id = current_settings.active_scenario_id
        if active_id:
            try:
                await activate_scenario(active_id)
            except ValueError:
                pass  # Scenario not found, skip activation

    return await settings_to_response(provider)


@router.put("/patient-source", response_model=SystemSettingsResponse)
async def set_patient_source(request: SourceRequest):
    """Switch patient data source between simulation and live RadFlow.

    When switching TO 'simulation', auto-loads the active scenario.
    """
    from app.providers import set_patient_source as _set_patient_source
    from fastapi import HTTPException

    if request.source not in ("simulation", "live"):
        raise HTTPException(status_code=400, detail="source must be 'simulation' or 'live'")

    provider = get_settings_provider()
    current_settings = await provider.get_settings()
    was_simulation = current_settings.patient_source == "simulation"

    await provider.set_patient_source(request.source)
    _set_patient_source(request.source)

    # When switching TO simulation, activate the scenario
    if request.source == "simulation" and not was_simulation:
        active_id = current_settings.active_scenario_id
        if active_id:
            try:
                await activate_scenario(active_id)
            except ValueError:
                pass  # Scenario not found, skip activation

    return await settings_to_response(provider)


@router.put("/active-scenario", response_model=SystemSettingsResponse)
async def set_active_scenario(request: ActiveScenarioRequest):
    """Set the active simulation scenario and apply it.

    This updates the active_scenario_id in settings and immediately
    activates the scenario (resets mock providers, clears call logs,
    restarts dispatcher).
    """
    from fastapi import HTTPException

    provider = get_settings_provider()

    # Update the active scenario ID in settings
    await provider.set_active_scenario_id(request.scenario_id)

    # Activate the scenario (load into mock providers)
    try:
        await activate_scenario(request.scenario_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return await settings_to_response(provider)


@router.put("/call-mode", response_model=SystemSettingsResponse)
async def set_call_mode(request: CallModeRequest):
    """Set the call mode (web or twilio)."""
    from fastapi import HTTPException

    if request.call_mode not in ("web", "twilio"):
        raise HTTPException(status_code=400, detail="call_mode must be 'web' or 'twilio'")

    provider = get_settings_provider()
    await provider.set_call_mode(request.call_mode)
    return await settings_to_response(provider)


@router.put("/mock-mode", response_model=SystemSettingsResponse)
async def set_mock_mode(request: MockModeRequest):
    """Toggle mock mode and set the redirect phone number for Twilio calls/SMS."""
    provider = get_settings_provider()
    await provider.set_mock_mode(request.enabled, request.mock_phone)
    return await settings_to_response(provider)


@router.get("/timezones", response_model=List[str])
async def get_timezones():
    """Get list of available timezones."""
    return COMMON_TIMEZONES
