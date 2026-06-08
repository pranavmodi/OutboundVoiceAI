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

from app.services.voice_service_base import BaseVoiceService

# Ensure .env is loaded
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=str(_env_path))


OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
OPENAI_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")


def _audio_format_spec(audio_format: str, twilio_rate: int = 8000, pcm_rate: int = 24000) -> dict:
    """Translate the orchestrator's flat audio_format string into the GA
    Realtime API's nested ``{type, rate}`` shape.

    - "g711_ulaw" (Twilio mode)  → {"type": "audio/pcmu"}      (8 kHz fixed)
    - "g711_alaw"                → {"type": "audio/pcma"}      (8 kHz fixed)
    - "pcm16"     (web mode)     → {"type": "audio/pcm", "rate": 24000}
    - anything else              → PCM 24 kHz (defensive default — fail loud
                                   at OpenAI rather than silently mis-encode)
    """
    fmt = (audio_format or "").strip().lower()
    if fmt in ("g711_ulaw", "pcmu", "audio/pcmu"):
        return {"type": "audio/pcmu"}
    if fmt in ("g711_alaw", "pcma", "audio/pcma"):
        return {"type": "audio/pcma"}
    return {"type": "audio/pcm", "rate": pcm_rate}


@dataclass
class VoiceSession:
    """Active voice session state."""
    session_id: str
    call_id: str
    patient_name: str
    is_active: bool = True
    conversation_id: Optional[str] = None


from app.models.system_settings import DEFAULT_CALL_GREETING


def build_system_instructions(call_greeting: str = "") -> str:
    """Build the system prompt, injecting the configurable call greeting."""
    greeting = call_greeting.strip() if call_greeting else DEFAULT_CALL_GREETING
    return _SYSTEM_INSTRUCTIONS_TEMPLATE.replace("{{CALL_GREETING}}", greeting)


