"""Google Gemini Live API voice service.

Based on the working implementation at https://github.com/pranavmodi/autocaller.

Key differences from OpenAI Realtime:
- Gemini accepts 16kHz PCM16 input, outputs 24kHz PCM16
- Twilio sends 8kHz mulaw — audio transcoding is required
- Uses v1beta API endpoint with API key in query string
- camelCase JSON wire format
- Tool definitions use functionDeclarations format
"""
import asyncio
import audioop
import base64
import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import websockets
from dotenv import load_dotenv

from app.services.voice_service_base import BaseVoiceService
from app.services.realtime_voice import build_system_instructions

# Ensure .env is loaded
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=str(_env_path))


GEMINI_MODEL = os.getenv("GEMINI_REALTIME_MODEL", "gemini-3.1-flash-live-preview")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Aoede")

# Gemini WebSocket endpoint (v1beta)
GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)


@dataclass
class GeminiSession:
    """Active Gemini voice session state."""
    session_id: str
    call_id: str
    patient_name: str
    is_active: bool = True


class GeminiVoiceService(BaseVoiceService):
    """Manages Google Gemini Live API connections for voice calls."""

    def __init__(self, audio_format: str = "pcm16", verbose: bool = False, voice: str = "", call_greeting: str = ""):
        super().__init__(audio_format=audio_format, verbose=verbose)
        self._voice = voice or GEMINI_VOICE
        self._call_greeting = call_greeting
        self._ws = None
        self._session: Optional[GeminiSession] = None
        # Audio transcoding state for mulaw ↔ PCM conversion (Twilio mode)
        self._inbound_state = None   # mulaw 8kHz → PCM 16kHz
        self._outbound_state = None  # PCM 24kHz → mulaw 8kHz

    @staticmethod
    def _language_instruction(language: Optional[str]) -> str:
        """Reuse OpenAI's language instruction logic."""
        from app.services.realtime_voice import RealtimeVoiceService
        return RealtimeVoiceService._language_instruction(language)

    async def connect(self, call_id: str, patient_name: str, patient_language: str = "en") -> bool:
        """Connect to Gemini Live API and start a session."""
        from app.providers.settings_provider import get_api_key_sync
        self._api_key = get_api_key_sync("gemini")
        if not self._api_key:
            error_msg = "Gemini API key not configured (set via Settings UI or GEMINI_API_KEY env var)"
            print(f"[GeminiVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

        try:
            url = f"{GEMINI_WS_URL}?key={self._api_key}"

            print(f"[GeminiVoice] Connecting to Gemini Live API (model={GEMINI_MODEL})...")
            self._ws = await websockets.connect(url)
            print(f"[GeminiVoice] WebSocket connected successfully")

            self._session = GeminiSession(
                session_id="",
                call_id=call_id,
                patient_name=patient_name,
            )

            # Reset transcoding state
            self._inbound_state = None
            self._outbound_state = None

            # Send setup message
            await self._configure_session(patient_name, patient_language)

            # Start listening for messages
            asyncio.create_task(self._listen())

            if self.on_session_created:
                await self.on_session_created(call_id)

            return True

        except Exception as e:
            error_msg = f"Gemini connection failed: {type(e).__name__}: {str(e)}"
            print(f"[GeminiVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

    async def _configure_session(self, patient_name: str, patient_language: str = "en"):
        """Send the BidiGenerateContent setup message."""
        language_instruction = self._language_instruction(patient_language)
        instructions = f"{build_system_instructions(self._call_greeting)}\n\n{language_instruction}"

        # Tools in Gemini functionDeclarations format
        tools = [
            {
                "functionDeclarations": [
                    {
                        "name": "check_transfer_availability",
                        "description": "Check whether a scheduler is available to take a transfer right now.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "transfer_to_scheduler",
                        "description": "Transfer the patient to a human scheduler only after explicit consent.",
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
                        "name": "end_call",
                        "description": "End the call.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "reason": {
                                    "type": "string",
                                    "description": "The reason for ending the call",
                                    "enum": ["patient_busy", "wrong_number", "voicemail", "completed", "patient_request"],
                                },
                                "callback_requested": {
                                    "type": "boolean",
                                    "description": "Whether the patient requested a callback",
                                },
                                "preferred_callback_time": {
                                    "type": "string",
                                    "description": "Optional preferred callback preference",
                                },
                            },
                            "required": ["reason"],
                        },
                    },
                    {
                        "name": "send_sms",
                        "description": "Send an SMS to the patient with callback information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "message_type": {
                                    "type": "string",
                                    "description": "Type of message to send",
                                    "enum": ["callback_info", "appointment_reminder"],
                                }
                            },
                            "required": ["message_type"],
                        },
                    },
                ]
            }
        ]

        setup = {
            "setup": {
                "model": f"models/{GEMINI_MODEL}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self._voice,
                            }
                        }
                    },
                },
                "systemInstruction": {
                    "parts": [{"text": instructions}]
                },
                "tools": tools,
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
            }
        }

        await self._send(setup)

    async def _listen(self):
        """Listen for messages from Gemini."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    try:
                        message = message.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                await self._handle_message(message)
            print(f"[GeminiVoice] WebSocket closed normally")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[GeminiVoice] WebSocket closed: code={e.code}, reason={e.reason}")
        except Exception as e:
            print(f"[GeminiVoice] Listen error: {type(e).__name__}: {e}")
            if self.on_error:
                await self.on_error(f"Listen error: {str(e)}")
        finally:
            if self._session:
                self._session.is_active = False
            if self.on_session_ended:
                await self.on_session_ended()

    async def _handle_message(self, message: str):
        """Handle incoming message from Gemini."""
        try:
            data = json.loads(message)

            if self._verbose:
                keys = list(data.keys())
                print(f"[GeminiVoice] Received: {keys}")

            # Setup complete
            if "setupComplete" in data or "setup_complete" in data:
                print(f"[GeminiVoice] Setup complete")
                return

            # Server content (audio, text, turn complete)
            server_content = data.get("serverContent") or data.get("server_content")
            if server_content:
                await self._handle_server_content(server_content)
                return

            # Tool call
            tool_call = data.get("toolCall") or data.get("tool_call")
            if tool_call:
                await self._handle_tool_call(tool_call)
                return

            # Tool call cancellation
            if "toolCallCancellation" in data or "tool_call_cancellation" in data:
                if self._verbose:
                    print(f"[GeminiVoice] Tool call cancelled")
                return

            # Go away (server disconnect signal)
            if "goAway" in data or "go_away" in data:
                print(f"[GeminiVoice] Server sent goAway")
                if self.on_session_ended:
                    await self.on_session_ended()
                return

        except json.JSONDecodeError:
            pass
        except Exception as e:
            if self.on_error:
                await self.on_error(f"Message handling error: {str(e)}")

    async def _handle_server_content(self, content: dict):
        """Handle serverContent messages (audio, transcript, turn complete)."""
        model_turn = content.get("modelTurn") or content.get("model_turn")
        if model_turn:
            for part in model_turn.get("parts", []):
                # Audio output (24kHz PCM16 from Gemini)
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data:
                    audio_b64 = inline_data.get("data", "")
                    if audio_b64 and self.on_audio:
                        pcm24k = base64.b64decode(audio_b64)
                        if self._audio_format == "g711_ulaw":
                            # Downsample 24kHz → 8kHz, then encode to mulaw
                            audio_out = self._pcm24k_to_mulaw(pcm24k)
                        else:
                            audio_out = pcm24k
                        await self.on_audio(audio_out)

                # Text output (if any)
                text = part.get("text")
                if text and self.on_transcript:
                    await self.on_transcript("ai", text)

        # Output audio transcription — final text of what the AI said.
        # Must use "ai_complete" (not "ai") so the orchestrator persists it
        # to the call log. "ai" is treated as a streaming delta.
        output_transcription = content.get("outputTranscription") or content.get("output_transcription")
        if output_transcription:
            text = output_transcription.get("text", "")
            if text and self.on_transcript:
                await self.on_transcript("ai_complete", text)

        # Input (patient) transcription
        input_transcription = content.get("inputTranscription") or content.get("input_transcription")
        if input_transcription:
            text = input_transcription.get("text", "")
            if text and text.strip() and self.on_transcript:
                await self.on_transcript("patient", text.strip())

    async def _handle_tool_call(self, tool_call: dict):
        """Handle function calls from Gemini."""
        function_calls = tool_call.get("functionCalls") or tool_call.get("function_calls") or []
        for fc in function_calls:
            name = fc.get("name", "")
            args = fc.get("args", {})
            # args can be a JSON string in some cases
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            call_id = fc.get("id", "")
            if self.on_function_call:
                await self.on_function_call(name, args, call_id)

    # -- Audio transcoding (Twilio mulaw ↔ Gemini PCM) -------------------------

    def _mulaw_to_pcm16k(self, mulaw_data: bytes) -> bytes:
        """Convert 8kHz mulaw (from Twilio) to 16kHz PCM16 (for Gemini input)."""
        # Decode mulaw to 16-bit PCM at 8kHz
        pcm8k = audioop.ulaw2lin(mulaw_data, 2)
        # Upsample 8kHz → 16kHz
        pcm16k, self._inbound_state = audioop.ratecv(
            pcm8k, 2, 1, 8000, 16000, self._inbound_state
        )
        return pcm16k

    def _pcm24k_to_mulaw(self, pcm24k: bytes) -> bytes:
        """Convert 24kHz PCM16 (from Gemini output) to 8kHz mulaw (for Twilio)."""
        # Downsample 24kHz → 8kHz
        pcm8k, self._outbound_state = audioop.ratecv(
            pcm24k, 2, 1, 24000, 8000, self._outbound_state
        )
        # Encode to mulaw
        return audioop.lin2ulaw(pcm8k, 2)

    # -- Public interface -------------------------------------------------------

    async def _send(self, data: dict):
        """Send a message to Gemini."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to Gemini.

        In Twilio mode (g711_ulaw), transcodes mulaw 8kHz → PCM 16kHz.
        In web mode (pcm16), sends PCM at 16kHz.
        """
        if not self._ws or not self._session or not self._session.is_active:
            return

        if self._audio_format == "g711_ulaw":
            # Transcode mulaw → PCM 16kHz for Gemini
            pcm16k = self._mulaw_to_pcm16k(audio_data)
            audio_b64 = base64.b64encode(pcm16k).decode("utf-8")
        else:
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        await self._send({
            "realtimeInput": {
                "audio": {
                    "mimeType": "audio/pcm;rate=16000",
                    "data": audio_b64,
                }
            }
        })

    async def send_function_result(self, call_id: str, result: dict) -> None:
        """Send function call result back to Gemini."""
        if self._ws:
            await self._send({
                "toolResponse": {
                    "functionResponses": [
                        {
                            "id": call_id,
                            "response": {
                                "output": json.dumps(result),
                            },
                        }
                    ]
                }
            })

    async def start_conversation(self) -> None:
        """Start the conversation with AI greeting.

        Uses realtimeInput.text (not clientContent) to trigger Gemini to speak.
        """
        if not self._ws:
            return

        patient_name = self._session.patient_name if self._session else "there"
        first_name = patient_name.split()[0] if patient_name else "there"

        await self._send({
            "realtimeInput": {
                "text": f"[System: The call has just connected. The patient's name is {first_name}. Please greet them and begin the call.]"
            }
        })

    async def inject_system_message(self, text: str) -> None:
        """Inject a system-level text message into the active conversation.

        Uses realtimeInput.text — clientContent.turns is rejected by
        gemini-3.1-flash-live-preview with 'invalid argument'.
        """
        if not self._ws:
            return
        await self._send({"realtimeInput": {"text": text}})

    async def disconnect(self) -> None:
        """Disconnect from Gemini."""
        if self._session:
            self._session.is_active = False

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self.on_session_ended:
            await self.on_session_ended()

    @property
    def is_connected(self) -> bool:
        """Check if connected to Gemini."""
        return self._ws is not None and self._session is not None and self._session.is_active
