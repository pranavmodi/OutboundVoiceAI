"""Settings API endpoints."""
import asyncio
import logging
import os
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from app.models import BusinessHours, HolidayEntry, QueueThresholds, DispatcherSettings, IntakeV2Settings, SystemSettings
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
    max_attempts_ordered: int = 4
    max_attempts_other: int = 4
    min_hours_between: int = 6
    verbose_logging: bool = False
    openai_voice: str = "alloy"
    gemini_voice: str = "Aoede"
    grok_voice: str = "eve"
    call_greeting: str = ""
    max_parallel_calls: int = 1
    dispatch_pacing_seconds: int = 1


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


class DailyReportRequest(BaseModel):
    enabled: bool = False
    webhook_url: str = ""
    hour: int = 7
    timezone: str = "America/Los_Angeles"


class IntakeV2Request(BaseModel):
    master_enabled: bool = False
    tenant_allowlist: List[str] = []
    order_canary_pct: int = 0
    mode_voice_capture: bool = False
    mode_portal_copilot: bool = False
    multi_call_resume: bool = False
    consent_disclosure: str = ""


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
    voice_provider: str
    daily_report: DailyReportRequest
    intake_v2: IntakeV2Request
    can_make_calls: bool
    is_within_business_hours: bool


class ActiveScenarioRequest(BaseModel):
    scenario_id: str


class CallModeRequest(BaseModel):
    call_mode: str  # "web" or "twilio"


class VoiceProviderRequest(BaseModel):
    voice_provider: str  # "openai" | "gemini" | "grok"


class MockModeRequest(BaseModel):
    enabled: bool
    mock_phone: str = ""


async def _broadcast_settings_change(response: "SystemSettingsResponse"):
    """Push a settings_updated event to all connected dashboard clients.

    This keeps other browser windows in sync when one window changes a setting.
    """
    try:
        from app.api.websocket import broadcast_to_dashboards
        await broadcast_to_dashboards({
            "type": "settings_updated",
            "settings": response.model_dump(),
        })
    except Exception:
        pass  # Don't fail the request if broadcast fails


async def settings_response_and_broadcast(provider) -> SystemSettingsResponse:
    """Build the settings response AND broadcast the change to all WebSocket clients."""
    resp = await settings_to_response(provider)
    await _broadcast_settings_change(resp)
    return resp


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
            max_attempts_ordered=settings.dispatcher_settings.max_attempts_ordered,
            max_attempts_other=settings.dispatcher_settings.max_attempts_other,
            min_hours_between=settings.dispatcher_settings.min_hours_between,
            verbose_logging=settings.dispatcher_settings.verbose_logging,
            openai_voice=settings.dispatcher_settings.openai_voice,
            gemini_voice=settings.dispatcher_settings.gemini_voice,
            grok_voice=settings.dispatcher_settings.grok_voice,
            call_greeting=settings.dispatcher_settings.call_greeting,
            max_parallel_calls=settings.dispatcher_settings.max_parallel_calls,
            dispatch_pacing_seconds=settings.dispatcher_settings.dispatch_pacing_seconds,
        ),
        allow_live_calls=settings.allow_live_calls,
        allowed_phones=settings.allowed_phones,
        queue_source=settings.queue_source,
        patient_source=settings.patient_source,
        active_scenario_id=settings.active_scenario_id,
        call_mode=settings.call_mode,
        mock_mode=settings.mock_mode,
        mock_phone=settings.mock_phone,
        voice_provider=settings.voice_provider,
        daily_report=DailyReportRequest(
            enabled=settings.daily_report.enabled,
            webhook_url=settings.daily_report.webhook_url,
            hour=settings.daily_report.hour,
            timezone=settings.daily_report.timezone,
        ),
        intake_v2=IntakeV2Request(
            master_enabled=settings.intake_v2.master_enabled,
            tenant_allowlist=list(settings.intake_v2.tenant_allowlist),
            order_canary_pct=settings.intake_v2.order_canary_pct,
            mode_voice_capture=settings.intake_v2.mode_voice_capture,
            mode_portal_copilot=settings.intake_v2.mode_portal_copilot,
            multi_call_resume=settings.intake_v2.multi_call_resume,
            consent_disclosure=settings.intake_v2.consent_disclosure,
        ),
        can_make_calls=await provider.can_make_outbound_call(),
        is_within_business_hours=await provider.is_within_business_hours(),
    )


