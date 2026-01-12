"""OpenAI Realtime API voice service."""
import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass
import websockets
from dotenv import load_dotenv

# Ensure .env is loaded
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=str(_env_path))


OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
OPENAI_MODEL = "gpt-4o-realtime-preview-2024-12-17"


@dataclass
class VoiceSession:
    """Active voice session state."""
    session_id: str
    call_id: str
    patient_name: str
    is_active: bool = True
    conversation_id: Optional[str] = None


SYSTEM_INSTRUCTIONS = """You are an outbound AI voice assistant calling patients on behalf of Precise Imaging, a medical imaging company.

Your primary goal is to determine whether the patient is available and willing to be transferred to a human scheduler right now.

Your secondary goal is to answer general, non-clinical, non-diagnostic company questions if needed.

## Core Rules
- You are polite, concise, calm, and professional.
- You must never provide medical advice, diagnoses, or clinical opinions.
- You must never discuss protected health information unless the patient confirms their identity.
- You must never pressure, threaten, or guilt the patient into continuing the call.
- If the patient is confused, upset, or requests a human immediately, comply.
- Keep responses SHORT - under 2 sentences when possible.

## Call Opening
1. Greet the patient by first name only.
2. Identify yourself as an automated assistant calling on behalf of Precise Imaging.
3. Clearly state the purpose of the call: checking availability to help schedule their MRI appointment.
4. Ask if now is a good time.

## If Patient is Available
- Confirm they are willing to be transferred to a human scheduler.
- Say "Great, let me transfer you now to our scheduling team."
- Then indicate you are transferring (the system will handle the actual transfer).

## If Patient is Busy
- Ask for permission to note a better callback time.
- Offer to send a text message with the callback number.
- Thank them and end politely.

## If Patient Says Wrong Number
- Apologize sincerely.
- Say you'll update the records.
- End the call quickly.

## Knowledge Scope - You MAY Answer:
- Office hours and locations
- General scheduling process
- What to bring to an MRI appointment
- How to contact the office
- What will happen next if transferred

## You May NOT Answer:
- Medical questions
- Billing disputes
- Test results
- Anything involving diagnoses

If asked something outside scope, say you're not able to help with that and offer to transfer to a human.

## Tone
- Conversational, not robotic
- Short sentences
- One question at a time
- Allow pauses for natural speech
- Do not interrupt
"""


class RealtimeVoiceService:
    """Manages OpenAI Realtime API connections for voice calls."""

    def __init__(self):
        self._ws = None  # WebSocket connection
        self._session: Optional[VoiceSession] = None
        self._api_key = os.getenv("OPENAI_API_KEY", "")

        # Callbacks
        self.on_transcript: Optional[Callable[[str, str], Any]] = None  # (speaker, text)
        self.on_audio: Optional[Callable[[bytes], Any]] = None  # audio data
        self.on_session_created: Optional[Callable[[str], Any]] = None
        self.on_session_ended: Optional[Callable[[], Any]] = None
        self.on_error: Optional[Callable[[str], Any]] = None
        self.on_function_call: Optional[Callable[[str, dict], Any]] = None

    async def connect(self, call_id: str, patient_name: str) -> bool:
        """Connect to OpenAI Realtime API and start a session."""
        try:
            url = f"{OPENAI_REALTIME_URL}?model={OPENAI_MODEL}"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "OpenAI-Beta": "realtime=v1",
            }

            self._ws = await websockets.connect(url, additional_headers=headers)
            self._session = VoiceSession(
                session_id="",
                call_id=call_id,
                patient_name=patient_name,
            )

            # Configure the session
            await self._configure_session(patient_name)

            # Start listening for messages
            asyncio.create_task(self._listen())

            return True

        except Exception as e:
            if self.on_error:
                await self.on_error(f"Connection failed: {str(e)}")
            return False

    async def _configure_session(self, patient_name: str):
        """Configure the realtime session."""
        # Update session with instructions
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": SYSTEM_INSTRUCTIONS.replace("{patient_name}", patient_name),
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "tools": [
                    {
                        "type": "function",
                        "name": "transfer_to_scheduler",
                        "description": "Transfer the patient to a human scheduler. Call this when the patient confirms they want to be transferred.",
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
                        "description": "End the call. Call this when the conversation is complete.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "reason": {
                                    "type": "string",
                                    "enum": ["patient_busy", "wrong_number", "completed", "patient_request"],
                                    "description": "The reason for ending the call",
                                },
                                "callback_requested": {
                                    "type": "boolean",
                                    "description": "Whether the patient requested a callback",
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
        """Listen for messages from OpenAI."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            if self.on_session_ended:
                await self.on_session_ended()
        except Exception as e:
            if self.on_error:
                await self.on_error(f"Listen error: {str(e)}")

    async def _handle_message(self, message: str):
        """Handle incoming message from OpenAI."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "session.created":
                self._session.session_id = data.get("session", {}).get("id", "")
                if self.on_session_created:
                    await self.on_session_created(self._session.session_id)

            elif msg_type == "session.updated":
                pass  # Session config acknowledged

            elif msg_type == "response.audio.delta":
                # Audio chunk from AI
                audio_b64 = data.get("delta", "")
                if audio_b64 and self.on_audio:
                    audio_bytes = base64.b64decode(audio_b64)
                    await self.on_audio(audio_bytes)

            elif msg_type == "response.audio_transcript.delta":
                # AI speech transcript delta
                text = data.get("delta", "")
                if text and self.on_transcript:
                    await self.on_transcript("ai", text)

            elif msg_type == "response.audio_transcript.done":
                # AI finished speaking - full transcript
                text = data.get("transcript", "")
                if text and self.on_transcript:
                    await self.on_transcript("ai_complete", text)

            elif msg_type == "conversation.item.input_audio_transcription.completed":
                # Patient speech transcript
                text = data.get("transcript", "")
                if text and self.on_transcript:
                    await self.on_transcript("patient", text)

            elif msg_type == "response.function_call_arguments.done":
                # Function call completed
                name = data.get("name", "")
                args_str = data.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                if self.on_function_call:
                    await self.on_function_call(name, args)

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
        """Send a message to OpenAI."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def send_audio(self, audio_data: bytes):
        """Send audio data to OpenAI."""
        if not self._ws or not self._session or not self._session.is_active:
            return

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        await self._send({
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        })

    async def commit_audio(self):
        """Commit the audio buffer (signal end of speech)."""
        if self._ws:
            await self._send({"type": "input_audio_buffer.commit"})

    async def start_response(self):
        """Trigger AI to generate a response."""
        if self._ws:
            await self._send({"type": "response.create"})

    async def cancel_response(self):
        """Cancel the current AI response."""
        if self._ws:
            await self._send({"type": "response.cancel"})

    async def send_function_result(self, call_id: str, result: dict):
        """Send function call result back to OpenAI."""
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
        """Start the conversation with AI greeting."""
        if not self._ws:
            return

        # Send initial user context as a text message
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

    async def disconnect(self):
        """Disconnect from OpenAI."""
        if self._session:
            self._session.is_active = False

        if self._ws:
            await self._ws.close()
            self._ws = None

        if self.on_session_ended:
            await self.on_session_ended()

    @property
    def is_connected(self) -> bool:
        """Check if connected to OpenAI."""
        return self._ws is not None and self._session is not None and self._session.is_active
