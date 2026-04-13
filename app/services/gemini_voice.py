"""Google Gemini Live API voice service."""
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
from app.services.realtime_voice import SYSTEM_INSTRUCTIONS

# Ensure .env is loaded
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=str(_env_path))


GEMINI_MODEL = os.getenv("GEMINI_REALTIME_MODEL", "gemini-2.0-flash-live-001")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Aoede")


@dataclass
class GeminiSession:
    """Active Gemini voice session state."""
    session_id: str
    call_id: str
    patient_name: str
    is_active: bool = True


class GeminiVoiceService(BaseVoiceService):
    """Manages Google Gemini Live API connections for voice calls."""

    def __init__(self, audio_format: str = "pcm16", verbose: bool = False):
        super().__init__(audio_format=audio_format, verbose=verbose)
        self._ws = None
        self._session: Optional[GeminiSession] = None
        self._api_key = os.getenv("GEMINI_API_KEY", "")

    @staticmethod
    def _language_instruction(language: Optional[str]) -> str:
        """Reuse OpenAI's language instruction logic."""
        from app.services.realtime_voice import RealtimeVoiceService
        return RealtimeVoiceService._language_instruction(language)

    async def connect(self, call_id: str, patient_name: str, patient_language: str = "en") -> bool:
        """Connect to Gemini Live API and start a session."""
        if not self._api_key:
            error_msg = "GEMINI_API_KEY not set in environment"
            print(f"[GeminiVoice] Error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
            return False

        try:
            url = (
                f"wss://generativelanguage.googleapis.com/ws/"
                f"google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
                f"?key={self._api_key}"
            )

            print(f"[GeminiVoice] Connecting to Gemini Live API...")
            self._ws = await websockets.connect(url)
            print(f"[GeminiVoice] WebSocket connected successfully")

            self._session = GeminiSession(
                session_id="",
                call_id=call_id,
                patient_name=patient_name,
            )

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
        instructions = f"{SYSTEM_INSTRUCTIONS}\n\n{language_instruction}"

        # Gemini audio format mapping
        if self._audio_format == "g711_ulaw":
            input_format = "MULAW"
            output_format = "MULAW"
            sample_rate = 8000
        else:
            input_format = "PCM"
            output_format = "PCM"
            sample_rate = 24000

        # Tools in Gemini format
        tools = [
            {
                "functionDeclarations": [
                    {
                        "name": "check_transfer_availability",
                        "description": "Check whether a scheduler is available to take a transfer right now.",
                        "parameters": {"type": "OBJECT", "properties": {}},
                    },
                    {
                        "name": "transfer_to_scheduler",
                        "description": "Transfer the patient to a human scheduler only after explicit consent.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "confirmed": {
                                    "type": "BOOLEAN",
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
                            "type": "OBJECT",
                            "properties": {
                                "reason": {
                                    "type": "STRING",
                                    "description": "The reason for ending the call",
                                    "enum": ["patient_busy", "wrong_number", "voicemail", "completed", "patient_request"],
                                },
                                "callback_requested": {
                                    "type": "BOOLEAN",
                                    "description": "Whether the patient requested a callback",
                                },
                                "preferred_callback_time": {
                                    "type": "STRING",
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
                            "type": "OBJECT",
                            "properties": {
                                "message_type": {
                                    "type": "STRING",
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
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": GEMINI_VOICE,
                            }
                        }
                    },
                    "responseModalities": ["AUDIO"],
                },
                "systemInstruction": {
                    "parts": [{"text": instructions}]
                },
                "tools": tools,
                "realtimeInputConfig": {
                    "automaticActivityDetection": {
                        "disabled": False,
                    },
                    "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
                    "mediaResolution": "MEDIA_RESOLUTION_LOW",
                },
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
                await self._handle_message(message)
            print(f"[GeminiVoice] WebSocket closed normally")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[GeminiVoice] WebSocket closed: code={e.code}, reason={e.reason}")
            if self.on_session_ended:
                await self.on_session_ended()
        except Exception as e:
            print(f"[GeminiVoice] Listen error: {type(e).__name__}: {e}")
            if self.on_error:
                await self.on_error(f"Listen error: {str(e)}")

    async def _handle_message(self, message: str):
        """Handle incoming message from Gemini."""
        try:
            data = json.loads(message)

            if self._verbose:
                keys = list(data.keys())
                print(f"[GeminiVoice] Received: {keys}")

            # Setup complete
            if "setupComplete" in data:
                print(f"[GeminiVoice] Setup complete")
                return

            # Server content (audio, text, turn complete)
            server_content = data.get("serverContent")
            if server_content:
                await self._handle_server_content(server_content)
                return

            # Tool call
            tool_call = data.get("toolCall")
            if tool_call:
                await self._handle_tool_call(tool_call)
                return

            # Tool call cancellation
            if "toolCallCancellation" in data:
                if self._verbose:
                    print(f"[GeminiVoice] Tool call cancelled")
                return

        except json.JSONDecodeError:
            pass
        except Exception as e:
            if self.on_error:
                await self.on_error(f"Message handling error: {str(e)}")

    async def _handle_server_content(self, content: dict):
        """Handle serverContent messages (audio, transcript, turn complete)."""
        model_turn = content.get("modelTurn")
        if model_turn:
            for part in model_turn.get("parts", []):
                # Audio output
                inline_data = part.get("inlineData")
                if inline_data:
                    audio_b64 = inline_data.get("data", "")
                    if audio_b64 and self.on_audio:
                        audio_bytes = base64.b64decode(audio_b64)
                        await self.on_audio(audio_bytes)

                # Text output (if any)
                text = part.get("text")
                if text and self.on_transcript:
                    await self.on_transcript("ai", text)

        # Output audio transcription
        output_transcription = content.get("outputTranscription")
        if output_transcription:
            text = output_transcription.get("text", "")
            if text and self.on_transcript:
                await self.on_transcript("ai", text)

        # Input (patient) transcription
        input_transcription = content.get("inputTranscription")
        if input_transcription:
            text = input_transcription.get("text", "")
            if text and text.strip() and self.on_transcript:
                await self.on_transcript("patient", text.strip())

        # Turn complete
        if content.get("turnComplete"):
            # Gemini signals turn is done; could trigger transcript finalization
            pass

    async def _handle_tool_call(self, tool_call: dict):
        """Handle function calls from Gemini."""
        function_calls = tool_call.get("functionCalls", [])
        for fc in function_calls:
            name = fc.get("name", "")
            args = fc.get("args", {})
            call_id = fc.get("id", "")
            if self.on_function_call:
                await self.on_function_call(name, args, call_id)

    async def _send(self, data: dict):
        """Send a message to Gemini."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to Gemini."""
        if not self._ws or not self._session or not self._session.is_active:
            return

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        if self._audio_format == "g711_ulaw":
            mime_type = "audio/pcmu"
        else:
            mime_type = "audio/pcm;rate=24000"

        await self._send({
            "realtimeInput": {
                "mediaChunks": [
                    {
                        "mimeType": mime_type,
                        "data": audio_b64,
                    }
                ]
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
                            "name": "",  # Gemini infers from id
                            "response": result,
                        }
                    ]
                }
            })

    async def start_conversation(self) -> None:
        """Start the conversation with AI greeting."""
        if not self._ws:
            return

        patient_name = self._session.patient_name if self._session else "there"
        first_name = patient_name.split()[0] if patient_name else "there"

        # Send a text message to trigger the greeting
        await self._send({
            "clientContent": {
                "turns": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": f"[System: The call has just connected. The patient's name is {first_name}. Please greet them and begin the call.]"
                            }
                        ],
                    }
                ],
                "turnComplete": True,
            }
        })

    async def disconnect(self) -> None:
        """Disconnect from Gemini."""
        if self._session:
            self._session.is_active = False

        if self._ws:
            await self._ws.close()
            self._ws = None

        if self.on_session_ended:
            await self.on_session_ended()

    @property
    def is_connected(self) -> bool:
        """Check if connected to Gemini."""
        return self._ws is not None and self._session is not None and self._session.is_active