async def activate_scenario(scenario_id: str) -> None:
    """Load scenario data into mock providers and restart the dispatcher.

    Only prepares the mock data — does NOT change which source (live vs
    simulation) is active.  The caller or the individual source-switch
    endpoints are responsible for setting the in-memory source.

    Note: call logs are NOT cleared — they are historical records that
    should persist across scenario switches and server restarts.
    Use DELETE /api/calls to clear them explicitly.
    """
    from sqlalchemy import select
    from app.db import AsyncSessionLocal
    from app.db.models import SimulationScenarioRow
    from app.providers import get_mock_queue_provider, get_simulation_patient_provider
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

        # 1. Reset mock queue provider with scenario data
        queue_provider = get_mock_queue_provider()
        queue_provider.reset_with_config(
            queues_config=row.queues or [],
            ami_connected=row.ami_connected,
        )

        # 2. Reset simulation patient provider with scenario data
        patient_provider = get_simulation_patient_provider()
        await patient_provider.reset_with_patients(
            patient_dicts=row.patients or []
        )

        # 3. Restart dispatcher
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
    return await settings_response_and_broadcast(provider)


@router.put("/system-enabled", response_model=SystemSettingsResponse)
async def set_system_enabled(request: SystemEnabledRequest):
    """Toggle system on/off."""
    from app.services.dispatcher import get_dispatcher
    from app.api.websocket import broadcast_to_dashboards

    provider = get_settings_provider()
    await provider.set_system_enabled(request.enabled)
    print(f"[SETTINGS] system_enabled → {request.enabled}")

    # Log to dispatcher events so the dashboard shows the state change in real time
    dispatcher = get_dispatcher()
    if request.enabled:
        decision_entry = dispatcher._log_decision("system_enabled", "System enabled — outbound calls will resume")
    else:
        decision_entry = dispatcher._log_decision("system_disabled", "System disabled — no new outbound calls will be placed")

    # Broadcast immediately so the UI event card updates without waiting for next tick
    await broadcast_to_dashboards({"type": "dispatcher_event", "decision": decision_entry})

    return await settings_response_and_broadcast(provider)


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
    return await settings_response_and_broadcast(provider)


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
    return await settings_response_and_broadcast(provider)


@router.put("/dispatcher", response_model=SystemSettingsResponse)
async def update_dispatcher_settings(request: DispatcherSettingsRequest):
    """Update dispatcher settings and apply immediately."""
    from app.services.dispatcher import get_dispatcher

    provider = get_settings_provider()

    dispatcher_settings = DispatcherSettings(
        poll_interval=request.poll_interval,
        dispatch_timeout=request.dispatch_timeout,
        max_attempts_ordered=request.max_attempts_ordered,
        max_attempts_other=request.max_attempts_other,
        min_hours_between=request.min_hours_between,
        verbose_logging=request.verbose_logging,
        openai_voice=request.openai_voice,
        gemini_voice=request.gemini_voice,
        grok_voice=request.grok_voice,
        call_greeting=request.call_greeting,
        max_parallel_calls=request.max_parallel_calls,
        dispatch_pacing_seconds=request.dispatch_pacing_seconds,
    )

    await provider.update_dispatcher_settings(dispatcher_settings)

    # Apply to running dispatcher immediately
    get_dispatcher().update_config(
        poll_interval=request.poll_interval,
        dispatch_timeout=request.dispatch_timeout,
        max_attempts_ordered=request.max_attempts_ordered,
        max_attempts_other=request.max_attempts_other,
        min_hours_between=request.min_hours_between,
        verbose_logging=request.verbose_logging,
        max_parallel_calls=request.max_parallel_calls,
        dispatch_pacing_seconds=request.dispatch_pacing_seconds,
    )

    return await settings_response_and_broadcast(provider)


@router.put("/allow-live-calls", response_model=SystemSettingsResponse)
async def set_allow_live_calls(request: AllowLiveCallsRequest):
    """Toggle live Twilio calls on/off."""
    provider = get_settings_provider()
    await provider.set_allow_live_calls(request.allowed)
    return await settings_response_and_broadcast(provider)


