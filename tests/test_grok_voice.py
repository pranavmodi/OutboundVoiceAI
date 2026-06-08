"""Tests for the xAI Grok Voice Agent integration.

Doesn't exercise the live WebSocket — the API requires a valid xAI key and
network access. These tests pin the wiring contracts that future refactors
must not break:

- Grok is recognized as a voice_provider and selects GrokVoiceService.
- get_api_key_sync("grok") falls back to XAI_API_KEY env when DB is empty.
- The session.update payload follows xAI's nested audio-format shape.
- The audio_format mapping translates orchestrator-side names to xAI types.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers import settings_provider
from app.services.grok_voice import GrokVoiceService, _audio_format_spec


# ---- Audio-format translation ------------------------------------------

def test_audio_format_g711_ulaw_maps_to_audio_pcmu_at_8khz():
    assert _audio_format_spec("g711_ulaw") == {"type": "audio/pcmu", "rate": 8000}


def test_audio_format_pcm16_maps_to_audio_pcm_at_24khz():
    assert _audio_format_spec("pcm16") == {"type": "audio/pcm", "rate": 24000}


def test_audio_format_unknown_falls_back_to_pcm():
    # Defensive default — surface the failure from xAI rather than locally.
    assert _audio_format_spec("")["type"] == "audio/pcm"
    assert _audio_format_spec("weird-format")["type"] == "audio/pcm"


def test_audio_format_alaw_maps_to_audio_pcma():
    assert _audio_format_spec("g711_alaw") == {"type": "audio/pcma", "rate": 8000}


# ---- API-key env fallback ----------------------------------------------

def test_grok_key_falls_back_to_xai_api_key_env(monkeypatch):
    """Empty DB cache + XAI_API_KEY env set → env wins."""
    monkeypatch.setitem(settings_provider._API_KEY_CACHE, "grok", "")
    monkeypatch.setenv("XAI_API_KEY", "xai-from-env")
    assert settings_provider.get_api_key_sync("grok") == "xai-from-env"


def test_grok_key_prefers_db_over_env(monkeypatch):
    """Populated DB cache wins over env."""
    monkeypatch.setitem(settings_provider._API_KEY_CACHE, "grok", "xai-from-db")
    monkeypatch.setenv("XAI_API_KEY", "xai-from-env")
    assert settings_provider.get_api_key_sync("grok") == "xai-from-db"


def test_grok_key_missing_when_neither_db_nor_env(monkeypatch):
    monkeypatch.setitem(settings_provider._API_KEY_CACHE, "grok", "")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert settings_provider.get_api_key_sync("grok") == ""


# ---- GrokVoiceService.connect() ----------------------------------------

@pytest.mark.asyncio
async def test_connect_refuses_without_key(monkeypatch):
    """Missing key → returns False, fires on_error, never opens WS."""
    monkeypatch.setitem(settings_provider._API_KEY_CACHE, "grok", "")
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    svc = GrokVoiceService()
    on_error = AsyncMock()
    svc.on_error = on_error

    with patch("app.services.grok_voice.websockets.connect", new=AsyncMock()) as ws_connect:
        ok = await svc.connect("CALL-1", "Jane Doe")
        assert ok is False
        ws_connect.assert_not_awaited()
        on_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_refuses_wrong_prefix(monkeypatch):
    """A non-xAI-shaped key fails fast before any network call."""
    monkeypatch.setitem(settings_provider._API_KEY_CACHE, "grok", "sk-not-a-grok-key")

    svc = GrokVoiceService()
    on_error = AsyncMock()
    svc.on_error = on_error

    with patch("app.services.grok_voice.websockets.connect", new=AsyncMock()) as ws_connect:
        ok = await svc.connect("CALL-1", "Jane Doe")
        assert ok is False
        ws_connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_update_uses_nested_audio_format(monkeypatch):
    """xAI uses audio.input.format / audio.output.format (nested), NOT the
    OpenAI flat input_audio_format / output_audio_format strings. Regression
    test so a future cleanup doesn't accidentally restore OpenAI's shape."""
    monkeypatch.setitem(settings_provider._API_KEY_CACHE, "grok", "xai-test-key")

    sent: list = []
    fake_ws = MagicMock()
    fake_ws.send = AsyncMock(side_effect=lambda payload: sent.append(json.loads(payload)))

    async def _ws_connect(*args, **kwargs):
        return fake_ws

    svc = GrokVoiceService(audio_format="g711_ulaw", voice="eve")

    with patch("app.services.grok_voice.websockets.connect", new=_ws_connect), \
         patch("app.services.grok_voice.asyncio.create_task"):
        ok = await svc.connect("CALL-G1", "Jane Doe")

    assert ok is True

    # The first thing sent on connect is session.update — find it.
    session_update = next(m for m in sent if m.get("type") == "session.update")
    sess = session_update["session"]

    # Nested audio shape — NOT OpenAI's flat strings.
    assert "input_audio_format" not in sess
    assert "output_audio_format" not in sess
    assert sess["audio"]["input"]["format"] == {"type": "audio/pcmu", "rate": 8000}
    assert sess["audio"]["output"]["format"] == {"type": "audio/pcmu", "rate": 8000}

    # Voice and tools shape is unchanged from OpenAI's payload.
    assert sess["voice"] == "eve"
    assert isinstance(sess["tools"], list) and len(sess["tools"]) >= 4
    assert sess["turn_detection"]["type"] == "server_vad"


# ---- Orchestrator provider selection -----------------------------------

@pytest.mark.asyncio
async def test_voice_provider_grok_selects_grok_service():
    """Confirm CallSession.start_call routes to GrokVoiceService when
    settings.voice_provider == 'grok'.

    We don't drive the full call — just intercept the constructor and bail
    out early via a forced exception, then assert the import happened.
    """
    from app.models import CallLog, Language, Patient, SystemSettings
    from app.services.call_orchestrator import CallSession

    session = CallSession()
    settings = SystemSettings()
    settings.voice_provider = "grok"
    settings.dispatcher_settings.grok_voice = "eve"

    settings_provider_mock = AsyncMock()
    settings_provider_mock.get_settings = AsyncMock(return_value=settings)

    call_log_provider = AsyncMock()
    call_log_provider.create_call = AsyncMock(return_value=CallLog(
        call_id="CALL-GROK", patient_id="PAT-1", patient_name="X",
        phone="+15550000000", order_id="O", priority_bucket=0,
    ))

    queue_provider = MagicMock()
    queue_provider.get_state = MagicMock(return_value=MagicMock(to_dict=lambda: {}))

    grok_ctor = MagicMock(side_effect=RuntimeError("stop here"))

    patient = Patient(
        patient_id="PAT-1", name="X", phone="+15550000000",
        language=Language.ENGLISH, order_id="O",
    )

    with patch("app.services.call_orchestrator.get_patient_provider", return_value=AsyncMock()), \
         patch("app.services.call_orchestrator.get_settings_provider", return_value=settings_provider_mock), \
         patch("app.services.call_orchestrator.get_call_log_provider", return_value=call_log_provider), \
         patch("app.services.call_orchestrator.get_queue_provider", return_value=queue_provider), \
         patch.object(CallSession, "_evaluate_intake_v2_gate", AsyncMock()), \
         patch("app.services.orchestrator_registry.get_registry", return_value=MagicMock()), \
         patch("app.services.grok_voice.GrokVoiceService", grok_ctor):
        try:
            await session.start_call("PAT-1", call_mode="web", patient_override=patient, settings_override=settings)
        except Exception:
            pass

    # GrokVoiceService was selected (and immediately raised our sentinel) —
    # if voice_provider routing were broken, OpenAI's service would be used
    # and this mock would never be called.
    grok_ctor.assert_called_once()
    # Voice arg threaded through correctly.
    assert grok_ctor.call_args.kwargs["voice"] == "eve"
