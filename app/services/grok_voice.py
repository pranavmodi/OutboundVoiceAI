"""xAI Grok Voice Agent realtime voice service.

xAI's Grok Voice Agent API is OpenAI-Realtime-compatible at the wire-protocol
level, with three documented deltas (per docs.x.ai/docs/guides/voice/agent):

1. session.update audio format is NESTED. OpenAI uses flat string fields
   (input_audio_format / output_audio_format); xAI uses
   audio.input.format.{type,rate} / audio.output.format.{type,rate}.
2. response.text.delta replaces OpenAI's response.output_text.delta
   (irrelevant here — we only consume audio + audio_transcript events).
3. xAI does NOT emit conversation.item.done, input_audio_buffer.timeout_triggered,
   or rate_limits.updated. We don't handle any of those in OpenAI either, so
   this is a no-op for us.

Everything else — session.update, conversation.item.create, response.create,
input_audio_buffer.append/commit/clear, response.function_call_arguments.done
— matches OpenAI byte-for-byte, so this file is a near-clone of
realtime_voice.py with the URL, auth header, key validation, and session
config adapted.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import websockets
from dotenv import load_dotenv

from app.services.voice_service_base import BaseVoiceService
from app.services.realtime_voice import build_system_instructions, VoiceSession
from app.services.realtime_voice import RealtimeVoiceService as _OpenAIRealtimeService

# Ensure .env is loaded (mirrors realtime_voice.py for env-var fallback).
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=str(_env_path))


GROK_REALTIME_URL = "wss://api.x.ai/v1/realtime"
GROK_MODEL = os.getenv("GROK_REALTIME_MODEL", "grok-voice-think-fast-1.0")


def _audio_format_spec(audio_format: str, twilio_rate: int = 8000, pcm_rate: int = 24000) -> dict:
    """Translate the orchestrator's audio_format string into xAI's nested form.

    - "g711_ulaw" (Twilio mode)  → {"type": "audio/pcmu", "rate": 8000}
    - "pcm16"     (web mode)     → {"type": "audio/pcm",  "rate": 24000}
    - Anything else falls through to PCM 24kHz so the connection still opens
      and the error surfaces from xAI rather than from a malformed config.
    """
    fmt = (audio_format or "").strip().lower()
    if fmt in ("g711_ulaw", "pcmu", "audio/pcmu"):
        return {"type": "audio/pcmu", "rate": twilio_rate}
    if fmt in ("g711_alaw", "pcma", "audio/pcma"):
        return {"type": "audio/pcma", "rate": twilio_rate}
    return {"type": "audio/pcm", "rate": pcm_rate}


class GrokVoiceService(BaseVoiceService):
    """Manages xAI Grok Voice Agent API connections for voice calls.

    Shares the OpenAI service's prompt template and language-selection logic
    via build_system_instructions / _OpenAIRealtimeService._language_instruction
    so all three providers (OpenAI, Gemini, Grok) follow identical scripting.
    """

    def __init__(self, audio_format: str = "pcm16", verbose: bool = False, voice: str = "", call_greeting: str = ""):
        super().__init__(audio_format=audio_format, verbose=verbose)
        # xAI voices: eve, ara, rex, sal, leo (plus custom IDs).
        self._voice = voice or os.getenv("GROK_VOICE", "eve")
        self._call_greeting = call_greeting
        self._ws = None
        self._session: Optional[VoiceSession] = None
        self._api_key = ""

    async def connect(self, call_id: str, patient_name: str, patient_language: str = "en") -> bool:
        """Connect to xAI Grok Voice Agent API and start a session."""
        from app.providers.settings_provider import get_api_key_sync
        # Read per-connect so UI key updates take effect on the next call
        # without a server restart.
        self._api_key = get_api_key_sync("grok")
        if not self._api_key:
            error_msg = "xAI Grok API key not configured (set via Settings UI or XAI_API_KEY env var)"
            print(f"[GrokVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

        if not self._api_key.startswith("xai-"):
            error_msg = "Invalid xAI API key format (should start with 'xai-')"
            print(f"[GrokVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

        try:
            url = f"{GROK_REALTIME_URL}?model={GROK_MODEL}"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
            }

            print(f"[GrokVoice] Connecting to {url}...")
            self._ws = await websockets.connect(url, additional_headers=headers)
            print(f"[GrokVoice] WebSocket connected successfully")

            self._session = VoiceSession(
                session_id="",
                call_id=call_id,
                patient_name=patient_name,
            )

            await self._configure_session(patient_name, patient_language)
            asyncio.create_task(self._listen())
            return True

        except websockets.exceptions.InvalidStatusCode as e:
            error_msg = f"xAI rejected connection (HTTP {e.status_code})"
            if e.status_code == 401:
                error_msg = "Invalid xAI API key (401 Unauthorized)"
            elif e.status_code == 403:
                error_msg = "API key doesn't have access to Grok Voice (403 Forbidden)"
            print(f"[GrokVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Connection failed: {type(e).__name__}: {str(e)}"
            print(f"[GrokVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

    async def _configure_session(self, patient_name: str, patient_language: str = "en"):
        """Configure the realtime session.

        The system prompt + language instructions are identical to OpenAI's;
        only the audio block uses xAI's nested shape (`audio.input.format` /
        `audio.output.format`) instead of OpenAI's flat string fields.
        """
        language_instruction = _OpenAIRealtimeService._language_instruction(patient_language)
        instructions = build_system_instructions(self._call_greeting)
        config = {
            "type": "session.update",
            "session": {
                "voice": self._voice,
                "instructions": f"{instructions}\n\n{language_instruction}",
                "audio": {
                    "input": {"format": _audio_format_spec(self._audio_format)},
                    "output": {"format": _audio_format_spec(self._audio_format)},
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": float(os.getenv("GROK_VAD_THRESHOLD", "0.85")),
                    "prefix_padding_ms": int(os.getenv("GROK_VAD_PREFIX_MS", "300")),
                    "silence_duration_ms": int(os.getenv("GROK_VAD_SILENCE_MS", "700")),
                },
                # Same tool surface as the OpenAI realtime service so the
                # CallOrchestrator's function-call handler works unchanged.
                "tools": [
                    {
                        "type": "function",
                        "name": "check_transfer_availability",
                        "description": "Check whether a scheduler is available to take a transfer right now. Call this BEFORE offering or promising a transfer to the patient. Returns {\"available\": true/false}.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                    {
                        "type": "function",
                        "name": "transfer_to_scheduler",
                        "description": "Transfer the patient to a human scheduler only after explicit consent to transfer. Never use this tool when patient indicates wrong number or identity mismatch.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "confirmed": {
                                    "type": "boolean",
                                    "description": "Whether the patient confirmed they want to transfer",
                                }
                            },
                            "required": ["confirmed"],
                        },
                    },
                    {
                        "type": "function",
                        "name": "end_call",
                        "description": "End the call. Use reason='wrong_number' immediately when patient says this is the wrong number/person.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "reason": {
                                    "type": "string",
                                    "enum": ["patient_busy", "wrong_number", "voicemail", "completed", "patient_request"],
                                    "description": "The reason for ending the call",
                                },
                                "callback_requested": {
                                    "type": "boolean",
                                    "description": "Whether the patient requested a callback",
                                },
                                "preferred_callback_time": {
                                    "type": "string",
                                    "description": "Optional preferred callback preference, e.g. 'tomorrow 3 PM' or 'after 1 hour'.",
                                },
                            },
                            "required": ["reason"],
                        },
                    },
                    {
                        "type": "function",
                        "name": "send_sms",
                        "description": "Send an SMS to the patient with callback information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "message_type": {
                                    "type": "string",
                                    "enum": ["callback_info", "appointment_reminder"],
                                    "description": "Type of message to send",
                                }
                            },
                            "required": ["message_type"],
                        },
                    },
                ],
            },
        }
        await self._send(config)

    async def _listen(self):
        if not self._ws:
            return
        try:
            async for message in self._ws:
                await self._handle_message(message)
            print(f"[GrokVoice] xAI WebSocket closed normally")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[GrokVoice] xAI WebSocket closed: code={e.code}, reason={e.reason}")
            if self.on_session_ended:
                await self.on_session_ended()
        except Exception as e:
            print(f"[GrokVoice] xAI listen error: {type(e).__name__}: {e}")
            if self.on_error:
                await self.on_error(f"Listen error: {str(e)}")

    async def _handle_message(self, message: str):
        """Dispatch xAI events. Names match OpenAI Realtime for everything we
        actually consume (audio, audio_transcript, function_call_arguments,
        error). Events xAI doesn't emit are simply never received."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if self._verbose and msg_type not in ("response.audio.delta", "response.audio_transcript.delta"):
                print(f"[GrokVoice] Received: {msg_type}")

            if msg_type == "session.created":
                self._session.session_id = data.get("session", {}).get("id", "")
                if self.on_session_created:
                    await self.on_session_created(self._session.session_id)

            elif msg_type == "session.updated":
                pass

            elif msg_type == "response.audio.delta":
                audio_b64 = data.get("delta", "")
                if audio_b64 and self.on_audio:
                    await self.on_audio(base64.b64decode(audio_b64))

            elif msg_type == "response.audio_transcript.delta":
                text = data.get("delta", "")
                if text and self.on_transcript:
                    await self.on_transcript("ai", text)

            elif msg_type == "response.audio_transcript.done":
                text = data.get("transcript", "")
                if text and self.on_transcript:
                    await self.on_transcript("ai_complete", text)

            elif msg_type == "conversation.item.input_audio_transcription.completed":
                text = data.get("transcript", "")
                if text and text.strip() and self.on_transcript:
                    await self.on_transcript("patient", text.strip())
                elif not text or not text.strip():
                    print("[GrokVoice] Patient transcription completed but text was empty")

            elif msg_type == "conversation.item.input_audio_transcription.failed":
                error = data.get("error", {})
                error_msg = error.get("message", "unknown")
                print(f"[GrokVoice] Patient transcription FAILED: {error_msg}")
                if self.on_transcript:
                    await self.on_transcript("patient", "[inaudible]")

            elif msg_type == "response.function_call_arguments.done":
                name = data.get("name", "")
                fn_call_id = data.get("call_id", "")
                args_str = data.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                if self.on_function_call:
                    await self.on_function_call(name, args, fn_call_id)

            elif msg_type == "error":
                error = data.get("error", {})
                error_msg = error.get("message", "Unknown error")
                if self.on_error:
                    await self.on_error(error_msg)

        except json.JSONDecodeError:
            pass
        except Exception as e:
            if self.on_error:
                await self.on_error(f"Message handling error: {str(e)}")

    async def _send(self, data: dict):
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def send_audio(self, audio_data: bytes):
        if not self._ws or not self._session or not self._session.is_active:
            return
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        if not hasattr(self, "_audio_logged"):
            self._audio_logged = True
            print(f"[GrokVoice] Sending audio chunk: {len(audio_data)} bytes")
        await self._send({"type": "input_audio_buffer.append", "audio": audio_b64})

    async def commit_audio(self):
        if self._ws:
            await self._send({"type": "input_audio_buffer.commit"})

    async def start_response(self):
        if self._ws:
            await self._send({"type": "response.create"})

    async def cancel_response(self):
        if self._ws:
            await self._send({"type": "response.cancel"})

    async def send_function_result(self, call_id: str, result: dict):
        if self._ws:
            await self._send({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            })
            await self._send({"type": "response.create"})

    async def start_conversation(self):
        if not self._ws:
            return
        patient_name = self._session.patient_name if self._session else "there"
        first_name = patient_name.split()[0] if patient_name else "there"
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"[System: The call has just connected. The patient's name is {first_name}. Please greet them and begin the call.]",
                    }
                ],
            },
        })
        await self._send({"type": "response.create"})

    async def inject_system_message(self, text: str) -> None:
        if not self._ws:
            return
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        })
        await self._send({"type": "response.create"})

    async def disconnect(self):
        if self._session:
            self._session.is_active = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self.on_session_ended:
            await self.on_session_ended()

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._session is not None and self._session.is_active
