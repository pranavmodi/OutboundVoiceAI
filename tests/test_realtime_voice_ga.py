"""Realtime GA compatibility tests."""
import base64
import json
from unittest.mock import AsyncMock

import pytest

from app.services.realtime_voice import OPENAI_MODEL, RealtimeVoiceService, _audio_format_spec


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, payload: str):
        self.sent.append(json.loads(payload))


def test_audio_format_spec_maps_twilio_mulaw_to_pcmu():
    assert _audio_format_spec("g711_ulaw") == {"type": "audio/pcmu"}
    assert _audio_format_spec("pcma") == {"type": "audio/pcma"}
    assert _audio_format_spec("pcm16") == {"type": "audio/pcm", "rate": 24000}


@pytest.mark.asyncio
async def test_configure_session_uses_realtime_ga_audio_shape():
    service = RealtimeVoiceService(audio_format="g711_ulaw", voice="marin")
    ws = FakeWebSocket()
    service._ws = ws

    await service._configure_session("Jane Doe")

    event = ws.sent[0]
    session = event["session"]
    assert event["type"] == "session.update"
    assert session["type"] == "realtime"
    assert session["model"] == OPENAI_MODEL
    assert session["output_modalities"] == ["audio"]
    assert session["audio"]["input"]["format"] == {"type": "audio/pcmu"}
    assert session["audio"]["output"]["format"] == {"type": "audio/pcmu"}
    assert session["audio"]["output"]["voice"] == "marin"
    assert session["audio"]["input"]["transcription"] == {"model": "gpt-4o-transcribe"}
    assert session["audio"]["input"]["turn_detection"]["type"] == "server_vad"
    assert "modalities" not in session
    assert "input_audio_format" not in session
    assert "output_audio_format" not in session
    assert "input_audio_transcription" not in session
    assert "turn_detection" not in session


@pytest.mark.asyncio
async def test_handle_message_accepts_ga_output_audio_events():
    service = RealtimeVoiceService()
    service.on_audio = AsyncMock()
    service.on_transcript = AsyncMock()

    audio = base64.b64encode(b"hello").decode("utf-8")
    await service._handle_message(json.dumps({"type": "response.output_audio.delta", "delta": audio}))
    await service._handle_message(json.dumps({"type": "response.output_audio_transcript.delta", "delta": "Hi"}))
    await service._handle_message(json.dumps({"type": "response.output_audio_transcript.done", "transcript": "Hi there"}))

    service.on_audio.assert_awaited_once_with(b"hello")
    service.on_transcript.assert_any_await("ai", "Hi")
    service.on_transcript.assert_any_await("ai_complete", "Hi there")
