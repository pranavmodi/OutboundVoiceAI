"""Settings provider for system configuration — DB-backed."""
import os
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.db.models import SystemSettingsRow
from app.models import (
    ApiKeys,
    BusinessHours,
    HolidayEntry,
    QueueThresholds,
    DispatcherSettings,
    DailyReportConfig,
    IntakeV2Settings,
    SystemSettings,
)
from app.models.system_settings import DEFAULT_CALL_GREETING, DEFAULT_V2_CONSENT_DISCLOSURE
from typing import List


# In-process cache so sync call sites (stt.py, tts.py, llm.py) can read keys
# without going async. Mirrors the DB row; populated on every settings read and
# explicitly invalidated on every set/clear. Empty string = "not set in DB"
# and the env var of the same NAME is used as a fallback.
_API_KEY_CACHE: dict[str, str] = {"openai": "", "gemini": "", "grok": ""}
_API_KEY_ENV_NAMES: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "grok": "XAI_API_KEY",
}


def get_api_key_sync(provider_name: str) -> str:
    """Sync key lookup with env fallback. Safe to call from any context."""
    key = (_API_KEY_CACHE.get(provider_name) or "").strip()
    if key:
        return key
    env_name = _API_KEY_ENV_NAMES.get(provider_name)
    if not env_name:
        return ""
    return (os.getenv(env_name, "") or "").strip()


# Common timezones for selection
COMMON_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "Pacific/Honolulu",
    "UTC",
]


MAX_PARALLEL_CALLS_CEILING = 10  # hard cap until Twilio capacity is validated higher


