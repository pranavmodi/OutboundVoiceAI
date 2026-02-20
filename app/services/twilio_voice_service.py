"""Twilio outbound call + media stream bridge to OpenAI Realtime API."""
import asyncio
import base64
import html
import json
import logging
import os
import uuid
from typing import Optional, Callable, Any

from twilio.rest import Client
from fastapi import WebSocket

from app.services.realtime_voice import RealtimeVoiceService

logger = logging.getLogger(__name__)

# Registry of pending Twilio streams keyed by stream_id.
# When the orchestrator places a call it registers a bridge here;
# when Twilio connects the media stream WS, we look it up.
_pending_bridges: dict[str, "TwilioMediaBridge"] = {}


def register_bridge(stream_id: str, bridge: "TwilioMediaBridge"):
    _pending_bridges[stream_id] = bridge


def pop_bridge(stream_id: str) -> Optional["TwilioMediaBridge"]:
    return _pending_bridges.pop(stream_id, None)


class TwilioMediaBridge:
    """Bridges a Twilio media stream WebSocket with an OpenAI RealtimeVoiceService."""

    def __init__(self, voice_service: RealtimeVoiceService):
        self.voice_service = voice_service
        self._twilio_ws: Optional[WebSocket] = None
        self._stream_sid: Optional[str] = None
        self._call_sid: Optional[str] = None
        self._connected = asyncio.Event()

        # Wire OpenAI audio output → Twilio
        self._original_on_audio = voice_service.on_audio
        voice_service.on_audio = self._forward_audio_to_twilio

    async def _forward_audio_to_twilio(self, audio_data: bytes):
        """Send OpenAI audio to Twilio media stream."""
        if self._twilio_ws and self._stream_sid:
            payload = base64.b64encode(audio_data).decode("utf-8")
            msg = {
                "event": "media",
                "streamSid": self._stream_sid,
                "media": {"payload": payload},
            }
            try:
                await self._twilio_ws.send_json(msg)
            except Exception as e:
                logger.error(f"Error sending audio to Twilio: {e}")

        # Also forward to original callback (browser gets transcripts, not audio in twilio mode,
        # but keep the chain intact in case it's used for logging)
        if self._original_on_audio:
            await self._original_on_audio(audio_data)

    async def handle_twilio_ws(self, websocket: WebSocket):
        """Handle an incoming Twilio media stream WebSocket."""
        self._twilio_ws = websocket
        logger.info("Twilio media stream WebSocket connected")

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                event = msg.get("event")

                if event == "connected":
                    logger.info("Twilio stream connected")

                elif event == "start":
                    self._stream_sid = msg["start"]["streamSid"]
                    self._call_sid = msg["start"].get("callSid")
                    logger.info(f"Twilio stream started: streamSid={self._stream_sid}")
                    self._connected.set()

                elif event == "media":
                    # Forward Twilio audio → OpenAI
                    payload = msg["media"]["payload"]
                    audio_bytes = base64.b64decode(payload)
                    if self.voice_service.is_connected:
                        await self.voice_service.send_audio(audio_bytes)

                elif event == "stop":
                    logger.info("Twilio stream stopped")
                    break

        except Exception as e:
            logger.error(f"Twilio media stream error: {e}")
        finally:
            self._twilio_ws = None
            self._connected.clear()

    async def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """Wait for Twilio to connect the media stream."""
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False


def place_twilio_call(
    to_number: str,
    twiml_url: str,
    status_callback_url: Optional[str] = None,
) -> str:
    """Place an outbound call via Twilio REST API. Returns Call SID.

    Raises RuntimeError if ALLOW_TWILIO_CALLS env var is not set to 'true'.
    """
    if os.getenv("ALLOW_TWILIO_CALLS", "false").lower() != "true":
        raise RuntimeError(
            "Twilio calls are disabled. Set ALLOW_TWILIO_CALLS=true to enable."
        )

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")

    client = Client(account_sid, auth_token)
    create_kwargs = {
        "to": to_number,
        "from_": from_number,
        "url": twiml_url,
        # Requirement: enable AMD for voicemail detection.
        "machine_detection": "DetectMessageEnd",
    }
    if status_callback_url:
        create_kwargs["status_callback"] = status_callback_url
        create_kwargs["status_callback_method"] = "POST"
        create_kwargs["status_callback_event"] = ["answered", "completed"]

    call = client.calls.create(**create_kwargs)
    logger.info(f"Twilio call placed: SID={call.sid}, to={to_number}")
    return call.sid


def generate_stream_id() -> str:
    return uuid.uuid4().hex[:12]


def play_voicemail_and_hangup(call_sid: str, message: str):
    """Update an in-progress Twilio call to play voicemail then hang up."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not account_sid or not auth_token:
        raise RuntimeError("Twilio is not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")

    escaped = html.escape(message, quote=True)
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Say voice=\"alice\">{escaped}</Say>"
        "<Hangup/>"
        "</Response>"
    )

    client = Client(account_sid, auth_token)
    client.calls(call_sid).update(twiml=twiml)