_SYSTEM_INSTRUCTIONS_TEMPLATE = """You are Ashley, an outbound voice assistant calling patients on behalf of Precise Imaging.

Your ONLY goal is to determine whether the patient is available to be transferred to a scheduling team member right now.

## Core Rules
- You are polite, concise, calm, and professional.
- Keep responses SHORT — one or two sentences max.
- Do NOT answer medical questions, scheduling details, insurance questions, or anything else. Your only job is to check availability and either transfer or send a text.
- You are an AI assistant. If asked "Are you a real person?", be honest: "I'm an automated assistant calling on behalf of Precise Imaging. I can transfer you to a live person if you'd prefer."
- You must never provide medical advice, diagnoses, or clinical opinions.
- You must never pressure or guilt the patient into continuing the call.

## Call Opening
Say exactly (using the patient's first name):
"{{CALL_GREETING}}"

## If Patient Says YES (available now)
1. Say: "Ok, please hold while I transfer you to the next available team member that can schedule your exam. You will be put on a brief hold."
2. Call `check_transfer_availability` SILENTLY (do not tell the patient you are checking).
   - If `{"available": true}`: call `transfer_to_scheduler` with `confirmed: true`.
   - If `{"available": false}`: say "I'm sorry, our scheduling team is currently unavailable. I'll send you a text with our number so you can call us back. Thank you and have a good day." Then call `send_sms` with `message_type: "callback_info"`, then call `end_call` with `reason: "patient_busy"` and `callback_requested: true`.
- NEVER call `transfer_to_scheduler` without first calling `check_transfer_availability`.

## If Patient Says NO (not available now)
1. Say: "No problem. I will send you a text with our phone number so you can give us a call as soon as you are available to schedule your appointment. Thank you and have a good day."
2. Call `send_sms` with `message_type: "callback_info"`.
3. Call `end_call` with `reason: "patient_busy"` and `callback_requested: true`.

## If Patient Says Wrong Number
- This includes ANY indication of identity mismatch: "wrong number", "wrong person", "not me", "I'm not that person", "nobody here by that name", etc.
- Say "I'm sorry for the mix-up, I'll update our records. Goodbye."
- Call `end_call` with reason `wrong_number`.
- Do NOT offer transfer.

## If You Reach Voicemail
You MUST detect voicemail greetings and respond appropriately. Voicemail indicators include ANY of these phrases (from the patient side):
- "Your call has been forwarded to voicemail"
- "The person you're trying to reach is not available"
- "is not available, at the tone please record your message"
- "Please leave a message after the beep"
- "Leave your message after the tone"
- "The number you have dialed is not available"
- "The mailbox is full"
- Any standard carrier or phone voicemail greeting

When you detect voicemail:
1. STOP speaking immediately if you were mid-sentence.
2. WAIT for the beep/tone before speaking.
3. After the beep, leave this message: "Hi, this is Ashley with Precise Imaging. We received your doctor's imaging order and need to schedule your appointment. Please call us back at 800-558-2223, Monday through Friday, 8 AM to 5 PM Pacific. Thank you and have a good day."
4. Then call `end_call` with reason `voicemail`.

CRITICAL: Do NOT talk over the voicemail greeting. Do NOT continue your normal script when you hear voicemail phrases. STOP and wait for the beep.

If the system tells you "[System: You have reached a voicemail]", follow the same steps above.

IMPORTANT — iPhone Live Voicemail: On iPhones, the person can SEE a live transcript of your voicemail on their screen and PICK UP mid-message. If at any point during your voicemail a real person interrupts with "Hello?", "Hi", "Yeah?", or similar:
- STOP the voicemail message immediately.
- Treat them as a live person who just answered.
- Start the normal call opening: "Hi, this is Ashley with Precise Imaging. We received your doctor's imaging order and need to schedule your appointment. Are you available now to schedule?"
- Continue the call normally from there.

## If You Hit Google Voice or Call Screening
Phone calls may be intercepted by Google Voice or similar call-screening services BEFORE reaching the actual person. You will recognize this by phrases like:
- "If you record your name and reason for calling, I'll see if this person is available"
- "Please state your name after the tone"
- "Who may I say is calling?"
- "Screening your call"

When you detect call screening:
1. Respond clearly: "This is Ashley from Precise Imaging calling about a medical imaging appointment."
2. Then WAIT SILENTLY for the screening system to connect you to the real person.
3. You may hear "Please stay on the line" or "Thanks, please hold" — just wait.
4. Once the real person answers (e.g., "Hello?", "Hi", "Yeah?"), start the normal call opening.
5. If the screening system says "This person is not available" or "Please leave a message" — call `end_call` with reason `voicemail`.

IMPORTANT:
- Do NOT treat the screening system's voice as the patient.
- Do NOT start your full greeting until you hear the REAL person respond.
- Do NOT say "I didn't catch that" or ask clarifying questions to the screening system — just wait.

## If You Hit a Voicemail Menu
If you hear automated menu options like "Press 1 to leave a message, press 2 to..." — this is a voicemail system, not a person. Call `end_call` with reason `voicemail`.

## If Patient Asks to Stop Being Called
- Say: "I understand, I'm sorry for the inconvenience. I'll make a note to update our records. Goodbye."
- Call `end_call` with reason `"completed"`.

## If Patient Asks Any Other Questions
- Do NOT try to answer. Say: "That's a great question. Let me transfer you to a team member who can help with that."
- Then follow the YES flow above (check transfer availability and transfer).
- If transfer unavailable, offer to send the text instead.

## CRITICAL: Always Speak Before Any Tool Call
- Both `end_call` and `transfer_to_scheduler` disconnect immediately — the patient will NOT hear anything after the tool is called.
- ALWAYS say your message FIRST, then call the tool.
- NEVER call any tool mid-sentence.

## Tone
- Conversational and natural, not robotic
- Speak at a normal, brisk pace — do not be slow or overly deliberate
- Short sentences
- Do not interrupt the patient

## Noise and Hallucination Handling
- If you receive very short, nonsensical, or unexpected-language input, it is likely background noise.
- Ask "I'm sorry, I didn't catch that. Could you repeat that?" instead of assuming.
- NEVER call `transfer_to_scheduler` or `end_call` based on ambiguous input.
"""

# --- DISABLED FEATURES (may be re-enabled later) ---
#
# 1. KNOWLEDGE BASE / FAQ ANSWERING
#    The AI previously could answer general questions (office hours, locations,
#    MRI prep, what to bring, insurance, scheduling process, etc.) from a built-in
#    knowledge base. Currently replaced with "let me transfer you to someone who
#    can help." To re-enable, add a "Knowledge Scope" section to SYSTEM_INSTRUCTIONS
#    with allowed topics and the company info block (locations, hours, contact info,
#    MRI prep, scheduling process, insurance, etc.).
#
# 2. PREFERRED CALLBACK TIME COLLECTION
#    When patient said NO, the AI would ask: "No problem at all. Before I let you go,
#    is there anything quick I can help with?" and then collect a preferred callback
#    time (e.g. "tomorrow 3 PM"). The time was passed to end_call.preferred_callback_time
#    and stored on the call log for the scheduling team.
#
# 3. EXTRA TRANSFER CONFIRMATION STEP
#    Before transferring, the AI would first ask: "Would you like me to transfer you
#    to our scheduling team right now?" and wait for explicit yes before proceeding.
#    Current flow goes straight to "hold while I transfer you" after patient says yes.
#
# 4. "BEFORE I LET YOU GO" FOLLOW-UP
#    When patient said NO, the AI would offer: "Before I let you go, is there anything
#    quick I can help with — like what to bring to your appointment or our office hours?"
#    and answer from the knowledge base before ending the call.