def _clamp_parallel(value) -> int:
    """Bound max_parallel_calls into [1, MAX_PARALLEL_CALLS_CEILING]."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    if n < 1:
        return 1
    if n > MAX_PARALLEL_CALLS_CEILING:
        return MAX_PARALLEL_CALLS_CEILING
    return n


def _normalize_holidays(raw_holidays) -> List[HolidayEntry]:
    items = raw_holidays if isinstance(raw_holidays, list) else []
    normalized: List[HolidayEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date_str = str(item.get("date", "")).strip()
        name = str(item.get("name", "")).strip()
        if not date_str or not name:
            continue
        recurring = bool(item.get("recurring", True))
        normalized.append(HolidayEntry(date=date_str, name=name, recurring=recurring))
    return normalized


def _is_holiday(today: date, holidays: List[HolidayEntry]) -> bool:
    for holiday in holidays:
        try:
            holiday_date = datetime.strptime(holiday.date, "%Y-%m-%d").date()
        except Exception:
            continue
        if holiday.recurring:
            if holiday_date.month == today.month and holiday_date.day == today.day:
                return True
        elif holiday_date == today:
            return True
    return False


def _matching_holiday(today: date, holidays: List[HolidayEntry]) -> Optional[HolidayEntry]:
    for holiday in holidays:
        try:
            holiday_date = datetime.strptime(holiday.date, "%Y-%m-%d").date()
        except Exception:
            continue
        if holiday.recurring:
            if holiday_date.month == today.month and holiday_date.day == today.day:
                return holiday
        elif holiday_date == today:
            return holiday
    return None


def _row_to_settings(row: SystemSettingsRow) -> SystemSettings:
    bh = row.business_hours
    qt = row.queue_thresholds
    settings = SystemSettings.__new__(SystemSettings)
    settings.system_enabled = row.system_enabled
    settings.business_hours = BusinessHours(
        start_time=bh.get("start_time", "08:00"),
        end_time=bh.get("end_time", "17:00"),
        enabled=bh.get("enabled", False),
        timezone=bh.get("timezone", "America/New_York"),
        days_of_week=bh.get("days_of_week", [0, 1, 2, 3, 4]),  # Default Mon-Fri
        holidays=_normalize_holidays(bh.get("holidays", [])),
    )
    settings.queue_thresholds = QueueThresholds(
        calls_waiting_threshold=qt.get("calls_waiting_threshold", 1),
        holdtime_threshold_seconds=qt.get("holdtime_threshold_seconds", 30),
        stable_polls_required=qt.get("stable_polls_required", 3),
    )
    ds = row.dispatcher_settings if row.dispatcher_settings else {}
    # Migrate legacy single max_attempts → per-status values on read.
    legacy_max = int(ds.get("max_attempts", 4))
    settings.dispatcher_settings = DispatcherSettings(
        poll_interval=ds.get("poll_interval", 10),
        dispatch_timeout=ds.get("dispatch_timeout", 30),
        max_attempts_ordered=int(ds.get("max_attempts_ordered", legacy_max)),
        max_attempts_other=int(ds.get("max_attempts_other", legacy_max)),
        min_hours_between=ds.get("min_hours_between", 6),
        verbose_logging=ds.get("verbose_logging", False),
        openai_voice=ds.get("openai_voice", "alloy"),
        gemini_voice=ds.get("gemini_voice", "Aoede"),
        grok_voice=ds.get("grok_voice", "eve"),
        call_greeting=ds.get("call_greeting", DEFAULT_CALL_GREETING),
        max_parallel_calls=_clamp_parallel(ds.get("max_parallel_calls", 1)),
        dispatch_pacing_seconds=int(ds.get("dispatch_pacing_seconds", 1)),
    )
    settings.allow_live_calls = row.allow_live_calls if row.allow_live_calls is not None else False
    settings.allowed_phones = row.allowed_phones if row.allowed_phones is not None else []
    settings.queue_source = row.queue_source if row.queue_source is not None else "simulation"
    settings.patient_source = row.patient_source if row.patient_source is not None else "simulation"
    settings.active_scenario_id = row.active_scenario_id
    settings.call_mode = row.call_mode if row.call_mode is not None else "web"
    settings.mock_mode = row.mock_mode if row.mock_mode is not None else False
    settings.mock_phone = row.mock_phone if row.mock_phone is not None else ""
    settings.voice_provider = getattr(row, "voice_provider", None) or "openai"
    dr = row.daily_report or {}
    settings.daily_report = DailyReportConfig(
        enabled=bool(dr.get("enabled", False)),
        webhook_url=str(dr.get("webhook_url", "")),
        hour=int(dr.get("hour", 7)),
        timezone=str(dr.get("timezone", "America/Los_Angeles")),
    )
    iv = getattr(row, "intake_v2", None) or {}
    raw_pct = iv.get("order_canary_pct", 0)
    try:
        canary_pct = max(0, min(100, int(raw_pct)))
    except (TypeError, ValueError):
        canary_pct = 0
    raw_allowlist = iv.get("tenant_allowlist", [])
    allowlist = [str(t) for t in raw_allowlist if isinstance(raw_allowlist, list) and str(t).strip()]
    settings.intake_v2 = IntakeV2Settings(
        master_enabled=bool(iv.get("master_enabled", False)),
        tenant_allowlist=allowlist,
        order_canary_pct=canary_pct,
        mode_voice_capture=bool(iv.get("mode_voice_capture", False)),
        mode_portal_copilot=bool(iv.get("mode_portal_copilot", False)),
        multi_call_resume=bool(iv.get("multi_call_resume", False)),
        consent_disclosure=str(iv.get("consent_disclosure", DEFAULT_V2_CONSENT_DISCLOSURE)),
    )
    ak = getattr(row, "api_keys", None) or {}
    openai_key = str(ak.get("openai", "") or "")
    gemini_key = str(ak.get("gemini", "") or "")
    grok_key = str(ak.get("grok", "") or "")
    settings.api_keys = ApiKeys(openai=openai_key, gemini=gemini_key, grok=grok_key)
    _API_KEY_CACHE["openai"] = openai_key
    _API_KEY_CACHE["gemini"] = gemini_key
    _API_KEY_CACHE["grok"] = grok_key
    return settings


class SettingsProvider:
    """Manages system settings with PostgreSQL storage."""

    async def get_settings(self) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                return SystemSettings()
            return _row_to_settings(row)

    async def update_settings(self, settings: SystemSettings) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1)
                session.add(row)
            row.system_enabled = settings.system_enabled
            row.business_hours = {
                "start_time": settings.business_hours.start_time,
                "end_time": settings.business_hours.end_time,
                "enabled": settings.business_hours.enabled,
                "timezone": settings.business_hours.timezone,
                "days_of_week": settings.business_hours.days_of_week,
                "holidays": [
                    {
                        "date": h.date,
                        "name": h.name,
                        "recurring": h.recurring,
                    }
                    for h in settings.business_hours.holidays
                ],
            }
            row.queue_thresholds = {
                "calls_waiting_threshold": settings.queue_thresholds.calls_waiting_threshold,
                "holdtime_threshold_seconds": settings.queue_thresholds.holdtime_threshold_seconds,
                "stable_polls_required": settings.queue_thresholds.stable_polls_required,
            }
            row.dispatcher_settings = {
                "poll_interval": settings.dispatcher_settings.poll_interval,
                "dispatch_timeout": settings.dispatcher_settings.dispatch_timeout,
                "max_attempts": settings.dispatcher_settings.max_attempts,
                "min_hours_between": settings.dispatcher_settings.min_hours_between,
                "verbose_logging": settings.dispatcher_settings.verbose_logging,
                "max_parallel_calls": _clamp_parallel(settings.dispatcher_settings.max_parallel_calls),
                "dispatch_pacing_seconds": int(settings.dispatcher_settings.dispatch_pacing_seconds),
            }
            row.allow_live_calls = settings.allow_live_calls
            row.allowed_phones = settings.allowed_phones
            row.queue_source = settings.queue_source
            row.patient_source = settings.patient_source
            # NOTE: mock_mode, mock_phone, and daily_report are NOT updated
            # here — they have their own dedicated endpoints.  Overwriting
            # them from the generic settings payload would silently reset
            # them to defaults whenever any other setting is saved.
            await session.commit()
            return _row_to_settings(row)

    async def set_system_enabled(self, enabled: bool) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1)
                session.add(row)
            row.system_enabled = enabled
            await session.commit()
            return _row_to_settings(row)

    async def update_business_hours(self, business_hours: BusinessHours) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(
                    id=1,
                    business_hours={},
                    queue_thresholds={
                        "calls_waiting_threshold": 1,
                        "holdtime_threshold_seconds": 30,
                        "stable_polls_required": 3,
                    },
                )
                session.add(row)
            row.business_hours = {
                "start_time": business_hours.start_time,
                "end_time": business_hours.end_time,
                "enabled": business_hours.enabled,
                "timezone": business_hours.timezone,
                "days_of_week": business_hours.days_of_week,
                "holidays": [
                    {
                        "date": h.date,
                        "name": h.name,
                        "recurring": h.recurring,
                    }
                    for h in business_hours.holidays
                ],
            }
            await session.commit()
            return _row_to_settings(row)

    async def update_queue_thresholds(self, thresholds: QueueThresholds) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(
                    id=1,
                    business_hours={
                        "start_time": "08:00",
                        "end_time": "17:00",
                        "enabled": False,
                        "timezone": "America/New_York",
                        "days_of_week": [0, 1, 2, 3, 4],
                        "holidays": [],
                    },
                    queue_thresholds={},
                )
                session.add(row)
            row.queue_thresholds = {
                "calls_waiting_threshold": thresholds.calls_waiting_threshold,
                "holdtime_threshold_seconds": thresholds.holdtime_threshold_seconds,
                "stable_polls_required": thresholds.stable_polls_required,
            }
            await session.commit()
            return _row_to_settings(row)

    async def update_dispatcher_settings(self, dispatcher_settings: DispatcherSettings) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(
                    id=1,
                    business_hours={
                        "start_time": "08:00",
                        "end_time": "17:00",
                        "enabled": False,
                        "timezone": "America/New_York",
                        "days_of_week": [0, 1, 2, 3, 4],
                        "holidays": [],
                    },
                    queue_thresholds={
                        "calls_waiting_threshold": 1,
                        "holdtime_threshold_seconds": 30,
                        "stable_polls_required": 3,
                    },
                    dispatcher_settings={},
                )
                session.add(row)
            row.dispatcher_settings = {
                "poll_interval": dispatcher_settings.poll_interval,
                "dispatch_timeout": dispatcher_settings.dispatch_timeout,
                "max_attempts_ordered": dispatcher_settings.max_attempts_ordered,
                "max_attempts_other": dispatcher_settings.max_attempts_other,
                "min_hours_between": dispatcher_settings.min_hours_between,
                "verbose_logging": dispatcher_settings.verbose_logging,
                "openai_voice": dispatcher_settings.openai_voice,
                "gemini_voice": dispatcher_settings.gemini_voice,
                "grok_voice": dispatcher_settings.grok_voice,
                "call_greeting": dispatcher_settings.call_greeting,
                "max_parallel_calls": _clamp_parallel(dispatcher_settings.max_parallel_calls),
                "dispatch_pacing_seconds": int(dispatcher_settings.dispatch_pacing_seconds),
            }
            await session.commit()
            return _row_to_settings(row)

    async def set_allow_live_calls(self, allowed: bool) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.allow_live_calls = allowed
            await session.commit()
            return _row_to_settings(row)

    async def update_allowed_phones(self, phones: List[str]) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.allowed_phones = phones
            await session.commit()
            return _row_to_settings(row)

    async def is_phone_allowed(self, phone: str) -> bool:
        """Check if a phone number is in the allowlist. Empty list = block all."""
        settings = await self.get_settings()
        if not settings.allowed_phones:
            return False
        return phone in settings.allowed_phones

    async def is_within_business_hours(self) -> bool:
        reason = await self.get_business_hours_block_reason()
        return reason is None

    async def get_business_hours_block_reason(self) -> Optional[str]:
        settings = await self.get_settings()
        bh = settings.business_hours
        if not bh.enabled:
            return None
        try:
            tz = ZoneInfo(bh.timezone)
            now = datetime.now(tz)
            current_time = now.strftime("%H:%M")
            current_day = now.weekday()  # 0=Monday, 6=Sunday
            today = now.date()

            # Check holiday calendar first (blocks even during valid weekday/time).
            holiday = _matching_holiday(today, bh.holidays)
            if holiday:
                return f"Holiday configured: {holiday.name} ({holiday.date})"

            # Check if current day is in allowed days
            if current_day not in bh.days_of_week:
                return "Outside configured business days"

            # Check if current time is within hours
            if not (bh.start_time <= current_time <= bh.end_time):
                return f"Outside business hours ({bh.start_time}-{bh.end_time} {bh.timezone})"
            return None
        except Exception:
            return None

    async def can_make_outbound_call(self) -> bool:
        settings = await self.get_settings()
        if not settings.system_enabled:
            return False
        if not await self.is_within_business_hours():
            return False
        return True

    async def set_patient_source(self, source: str) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.patient_source = source
            await session.commit()
            return _row_to_settings(row)

    async def set_queue_source(self, source: str) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.queue_source = source
            await session.commit()
            return _row_to_settings(row)

    async def set_active_scenario_id(self, scenario_id: str) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.active_scenario_id = scenario_id
            await session.commit()
            return _row_to_settings(row)

    async def set_call_mode(self, call_mode: str) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.call_mode = call_mode
            await session.commit()
            return _row_to_settings(row)

    async def set_voice_provider(self, voice_provider: str) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.voice_provider = voice_provider
            await session.commit()
            return _row_to_settings(row)

    async def set_mock_mode(self, enabled: bool, mock_phone: str = "") -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.mock_mode = enabled
            row.mock_phone = mock_phone
            await session.commit()
            return _row_to_settings(row)

    async def update_daily_report(self, config: DailyReportConfig) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.daily_report = {
                "enabled": config.enabled,
                "webhook_url": config.webhook_url,
                "hour": max(0, min(23, int(config.hour))),
                "timezone": config.timezone or "America/Los_Angeles",
            }
            await session.commit()
            return _row_to_settings(row)

    async def update_intake_v2(self, config: IntakeV2Settings) -> SystemSettings:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            row.intake_v2 = {
                "master_enabled": bool(config.master_enabled),
                "tenant_allowlist": [str(t) for t in config.tenant_allowlist],
                "order_canary_pct": max(0, min(100, int(config.order_canary_pct))),
                "mode_voice_capture": bool(config.mode_voice_capture),
                "mode_portal_copilot": bool(config.mode_portal_copilot),
                "multi_call_resume": bool(config.multi_call_resume),
                "consent_disclosure": str(config.consent_disclosure or "").strip(),
            }
            await session.commit()
            return _row_to_settings(row)

    async def get_thresholds(self) -> QueueThresholds:
        settings = await self.get_settings()
        return settings.queue_thresholds

    async def get_api_key(self, provider_name: str) -> str:
        """Return the API key for a provider, falling back to env if not in DB."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is not None:
                _row_to_settings(row)  # refreshes _API_KEY_CACHE
        return get_api_key_sync(provider_name)

    async def set_api_key(self, provider_name: str, api_key: str) -> SystemSettings:
        """Write a provider key to the DB and update the in-process cache."""
        if provider_name not in _API_KEY_ENV_NAMES:
            raise ValueError(f"Unknown provider: {provider_name}")
        clean = (api_key or "").strip()
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                row = SystemSettingsRow(id=1, business_hours={}, queue_thresholds={})
                session.add(row)
            existing = dict(row.api_keys or {})
            existing[provider_name] = clean
            row.api_keys = existing
            await session.commit()
            _API_KEY_CACHE[provider_name] = clean
            return _row_to_settings(row)

    async def clear_api_key(self, provider_name: str) -> SystemSettings:
        """Remove a provider key from the DB. Env fallback (if set) becomes active again."""
        return await self.set_api_key(provider_name, "")

    async def bootstrap_api_keys_from_env(self) -> None:
        """One-shot: copy env-var keys into the DB on startup if DB has none.

        Lets existing deployments transition to DB-backed keys without
        manual reconfiguration. Only fills empty slots — never overwrites a
        value the operator has already saved.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettingsRow).where(SystemSettingsRow.id == 1))
            row = result.scalar_one_or_none()
            if row is None:
                return
            current = dict(row.api_keys or {})
            changed = False
            for provider_name, env_name in _API_KEY_ENV_NAMES.items():
                if (current.get(provider_name) or "").strip():
                    continue
                env_value = (os.getenv(env_name, "") or "").strip()
                if env_value:
                    current[provider_name] = env_value
                    changed = True
            if changed:
                row.api_keys = current
                await session.commit()
            _row_to_settings(row)  # populate cache regardless


# Global instance
_settings_provider: Optional[SettingsProvider] = None


def get_settings_provider() -> SettingsProvider:
    """Get the global settings provider instance."""
    global _settings_provider
    if _settings_provider is None:
        _settings_provider = SettingsProvider()
    return _settings_provider
