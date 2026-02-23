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
- Immediately call the `end_call` tool with reason `wrong_number`.
- Do NOT offer transfer if the patient says wrong number.
- Do NOT call `transfer_to_scheduler` after any wrong-number statement.

## If You Reach Voicemail
- If you hear voicemail greeting/beep language, treat it as voicemail.
- End the call using the `end_call` tool with reason `voicemail`.
- Do not attempt transfer.

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

---

## PRECISE IMAGING COMPANY INFORMATION

### Locations
We have 3 convenient locations:

1. **Downtown Los Angeles**
   - 350 South Grand Avenue, Suite 100, Los Angeles, CA 90071
   - Near the Pershing Square Metro station
   - Parking available in the building garage

2. **Burbank**
   - 2500 West Olive Avenue, Suite 200, Burbank, CA 91505
   - Free parking lot on site
   - Near the Burbank Town Center

3. **Long Beach**
   - 100 Oceangate, Suite 400, Long Beach, CA 90802
   - Validated parking in the building
   - Near the Long Beach Convention Center

### Office Hours
- **Monday to Friday**: 7:00 AM to 7:00 PM
- **Saturday**: 8:00 AM to 4:00 PM
- **Sunday**: Closed
- We offer early morning and evening appointments for your convenience.

### Contact Information
- **Main Phone**: 1-800-555-SCAN (1-800-555-7226)
- **Website**: www.preciseimaging.com
- **Patient Portal**: portal.preciseimaging.com
- **Email**: scheduling@preciseimaging.com

### What to Bring to Your MRI Appointment
1. **Photo ID** - Driver's license or government-issued ID
2. **Insurance card** - Both front and back
3. **Referral or prescription** - From your doctor (if not already sent to us)
4. **List of medications** - Including dosages
5. **Prior imaging** - CDs or reports from previous scans if you have them

### MRI Preparation Instructions
- **Clothing**: Wear comfortable, loose-fitting clothes without metal (zippers, buttons, underwire). We provide gowns if needed.
- **Metal**: Remove all jewelry, watches, hair clips, belts, and piercings before the scan.
- **Eating**: You can eat normally unless your doctor gave specific instructions. For abdominal MRIs, you may need to fast for 4 hours.
- **Arrive early**: Please arrive 15 minutes before your appointment to complete paperwork.
- **Claustrophobia**: Let us know if you're anxious about enclosed spaces - we can discuss options.
- **Implants**: Tell us about any metal implants, pacemakers, or medical devices.

### How Long Does an MRI Take?
- Most MRI scans take **30 to 60 minutes** depending on the body part being scanned.
- Some specialized scans may take up to 90 minutes.
- You'll need to lie still during the scan.
- You can listen to music during the procedure.

### Scheduling Process
1. When transferred to scheduling, a team member will verify your insurance.
2. They'll find an appointment time that works for you.
3. You'll receive a confirmation text and email with appointment details.
4. A reminder will be sent 24 hours before your appointment.
5. You can reschedule or cancel through our patient portal or by calling us.

### Insurance and Payment
- We accept most major insurance plans including Medicare.
- Our team will verify your coverage before your appointment.
- For questions about coverage or costs, our scheduling team can help.
- Payment plans are available if needed.

