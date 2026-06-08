"""Runtime SMS provider selection (dev Settings toggle). Falls back to env."""
from pathlib import Path

from app.config import settings

_OVERRIDE_FILE = Path(__file__).resolve().parents[2] / ".sms_provider_override"
_memory_override: str | None = None


def _load_file_override() -> str | None:
    if not _OVERRIDE_FILE.exists():
        return None
    raw = _OVERRIDE_FILE.read_text(encoding="utf-8").strip().lower()
    return raw if raw in {"mock", "twilio"} else None


def get_effective_sms_provider() -> str:
    global _memory_override
    if _memory_override is None:
        _memory_override = _load_file_override()
    if _memory_override in {"mock", "twilio"}:
        return _memory_override
    return settings.backfill_sms_provider.lower()


def is_mock_sms_mode() -> bool:
    return get_effective_sms_provider() == "mock"


def set_sms_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in {"mock", "twilio"}:
        raise ValueError("sms_provider must be mock or twilio")
    global _memory_override
    _memory_override = normalized
    _OVERRIDE_FILE.write_text(normalized, encoding="utf-8")
    return normalized