@router.put("/allowed-phones", response_model=SystemSettingsResponse)
async def update_allowed_phones(request: AllowedPhonesRequest):
    """Update the phone number allowlist for live calls."""
    provider = get_settings_provider()
    await provider.update_allowed_phones(request.phones)
    return await settings_response_and_broadcast(provider)


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
    print(f"[SETTINGS] queue_source: {current_settings.queue_source} → {request.source}")

    # When switching TO simulation, activate the scenario
    if request.source == "simulation" and not was_simulation:
        active_id = current_settings.active_scenario_id
        if active_id:
            try:
                await activate_scenario(active_id)
            except ValueError:
                pass  # Scenario not found, skip activation

    return await settings_response_and_broadcast(provider)


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
    print(f"[SETTINGS] patient_source: {current_settings.patient_source} → {request.source}")

    # When switching TO simulation, activate the scenario
    if request.source == "simulation" and not was_simulation:
        active_id = current_settings.active_scenario_id
        if active_id:
            try:
                await activate_scenario(active_id)
            except ValueError:
                pass  # Scenario not found, skip activation

    return await settings_response_and_broadcast(provider)


@router.put("/active-scenario", response_model=SystemSettingsResponse)
async def set_active_scenario(request: ActiveScenarioRequest):
    """Set the active simulation scenario and apply it.

    This updates the active_scenario_id in settings and immediately
    activates the scenario (resets mock providers, restarts dispatcher).
    Call logs are preserved.
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

    return await settings_response_and_broadcast(provider)


@router.put("/call-mode", response_model=SystemSettingsResponse)
async def set_call_mode(request: CallModeRequest):
    """Set the call mode (web or twilio)."""
    from fastapi import HTTPException

    if request.call_mode not in ("web", "twilio"):
        raise HTTPException(status_code=400, detail="call_mode must be 'web' or 'twilio'")

    provider = get_settings_provider()
    current_settings = await provider.get_settings()
    await provider.set_call_mode(request.call_mode)
    print(f"[SETTINGS] call_mode: {current_settings.call_mode} → {request.call_mode}")
    return await settings_response_and_broadcast(provider)


@router.put("/voice-provider", response_model=SystemSettingsResponse)
async def set_voice_provider(request: VoiceProviderRequest):
    """Set the voice provider (openai or gemini)."""
    from fastapi import HTTPException

    if request.voice_provider not in ("openai", "gemini", "grok"):
        raise HTTPException(status_code=400, detail="voice_provider must be 'openai', 'gemini', or 'grok'")

    provider = get_settings_provider()
    current_settings = await provider.get_settings()
    await provider.set_voice_provider(request.voice_provider)
    print(f"[SETTINGS] voice_provider: {current_settings.voice_provider} → {request.voice_provider}")
    return await settings_response_and_broadcast(provider)


@router.put("/mock-mode", response_model=SystemSettingsResponse)
async def set_mock_mode(request: MockModeRequest):
    """Toggle mock mode and set the redirect phone number for Twilio calls/SMS."""
    provider = get_settings_provider()
    await provider.set_mock_mode(request.enabled, request.mock_phone)
    label = f"ON (redirect to {request.mock_phone})" if request.enabled else "OFF"
    print(f"[SETTINGS] mock_mode → {label}")
    return await settings_response_and_broadcast(provider)


@router.put("/daily-report", response_model=SystemSettingsResponse)
async def update_daily_report(request: DailyReportRequest):
    """Update the daily Slack report configuration."""
    from app.models import DailyReportConfig
    provider = get_settings_provider()
    config = DailyReportConfig(
        enabled=request.enabled,
        webhook_url=request.webhook_url.strip(),
        hour=request.hour,
        timezone=request.timezone,
    )
    await provider.update_daily_report(config)
    label = "ON" if request.enabled else "OFF"
    print(f"[SETTINGS] daily_report → {label} (hour={request.hour} tz={request.timezone})")
    return await settings_response_and_broadcast(provider)


@router.put("/intake-v2", response_model=SystemSettingsResponse)
async def update_intake_v2(request: IntakeV2Request):
    """Update the v2 intake-agent feature flags."""
    provider = get_settings_provider()
    from app.models.system_settings import DEFAULT_V2_CONSENT_DISCLOSURE
    disclosure = (request.consent_disclosure or "").strip() or DEFAULT_V2_CONSENT_DISCLOSURE
    config = IntakeV2Settings(
        master_enabled=request.master_enabled,
        tenant_allowlist=list(request.tenant_allowlist),
        order_canary_pct=request.order_canary_pct,
        mode_voice_capture=request.mode_voice_capture,
        mode_portal_copilot=request.mode_portal_copilot,
        multi_call_resume=request.multi_call_resume,
        consent_disclosure=disclosure,
    )
    await provider.update_intake_v2(config)
    print(
        f"[SETTINGS] intake_v2 → master={request.master_enabled} "
        f"canary={request.order_canary_pct}% "
        f"voice={request.mode_voice_capture} "
        f"portal={request.mode_portal_copilot} "
        f"resume={request.multi_call_resume}"
    )
    return await settings_response_and_broadcast(provider)


@router.get("/timezones", response_model=List[str])
async def get_timezones():
    """Get list of available timezones."""
    return COMMON_TIMEZONES


# -- Call greeting / script editor ---------------------------------------------

class CallGreetingRequest(BaseModel):
    call_greeting: str


@router.get("/call-greeting")
async def get_call_greeting():
    """Return the current call greeting text."""
    from app.models.system_settings import DEFAULT_CALL_GREETING
    provider = get_settings_provider()
    settings = await provider.get_settings()
    return {
        "call_greeting": settings.dispatcher_settings.call_greeting,
        "default_greeting": DEFAULT_CALL_GREETING,
    }


@router.put("/call-greeting", response_model=SystemSettingsResponse)
async def update_call_greeting(request: CallGreetingRequest):
    """Update the call greeting text."""
    provider = get_settings_provider()
    settings = await provider.get_settings()
    ds = settings.dispatcher_settings
    ds.call_greeting = request.call_greeting.strip()
    await provider.update_dispatcher_settings(ds)
    print(f"[SETTINGS] call_greeting updated ({len(ds.call_greeting)} chars)")
    return await settings_response_and_broadcast(provider)


# -- Voice preview + selection ------------------------------------------------

OPENAI_VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse"]
GEMINI_VOICES = ["Aoede", "Charon", "Fenrir", "Kore", "Puck", "Leda", "Orus", "Perseus", "Zephyr"]
GROK_VOICES = ["eve", "ara", "rex", "sal", "leo"]


class VoicePreviewRequest(BaseModel):
    provider: str  # "openai" or "gemini"
    voice: str
    text: str = (
        "Hi, this is Ashley with Precise Imaging. "
        "We received your doctor's imaging order and need to schedule your appointment. "
        "Are you available now?"
    )


class VoiceSettingsRequest(BaseModel):
    openai_voice: str = "alloy"
    gemini_voice: str = "Aoede"
    grok_voice: str = "eve"


@router.get("/voices")
async def get_voices():
    """Return available voices for each provider + current selection."""
    provider = get_settings_provider()
    settings = await provider.get_settings()
    return {
        "openai_voices": OPENAI_VOICES,
        "gemini_voices": GEMINI_VOICES,
        "grok_voices": GROK_VOICES,
        "openai_voice": settings.dispatcher_settings.openai_voice,
        "gemini_voice": settings.dispatcher_settings.gemini_voice,
        "grok_voice": settings.dispatcher_settings.grok_voice,
    }


@router.put("/voices", response_model=SystemSettingsResponse)
async def update_voices(request: VoiceSettingsRequest):
    """Update the selected voice for each provider."""
    from fastapi import HTTPException
    if request.openai_voice not in OPENAI_VOICES:
        raise HTTPException(400, f"Invalid OpenAI voice: {request.openai_voice}")
    if request.gemini_voice not in GEMINI_VOICES:
        raise HTTPException(400, f"Invalid Gemini voice: {request.gemini_voice}")
    if request.grok_voice not in GROK_VOICES:
        raise HTTPException(400, f"Invalid Grok voice: {request.grok_voice}")

    provider = get_settings_provider()
    settings = await provider.get_settings()
    ds = settings.dispatcher_settings
    ds.openai_voice = request.openai_voice
    ds.gemini_voice = request.gemini_voice
    ds.grok_voice = request.grok_voice
    await provider.update_dispatcher_settings(ds)
    print(f"[SETTINGS] voices → openai={request.openai_voice}, gemini={request.gemini_voice}, grok={request.grok_voice}")
    return await settings_response_and_broadcast(provider)


@router.post("/voice-preview")
async def voice_preview(request: VoicePreviewRequest):
    """Generate a voice preview clip on demand. Returns audio bytes."""
    from fastapi import HTTPException
    from fastapi.responses import Response as FastResponse
    import base64
    import json as _json
    import struct
    import websockets

    logger.info("[VoicePreview] provider=%s voice=%s", request.provider, request.voice)

    if request.provider == "openai":
        if request.voice not in OPENAI_VOICES:
            raise HTTPException(400, f"Invalid OpenAI voice: {request.voice}")
        from app.providers.settings_provider import get_api_key_sync
        api_key = get_api_key_sync("openai")
        if not api_key:
            raise HTTPException(500, "OpenAI API key not configured")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.audio.speech.create(
                model="tts-1",
                voice=request.voice,
                input=request.text,
                response_format="mp3",
            )
            audio_bytes = response.read()
            logger.info("[VoicePreview] OpenAI OK, %d bytes", len(audio_bytes))
            return FastResponse(content=audio_bytes, media_type="audio/mpeg")
        except Exception as e:
            logger.error("[VoicePreview] OpenAI TTS failed: %s", e)
            raise HTTPException(500, f"OpenAI TTS failed: {e}")

    elif request.provider == "gemini":
        if request.voice not in GEMINI_VOICES:
            raise HTTPException(400, f"Invalid Gemini voice: {request.voice}")
        from app.providers.settings_provider import get_api_key_sync
        api_key = get_api_key_sync("gemini")
        if not api_key:
            raise HTTPException(500, "Gemini API key not configured")

        gemini_model = os.getenv("GEMINI_REALTIME_MODEL", "gemini-3.1-flash-live-preview")
        ws_url = (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
            f"?key={api_key}"
        )
        logger.info("[VoicePreview] Gemini connecting model=%s voice=%s", gemini_model, request.voice)
        try:
            ws = await websockets.connect(ws_url)
        except Exception as e:
            logger.error("[VoicePreview] Gemini WS connect failed: %s", e)
            raise HTTPException(500, f"Gemini connect failed: {e}")

        try:
            setup = {
                "setup": {
                    "model": f"models/{gemini_model}",
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {"voiceName": request.voice}
                            }
                        },
                    },
                    "systemInstruction": {
                        "parts": [{"text": "You are a voice preview generator. Say exactly what the user asks, nothing more."}]
                    },
                }
            }
            await ws.send(_json.dumps(setup))
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8")
            data = _json.loads(msg)
            if "setupComplete" not in data and "setup_complete" not in data:
                logger.error("[VoicePreview] Gemini setup failed: %s", list(data.keys()))
                raise HTTPException(500, f"Gemini Live setup failed: {list(data.keys())}")
            logger.info("[VoicePreview] Gemini setup complete")

            await ws.send(_json.dumps({
                "realtimeInput": {
                    "text": f"Say exactly: {request.text}"
                }
            }))

            audio_chunks: list[bytes] = []
            deadline = asyncio.get_event_loop().time() + 15
            while asyncio.get_event_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    logger.warning("[VoicePreview] Gemini recv timeout after %d chunks", len(audio_chunks))
                    break
                if isinstance(raw, bytes):
                    try:
                        raw = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                ev = _json.loads(raw)
                sc = ev.get("serverContent") or ev.get("server_content") or {}
                mt = sc.get("modelTurn") or sc.get("model_turn") or {}
                for part in mt.get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        audio_chunks.append(base64.b64decode(inline["data"]))
                if sc.get("turnComplete") or sc.get("turn_complete"):
                    break
        except HTTPException:
            raise
        except Exception as e:
            logger.error("[VoicePreview] Gemini error: %s", e)
            raise HTTPException(500, f"Gemini voice preview failed: {e}")
        finally:
            await ws.close()

        if not audio_chunks:
            logger.error("[VoicePreview] Gemini returned no audio")
            raise HTTPException(500, "Gemini Live returned no audio")

        pcm_data = b"".join(audio_chunks)
        data_size = len(pcm_data)
        logger.info("[VoicePreview] Gemini OK, %d chunks, %d bytes", len(audio_chunks), data_size)
        wav_header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + data_size, b"WAVE",
            b"fmt ", 16, 1, 1,
            24000, 24000 * 2,
            2, 16,
            b"data", data_size,
        )
        return FastResponse(content=wav_header + pcm_data, media_type="audio/wav")

    elif request.provider == "grok":
        if request.voice not in GROK_VOICES:
            raise HTTPException(400, f"Invalid Grok voice: {request.voice}")
        from app.providers.settings_provider import get_api_key_sync
        api_key = get_api_key_sync("grok")
        if not api_key:
            raise HTTPException(500, "xAI Grok API key not configured")
        # xAI TTS is a simple HTTP POST that returns raw audio bytes.
        # Codec defaults to mp3; we ask for it explicitly so the
        # Content-Type we hand back is unambiguous.
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.x.ai/v1/tts",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": request.text,
                        "voice_id": request.voice,
                        "language": "en",
                        "output_format": {"codec": "mp3", "sample_rate": 24000},
                    },
                )
            if resp.status_code != 200:
                # xAI returns a JSON error body on failure.
                detail = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                logger.error("[VoicePreview] Grok TTS failed: %s", detail)
                raise HTTPException(500, f"Grok TTS failed (HTTP {resp.status_code}): {detail}")
            audio_bytes = resp.content
            logger.info("[VoicePreview] Grok OK, %d bytes", len(audio_bytes))
            return FastResponse(content=audio_bytes, media_type="audio/mpeg")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("[VoicePreview] Grok TTS error: %s", e)
            raise HTTPException(500, f"Grok TTS failed: {e}")

    else:
        raise HTTPException(400, f"provider must be 'openai', 'gemini', or 'grok'")


# --- API-key configuration ----------------------------------------------------
# Stored in DB so the UI can update them without a server restart. PUT validates
# the key against the provider before saving; GET returns masked status only.

class ApiKeyUpdateRequest(BaseModel):
    provider: str  # "openai" | "gemini" | "grok"
    api_key: str


class ApiKeyStatus(BaseModel):
    configured: bool
    source: str  # "db", "env", or "none"
    preview: str


class ApiKeysStatusResponse(BaseModel):
    openai: ApiKeyStatus
    gemini: ApiKeyStatus
    grok: ApiKeyStatus


# Single source of truth for which provider names the API-keys endpoints
# accept. Keep in sync with _API_KEY_ENV_NAMES in settings_provider.py.
_API_KEY_PROVIDERS = ("openai", "gemini", "grok")


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 11:
        return "***"
    return f"{key[:7]}...{key[-4:]}"


def _status_for(provider_name: str) -> ApiKeyStatus:
    from app.providers.settings_provider import (
        _API_KEY_CACHE,
        _API_KEY_ENV_NAMES,
        get_api_key_sync,
    )
    db_value = (_API_KEY_CACHE.get(provider_name) or "").strip()
    env_value = (os.getenv(_API_KEY_ENV_NAMES.get(provider_name, ""), "") or "").strip()
    effective = get_api_key_sync(provider_name)
    if db_value:
        source = "db"
    elif env_value:
        source = "env"
    else:
        source = "none"
    return ApiKeyStatus(
        configured=bool(effective),
        source=source,
        preview=_mask_key(effective),
    )


async def _validate_openai_key(api_key: str) -> None:
    """Make a tiny live call to confirm the key works. Raises HTTPException on failure."""
    from fastapi import HTTPException
    try:
        from openai import OpenAI, AuthenticationError
    except Exception as e:
        raise HTTPException(500, f"OpenAI SDK unavailable: {e}")
    try:
        client = OpenAI(api_key=api_key)
        # models.list is a cheap auth check
        await asyncio.to_thread(lambda: client.models.list())
    except AuthenticationError:
        raise HTTPException(400, "OpenAI rejected the key (authentication failed)")
    except Exception as e:
        raise HTTPException(400, f"OpenAI key validation failed: {e}")


async def _validate_gemini_key(api_key: str) -> None:
    """Hit a public Gemini REST endpoint to confirm the key works."""
    from fastapi import HTTPException
    import urllib.error
    import urllib.request

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

    def _do_request() -> int:
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code

    try:
        status = await asyncio.to_thread(_do_request)
    except Exception as e:
        raise HTTPException(400, f"Gemini key validation failed: {e}")
    if status == 200:
        return
    if status in (400, 401, 403):
        raise HTTPException(400, "Gemini rejected the key (authentication failed)")
    raise HTTPException(400, f"Gemini key validation failed (HTTP {status})")


@router.get("/api-keys", response_model=ApiKeysStatusResponse)
async def get_api_keys_status():
    """Return masked status for each provider's API key. Never returns plaintext."""
    # Force a fresh DB read so the cache is current
    await get_settings_provider().get_settings()
    return ApiKeysStatusResponse(
        openai=_status_for("openai"),
        gemini=_status_for("gemini"),
        grok=_status_for("grok"),
    )