### After the Scan
- Results are typically sent to your doctor within 24-48 hours.
- Your doctor will review the results and contact you.
- You can also view results in the patient portal once released.
- We do not provide results directly to patients - please contact your referring physician.
"""


class RealtimeVoiceService:
    """Manages OpenAI Realtime API connections for voice calls."""

    def __init__(self, audio_format: str = "pcm16"):
        """Initialize voice service.

        Args:
            audio_format: Audio format for OpenAI Realtime API.
                          "pcm16" for browser WebSocket (24kHz 16-bit PCM).
                          "g711_ulaw" for Twilio media streams (8kHz mulaw).
        """
        self._ws = None  # WebSocket connection
        self._session: Optional[VoiceSession] = None
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        self._audio_format = audio_format

        # Callbacks
        self.on_transcript: Optional[Callable[[str, str], Any]] = None  # (speaker, text)
        self.on_audio: Optional[Callable[[bytes], Any]] = None  # audio data
        self.on_session_created: Optional[Callable[[str], Any]] = None
        self.on_session_ended: Optional[Callable[[], Any]] = None
        self.on_error: Optional[Callable[[str], Any]] = None
        self.on_function_call: Optional[Callable[[str, dict], Any]] = None

    @staticmethod
    def _normalize_language_code(language: Optional[str]) -> str:
        value = (language or "en").strip().lower()
        return value if value else "en"

    @classmethod
    def _language_instruction(cls, language: Optional[str]) -> str:
        code = cls._normalize_language_code(language)
        if code == "es":
            return (
                "IMPORTANT LANGUAGE RULE: The patient preference is Spanish ('es'). "
                "Speak in natural Spanish for the entire call, including greeting, questions, and transfer/callback phrasing. "
                "Only switch to English if the patient explicitly asks you to."
            )
        if code == "zh":
            return (
                "IMPORTANT LANGUAGE RULE: The patient preference is Chinese ('zh'). "
                "Speak in simple, clear Mandarin Chinese for the entire call when possible. "
                "If Mandarin is not possible for a specific phrase, use very simple English and offer transfer."
            )
        return (
            "IMPORTANT LANGUAGE RULE: The patient preference is English ('en'). "
            "Conduct the call in English."
        )

    async def connect(self, call_id: str, patient_name: str, patient_language: str = "en") -> bool:
        """Connect to OpenAI Realtime API and start a session."""
        # Validate API key first
        if not self._api_key:
            error_msg = "OPENAI_API_KEY not set in environment"
            print(f"[RealtimeVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

        if not self._api_key.startswith("sk-"):
            error_msg = f"Invalid API key format (should start with 'sk-')"
            print(f"[RealtimeVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

        try:
            url = f"{OPENAI_REALTIME_URL}?model={OPENAI_MODEL}"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "OpenAI-Beta": "realtime=v1",
            }

            print(f"[RealtimeVoice] Connecting to {url}...")
            self._ws = await websockets.connect(url, additional_headers=headers)
            print(f"[RealtimeVoice] WebSocket connected successfully")

            self._session = VoiceSession(
                session_id="",
                call_id=call_id,
                patient_name=patient_name,
            )

            # Configure the session
            await self._configure_session(patient_name, patient_language)

            # Start listening for messages
            asyncio.create_task(self._listen())

            return True

        except websockets.exceptions.InvalidStatusCode as e:
            error_msg = f"OpenAI rejected connection (HTTP {e.status_code})"
            if e.status_code == 401:
                error_msg = "Invalid OpenAI API key (401 Unauthorized)"
            elif e.status_code == 403:
                error_msg = "API key doesn't have access to Realtime API (403 Forbidden)"
            print(f"[RealtimeVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Connection failed: {type(e).__name__}: {str(e)}"
            print(f"[RealtimeVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

    async def _configure_session(self, patient_name: str, patient_language: str = "en"):
        """Configure the realtime session."""
        language_instruction = self._language_instruction(patient_language)
        # Update session with instructions
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": (
                    f"{SYSTEM_INSTRUCTIONS.replace('{patient_name}', patient_name)}\n\n"
                    f"{language_instruction}"
                ),
                "voice": "alloy",
                "input_audio_format": self._audio_format,
                "output_audio_format": self._audio_format,
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

            # Log important message types
            if msg_type not in ("response.audio.delta", "response.audio_transcript.delta"):
                print(f"[RealtimeVoice] Received: {msg_type}")

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
        # Debug: log audio chunks being sent (first time only to avoid spam)
        if not hasattr(self, '_audio_logged'):
            self._audio_logged = True
            print(f"[RealtimeVoice] Sending audio chunk: {len(audio_data)} bytes")
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