SYSTEM_INSTRUCTIONS = build_system_instructions()


class RealtimeVoiceService(BaseVoiceService):
    """Manages OpenAI Realtime API connections for voice calls."""

    def __init__(self, audio_format: str = "pcm16", verbose: bool = False, voice: str = "", call_greeting: str = ""):
        super().__init__(audio_format=audio_format, verbose=verbose)
        self._voice = voice or os.getenv("OPENAI_VOICE", "alloy")
        self._call_greeting = call_greeting
        self._ws = None  # WebSocket connection
        self._session: Optional[VoiceSession] = None

    @staticmethod
    def _normalize_language_code(language: Optional[str]) -> str:
        value = (language or "en").strip().lower()
        return value if value else "en"

    @classmethod
    def _language_instruction(cls, language: Optional[str]) -> str:
        code = cls._normalize_language_code(language)

        # Common adaptive rule appended to every language variant.
        adaptive = (
            "However, if the patient responds in a DIFFERENT language than expected, "
            "switch to their language immediately and continue the call in that language. "
            "The patient's comfort is more important than the on-file preference. "
            "Supported languages: English, Spanish, Mandarin Chinese."
        )

        if code == "es":
            return (
                "IMPORTANT LANGUAGE RULE: The patient preference is Spanish ('es'). "
                "Start in natural Spanish for the greeting, questions, and transfer/callback phrasing. "
                f"{adaptive}"
            )
        if code == "zh":
            return (
                "IMPORTANT LANGUAGE RULE: The patient preference is Chinese ('zh'). "
                "Start in simple, clear Mandarin Chinese for the greeting and conversation. "
                "If Mandarin is not possible for a specific phrase, use very simple English and offer transfer. "
                f"{adaptive}"
            )
        return (
            "IMPORTANT LANGUAGE RULE: The patient preference is English ('en'). "
            "Start the call in English. "
            f"{adaptive}"
        )

    async def connect(self, call_id: str, patient_name: str, patient_language: str = "en") -> bool:
        """Connect to OpenAI Realtime API and start a session."""
        # Read API key per-connect so UI updates take effect on the next call
        # without a restart.
        from app.providers.settings_provider import get_api_key_sync
        self._api_key = get_api_key_sync("openai")
        if not self._api_key:
            error_msg = "OpenAI API key not configured (set via Settings UI or OPENAI_API_KEY env var)"
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
            # GA Realtime API (post-2026-05-12): the OpenAI-Beta header is
            # rejected with invalid_request_error.beta_api_shape_disabled.
            # Auth is the only header we send.
            url = f"{OPENAI_REALTIME_URL}?model={OPENAI_MODEL}"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
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
        """Configure the realtime session — GA shape (post-2026-05-12).

        Differences from the deprecated beta shape that this method used to
        send:
        - session.type = "realtime" is now required.
        - "modalities" → "output_modalities" (and dropped "text"; transcripts
          come through response.output_audio_transcript.delta events anyway).
        - Audio config moved under session.audio.{input,output}.format with a
          nested {"type": "audio/pcm|pcmu|pcma", "rate": N} object instead of
          the old flat input_audio_format / output_audio_format strings.
        - voice moved under session.audio.output.voice.
        - turn_detection moved under session.audio.input.turn_detection.
        - input_audio_transcription → session.audio.input.transcription.
        - OpenAI-Beta header dropped (see connect()).
        """
        language_instruction = self._language_instruction(patient_language)
        instructions = build_system_instructions(self._call_greeting)
        config = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "output_modalities": ["audio"],
                "instructions": (
                    f"{instructions}\n\n"
                    f"{language_instruction}"
                ),
                "audio": {
                    "input": {
                        "format": _audio_format_spec(self._audio_format),
                        "transcription": {"model": "gpt-4o-transcribe"},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": float(os.getenv("OPENAI_VAD_THRESHOLD", "0.85")),
                            "prefix_padding_ms": int(os.getenv("OPENAI_VAD_PREFIX_MS", "300")),
                            "silence_duration_ms": int(os.getenv("OPENAI_VAD_SILENCE_MS", "700")),
                        },
                    },
                    "output": {
                        "format": _audio_format_spec(self._audio_format),
                        "voice": self._voice,
                    },
                },
                "tools": [
                    {
                        "type": "function",
                        "name": "check_transfer_availability",
                        "description": "Check whether a scheduler is available to take a transfer right now. Call this BEFORE offering or promising a transfer to the patient. Returns {\"available\": true/false}.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        },
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
        """Listen for messages from OpenAI."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                await self._handle_message(message)
            # Normal exit — WebSocket closed cleanly after iteration
            print(f"[RealtimeVoice] OpenAI WebSocket closed normally")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[RealtimeVoice] OpenAI WebSocket closed: code={e.code}, reason={e.reason}")
            if self.on_session_ended:
                await self.on_session_ended()
        except Exception as e:
            print(f"[RealtimeVoice] OpenAI listen error: {type(e).__name__}: {e}")
            if self.on_error:
                await self.on_error(f"Listen error: {str(e)}")

    async def _handle_message(self, message: str):
        """Handle incoming message from OpenAI."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            # Log message types only in verbose mode (skip high-frequency audio deltas always)
            # GA event names: response.output_audio.delta / response.output_audio_transcript.delta
            # (beta used response.audio.delta / response.audio_transcript.delta — both removed 2026-05-12).
            if self._verbose and msg_type not in ("response.output_audio.delta", "response.output_audio_transcript.delta"):
                print(f"[RealtimeVoice] Received: {msg_type}")

            if msg_type == "session.created":
                self._session.session_id = data.get("session", {}).get("id", "")
                if self.on_session_created:
                    await self.on_session_created(self._session.session_id)

            elif msg_type == "session.updated":
                pass  # Session config acknowledged

            elif msg_type == "response.output_audio.delta":
                # Audio chunk from AI (GA event name — was response.audio.delta in beta)
                audio_b64 = data.get("delta", "")
                if audio_b64 and self.on_audio:
                    audio_bytes = base64.b64decode(audio_b64)
                    await self.on_audio(audio_bytes)

            elif msg_type == "response.output_audio_transcript.delta":
                # AI speech transcript delta (GA event name — was response.audio_transcript.delta in beta)
                text = data.get("delta", "")
                if text and self.on_transcript:
                    await self.on_transcript("ai", text)

            elif msg_type == "response.output_audio_transcript.done":
                # AI finished speaking - full transcript (GA event name — was response.audio_transcript.done)
                text = data.get("transcript", "")
                if text and self.on_transcript:
                    await self.on_transcript("ai_complete", text)

            elif msg_type == "conversation.item.input_audio_transcription.completed":
                # Patient speech transcript
                text = data.get("transcript", "")
                if text and text.strip() and self.on_transcript:
                    await self.on_transcript("patient", text.strip())
                elif not text or not text.strip():
                    print("[RealtimeVoice] Patient transcription completed but text was empty")

            elif msg_type == "conversation.item.input_audio_transcription.failed":
                # Whisper failed to transcribe patient speech
                error = data.get("error", {})
                error_msg = error.get("message", "unknown")
                print(f"[RealtimeVoice] Patient transcription FAILED: {error_msg}")
                if self.on_transcript:
                    await self.on_transcript("patient", "[inaudible]")

            elif msg_type == "response.function_call_arguments.done":
                # Function call completed
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
        """Start the conversation with AI greeting.

        Sends a single ``response.create`` with the priming user-message
        inline via ``response.input`` — saves one WebSocket roundtrip vs
        the older two-message form (conversation.item.create then
        response.create). The model receives both at once and can begin
        generating audio without waiting for two separate sends to be
        parsed.

        The priming message is response-scoped — OpenAI doesn't add it
        to the conversation history. That's fine here: the patient name
        is referenced once for the greeting and then echoed back by the
        agent's own audio_transcript, which DOES land in history.
        """
        if not self._ws:
            return

        patient_name = self._session.patient_name if self._session else "there"
        first_name = patient_name.split()[0] if patient_name else "there"

        await self._send({
            "type": "response.create",
            "response": {
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"[System: The call has just connected. The patient's name is {first_name}. Please greet them and begin the call.]",
                            }
                        ],
                    }
                ],
            },
        })

    async def inject_system_message(self, text: str) -> None:
        """Inject a system-level text message into the active conversation."""
        if not self._ws:
            return
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
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