class ApiKeyRevealResponse(BaseModel):
    provider: str
    source: str  # "db", "env", or "none"
    api_key: str


@router.get("/api-keys/{provider}/reveal", response_model=ApiKeyRevealResponse)
async def reveal_api_key(provider: str):
    """Return the plaintext API key for a provider. Keys are stored plaintext;
    this endpoint is the explicit "view" action behind the UI eye-toggle."""
    from fastapi import HTTPException
    provider_name = (provider or "").strip().lower()
    if provider_name not in _API_KEY_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {_API_KEY_PROVIDERS}")
    # Refresh the cache from DB before reading
    await get_settings_provider().get_settings()
    status = _status_for(provider_name)
    from app.providers.settings_provider import get_api_key_sync
    return ApiKeyRevealResponse(
        provider=provider_name,
        source=status.source,
        api_key=get_api_key_sync(provider_name),
    )


@router.put("/api-keys", response_model=ApiKeysStatusResponse)
async def update_api_key(request: ApiKeyUpdateRequest):
    """Validate the key against the provider, then store it."""
    from fastapi import HTTPException

    provider_name = (request.provider or "").strip().lower()
    if provider_name not in _API_KEY_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {_API_KEY_PROVIDERS}")
    api_key = (request.api_key or "").strip()
    if not api_key:
        raise HTTPException(400, "api_key cannot be empty (use DELETE to clear)")

    if provider_name == "openai":
        await _validate_openai_key(api_key)
    elif provider_name == "gemini":
        await _validate_gemini_key(api_key)
    elif provider_name == "grok":
        # xAI keys are validated by format only; xAI doesn't expose a cheap
        # `validate-credentials` endpoint and the realtime endpoint is the
        # natural integration test.
        if not api_key.startswith("xai-"):
            raise HTTPException(400, "xAI keys must start with 'xai-'")

    provider = get_settings_provider()
    await provider.set_api_key(provider_name, api_key)
    logger.info("[SETTINGS] api_key updated for provider=%s", provider_name)

    # Refresh cache + broadcast that settings changed so other browser windows refetch
    await get_api_keys_status()
    try:
        from app.api.websocket import broadcast_to_dashboards
        await broadcast_to_dashboards({"type": "api_keys_updated", "provider": provider_name})
    except Exception:
        pass

    return ApiKeysStatusResponse(
        openai=_status_for("openai"),
        gemini=_status_for("gemini"),
        grok=_status_for("grok"),
    )


@router.delete("/api-keys/{provider}", response_model=ApiKeysStatusResponse)
async def clear_api_key(provider: str):
    """Remove a provider's key from the DB. Env fallback (if set) becomes active again."""
    from fastapi import HTTPException

    provider_name = (provider or "").strip().lower()
    if provider_name not in _API_KEY_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {_API_KEY_PROVIDERS}")

    settings_provider = get_settings_provider()
    await settings_provider.clear_api_key(provider_name)
    logger.info("[SETTINGS] api_key cleared for provider=%s", provider_name)

    try:
        from app.api.websocket import broadcast_to_dashboards
        await broadcast_to_dashboards({"type": "api_keys_updated", "provider": provider_name})
    except Exception:
        pass

    return ApiKeysStatusResponse(
        openai=_status_for("openai"),
        gemini=_status_for("gemini"),
        grok=_status_for("grok"),
    )
