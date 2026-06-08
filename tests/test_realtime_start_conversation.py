"""Pin the start_conversation payload shape for RealtimeVoiceService.

start_conversation switched from a two-message exchange (conversation.item.
create + response.create) to a single response.create with the priming
user-message inline via response.input. This saves one WebSocket roundtrip
and reduces time-to-first-speech.

If anyone reverts to the two-message form by accident, these tests fail —
which catches a real regression because the latency hit isn't visible in
ordinary integration tests.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.realtime_voice import RealtimeVoiceService, VoiceSession


@pytest.mark.asyncio
async def test_start_conversation_sends_single_response_create():
    """Exactly one WS send. Payload type is response.create."""
    svc = RealtimeVoiceService()
    svc._ws = AsyncMock()
    svc._session = VoiceSession(session_id="s1", call_id="CALL-1", patient_name="Jane Doe")

    await svc.start_conversation()

    assert svc._ws.send.await_count == 1
    payload = json.loads(svc._ws.send.await_args.args[0])
    assert payload["type"] == "response.create"


@pytest.mark.asyncio
async def test_start_conversation_uses_inline_input():
    """The priming message lives in response.input — not conversation.item.create."""
    svc = RealtimeVoiceService()
    svc._ws = AsyncMock()
    svc._session = VoiceSession(session_id="s1", call_id="CALL-1", patient_name="Jane Doe")

    await svc.start_conversation()

    payload = json.loads(svc._ws.send.await_args.args[0])
    items = payload["response"]["input"]
    assert isinstance(items, list) and len(items) == 1
    item = items[0]
    assert item["type"] == "message"
    assert item["role"] == "user"
    content = item["content"][0]
    assert content["type"] == "input_text"
    assert "Jane" in content["text"]  # first name extracted


@pytest.mark.asyncio
async def test_start_conversation_extracts_first_name():
    """Multi-token names: use first token. Defensive for edge cases."""
    svc = RealtimeVoiceService()
    svc._ws = AsyncMock()
    svc._session = VoiceSession(
        session_id="s1", call_id="CALL-1",
        patient_name="MARIA GARCIA DE LA CRUZ",
    )

    await svc.start_conversation()

    payload = json.loads(svc._ws.send.await_args.args[0])
    text = payload["response"]["input"][0]["content"][0]["text"]
    assert "MARIA" in text
    assert "GARCIA" not in text  # second token should be dropped


@pytest.mark.asyncio
async def test_start_conversation_handles_missing_session():
    """No session = still sends, with 'there' as a placeholder name.
    The WS path is the gating condition, not the session — losing the
    session shouldn't break the greeting if the WS is up."""
    svc = RealtimeVoiceService()
    svc._ws = AsyncMock()
    svc._session = None

    await svc.start_conversation()

    svc._ws.send.assert_awaited_once()
    payload = json.loads(svc._ws.send.await_args.args[0])
    text = payload["response"]["input"][0]["content"][0]["text"]
    assert "there" in text


@pytest.mark.asyncio
async def test_start_conversation_handles_missing_ws():
    """No WebSocket = no crash (defensive)."""
    svc = RealtimeVoiceService()
    svc._ws = None
    svc._session = VoiceSession(session_id="s1", call_id="CALL-1", patient_name="Jane Doe")

    # Should not raise.
    await svc.start_conversation()
