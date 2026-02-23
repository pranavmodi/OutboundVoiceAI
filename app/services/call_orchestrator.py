"""Call orchestrator service managing the call lifecycle."""
import asyncio
import json
import logging
import os
import re
from typing import Optional, Callable, Any
from datetime import datetime

from app.models import CallLog, CallOutcome, Patient
from app.providers import get_queue_provider, get_patient_provider, get_call_log_provider, get_settings_provider
from app.services.realtime_voice import RealtimeVoiceService
from app.services.email_notification_service import (
    send_wrong_number_email,
    send_disconnected_number_email,
)
from app.services.twilio_sms_service import (
    build_sms_message,
    send_sms,
    get_callback_number,
    is_number_opted_out,
    is_twilio_opt_out_error,
)

logger = logging.getLogger(__name__)


class CallOrchestrator:
    """Orchestrates outbound calls with OpenAI Realtime voice."""

    def __init__(self):
        self._voice_service: Optional[RealtimeVoiceService] = None
        self._current_call: Optional[CallLog] = None
        self._current_patient: Optional[Patient] = None
        self._twilio_bridge = None  # TwilioMediaBridge when in twilio mode
        self._call_mode: str = "web"  # "web" or "twilio"
        # SMS idempotency guards keyed by call_id.
        self._sms_sent_call_ids: set[str] = set()
        self._sms_locks: dict[str, asyncio.Lock] = {}
        self._email_sent_call_ids: set[str] = set()
        self._twilio_call_sid: Optional[str] = None
        self._voicemail_handled: bool = False
        self._web_voicemail_simulated: bool = False

        # Callbacks for UI updates
        self.on_call_started: Optional[Callable[[CallLog], Any]] = None
        self.on_call_ended: Optional[Callable[[CallLog], Any]] = None
        self.on_transcript_update: Optional[Callable[[str, str], Any]] = None
        self.on_audio_output: Optional[Callable[[bytes], Any]] = None
        self.on_status_update: Optional[Callable[[str], Any]] = None
        self.on_error: Optional[Callable[[str], Any]] = None

    async def _has_sms_been_sent(self, call_id: str) -> bool:
        """Check persisted call state to avoid duplicate SMS sends."""
        call_log_provider = get_call_log_provider()
        row = await call_log_provider.get_call(call_id)
        return bool(row and row.sms_sent)

    async def _send_sms_for_call(
        self,
        call: CallLog,
        patient: Optional[Patient],
        message_type: str = "callback_info",
        reason: str = "manual",
        call_mode: Optional[str] = None,
    ) -> bool:
        """Send SMS for a call and update call log/status."""
        if not patient or not patient.phone:
            await self._log_call_event(call.call_id, f"SMS skipped ({reason}): patient phone unavailable")
            if self.on_status_update:
                await self.on_status_update(f"SMS failed ({reason}): patient phone unavailable")
            return False

        lock = self._sms_locks.setdefault(call.call_id, asyncio.Lock())
        async with lock:
            # Fast in-memory checks first for repeated tool calls in the same process/session.
            if call.sms_sent or call.call_id in self._sms_sent_call_ids:
                await self._log_call_event(call.call_id, f"SMS skipped ({reason}): already sent")
                if self.on_status_update:
                    await self.on_status_update(f"SMS already sent for call {call.call_id[:8]}")
                return True

            # Persisted fallback check.
            if await self._has_sms_been_sent(call.call_id):
                call.sms_sent = True
                self._sms_sent_call_ids.add(call.call_id)
                await self._log_call_event(call.call_id, f"SMS skipped ({reason}): already sent")
                if self.on_status_update:
                    await self.on_status_update(f"SMS already sent for call {call.call_id[:8]}")
                return True

            mode = call_mode or self._call_mode or "web"
            call_log_provider = get_call_log_provider()
            if is_number_opted_out(patient.phone):
                await self._log_call_event(
                    call.call_id,
                    f"SMS blocked ({reason}): recipient opted out [{patient.phone}]",
                )
                if self.on_status_update:
                    await self.on_status_update(f"SMS blocked ({reason}): recipient opted out")
                return False

            # In web/browser mode, simulate SMS delivery (no external Twilio send).
            if mode == "web":
                await call_log_provider.update_call(call.call_id, sms_sent=True)
                call.sms_sent = True
                self._sms_sent_call_ids.add(call.call_id)
                await self._log_call_event(
                    call.call_id,
                    f"SMS delivered ({reason}) mode=web simulated=true to={patient.phone}",
                )
                if self.on_status_update:
                    await self.on_status_update(
                        f"SMS sent ({reason}) in web mode (simulated) to {patient.phone}"
                    )
                return True

            body = build_sms_message(message_type)
            try:
                sid = await asyncio.to_thread(send_sms, patient.phone, body)
                await call_log_provider.update_call(call.call_id, sms_sent=True)
                call.sms_sent = True
                self._sms_sent_call_ids.add(call.call_id)
                await self._log_call_event(
                    call.call_id,
                    f"SMS delivered ({reason}) mode=twilio sid={sid} to={patient.phone}",
                )
                if self.on_status_update:
                    await self.on_status_update(
                        f"SMS sent ({reason}) in twilio mode to {patient.phone} [sid={sid}]"
                    )
                return True
            except Exception as e:
                logger.warning("SMS send failed for call %s: %s", call.call_id, e)
                if is_twilio_opt_out_error(e):
                    await self._log_call_event(
                        call.call_id,
                        f"SMS blocked ({reason}): Twilio recipient opt-out to={patient.phone}",
                    )
                    if self.on_status_update:
                        await self.on_status_update(f"SMS blocked ({reason}): recipient opted out")
                    return False
                await self._log_call_event(call.call_id, f"SMS failed ({reason}): {str(e)}")
                if self.on_status_update:
                    await self.on_status_update(f"SMS failed ({reason}): {str(e)}")
                return False

    async def _log_call_event(self, call_id: str, message: str):
        """Persist non-audio operational events to the call transcript."""
        call_log_provider = get_call_log_provider()
        await call_log_provider.add_transcript(call_id, "system", message)

    @staticmethod
    def _looks_like_disconnected_or_invalid(error_text: str) -> bool:
        text = (error_text or "").lower()
        keywords = (
            "disconnected",
            "invalid",
            "not in service",
            "unreachable",
            "failed to route",
            "does not exist",
            "cannot be completed",
        )
        return any(k in text for k in keywords)

    @staticmethod
    def _parse_int_or_none(value: str) -> Optional[int]:
        try:
            return int(str(value).strip())
        except Exception:
            return None

    @staticmethod
    def _map_twilio_failure_reason(
        call_status: str,
        error_code: Optional[int],
        sip_response_code: Optional[int],
    ) -> str:
        code_map = {
            32009: "invalid number",
            32005: "disconnected/unreachable number",
        }
        if error_code in code_map:
            detail = code_map[error_code]
        elif error_code is not None and 32000 <= error_code <= 32999:
            detail = "carrier failure"
        else:
            detail = "call failed"

        parts = [f"Twilio {call_status}", detail]
        if error_code is not None:
            parts.append(f"error_code={error_code}")
        if sip_response_code is not None:
            parts.append(f"sip_response_code={sip_response_code}")
        return " | ".join(parts)

    @staticmethod
    def _is_carrier_failure(
        call_status: str,
        error_code: Optional[int],
        sip_response_code: Optional[int],
    ) -> bool:
        status = (call_status or "").strip().lower()
        if status == "failed":
            return True
        if status in {"busy", "no-answer"} and (error_code is not None or sip_response_code is not None):
            return True
        return False

    @staticmethod
    def _is_known_invalid_number_code(error_code: Optional[int]) -> bool:
        # Twilio known invalid/disconnected style codes
        return error_code in {32005, 32009}

    @staticmethod
    def _is_known_invalid_number_sip_code(sip_response_code: Optional[int]) -> bool:
        # Common SIP responses that indicate invalid/unroutable numbers.
        return sip_response_code in {404, 410, 484, 604}

    @classmethod
    def _should_flag_invalid_number(
        cls,
        error_code: Optional[int],
        sip_response_code: Optional[int],
        reason_text: str,
    ) -> bool:
        if cls._is_known_invalid_number_code(error_code):
            return True
        if cls._is_known_invalid_number_sip_code(sip_response_code):
            return True
        return cls._looks_like_disconnected_or_invalid(reason_text)

    @staticmethod
    def _looks_like_wrong_number_signal(text: str) -> bool:
        """Best-effort detection of wrong-number intent in patient utterances."""
        lowered = (text or "").lower()
        if "wrong number" in lowered or "wrong person" in lowered:
            return True
        patterns = (
            r"\bnot me\b",
            r"\bthis is(?:n't| not) [a-z]+\b",
            r"\byou have the wrong\b",
            r"\bno one (?:by|with) (?:that|this) name\b",
            r"\bdon'?t know (?:who|them|that person)\b",
        )
        return any(re.search(p, lowered) for p in patterns)

    @staticmethod
    def _looks_like_voicemail_signal(text: str) -> bool:
        """Detect voicemail-like phrases in web-mode simulated patient speech."""
        lowered = (text or "").lower()
        phrases = (
            "leave a message",
            "at the tone",
            "after the beep",
            "cannot take your call",
            "not available right now",
            "i'm not available",
            "im not available",
            "please leave your name",
            "leave your name",
            "leave your number",
            "leave your name and number",
            "voice mail",
            "voicemail",
        )
        if any(p in lowered for p in phrases):
            return True
        # Broader fallback for variants like "leave your number and name".
        return "leave your" in lowered and ("name" in lowered or "number" in lowered)

    @staticmethod
    def _normalize_language_code(language: Optional[object]) -> str:
        if language is None:
            return "en"
        value = getattr(language, "value", language)
        normalized = str(value).strip().lower()
        return normalized or "en"

    @staticmethod
    def _load_json_object_env(var_name: str) -> dict[str, str]:
        raw = os.getenv(var_name, "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {
                    str(k).strip().lower(): str(v).strip()
                    for k, v in parsed.items()
                    if str(v).strip()
                }
        except Exception:
            logger.warning("Invalid JSON in %s; expected an object map", var_name)
        return {}

    @classmethod
    def _resolve_transfer_queue_for_language(cls, language: Optional[object]) -> str:
        language_code = cls._normalize_language_code(language)

        default_map = {
            "en": "scheduling_en",
            "es": "scheduling_es",
            # Default non-mapped languages to English queue.
            "zh": "scheduling_en",
        }
        configured_map = cls._load_json_object_env("LANGUAGE_QUEUE_MAP")
        mapping = {**default_map, **configured_map}
        return mapping.get(language_code) or mapping.get("en", "scheduling_en")

    @classmethod
    def _resolve_transfer_destination_for_queue(cls, queue_name: str) -> Optional[str]:
        configured_targets = cls._load_json_object_env("QUEUE_TRANSFER_TARGETS")
        if queue_name in configured_targets:
            return configured_targets[queue_name]
        # Optional per-queue environment override, e.g. TRANSFER_TARGET_SCHEDULING_EN.
        env_name = f"TRANSFER_TARGET_{queue_name.upper()}"
        value = os.getenv(env_name, "").strip()
        if value:
            return value
        return None

    @staticmethod
    def _find_queue_by_name(queue_state, queue_name: str):
        for queue in queue_state.queues:
            if (queue.Queue or "").strip().lower() == queue_name.strip().lower():
                return queue
        return None

    async def _recent_patient_indicates_wrong_number(self, call_id: str) -> bool:
        """Inspect recent patient transcript lines for wrong-number cues."""
        call_log_provider = get_call_log_provider()
        row = await call_log_provider.get_call(call_id)
        if not row or not row.transcript:
            return False
        recent = row.transcript[-8:]
        for entry in recent:
            if entry.speaker == "patient" and self._looks_like_wrong_number_signal(entry.text):
                return True
        return False

    async def _maybe_send_issue_email(self, call: CallLog, outcome: CallOutcome):
        """Send required call-issue email notifications based on outcome/status."""
        if call.call_id in self._email_sent_call_ids:
            return

        status_text = call.error_message or outcome.value

        try:
            if outcome == CallOutcome.WRONG_NUMBER:
                message_id = await asyncio.to_thread(send_wrong_number_email, call)
                self._email_sent_call_ids.add(call.call_id)
                await self._log_call_event(call.call_id, f"Email sent (wrong_number) [message_id={message_id or 'n/a'}]")
                if self.on_status_update:
                    await self.on_status_update("Email sent (wrong_number) to scheduling team")
                return

            if outcome == CallOutcome.DISCONNECTED or (
                outcome == CallOutcome.FAILED and self._looks_like_disconnected_or_invalid(status_text)
            ):
                message_id = await asyncio.to_thread(send_disconnected_number_email, call, status_text)
                self._email_sent_call_ids.add(call.call_id)
                await self._log_call_event(
                    call.call_id,
                    f"Email sent (invalid_disconnected) [message_id={message_id or 'n/a'}] status={status_text}",
                )
                if self.on_status_update:
                    await self.on_status_update("Email sent (invalid/disconnected) to scheduling team")
        except Exception as e:
            await self._log_call_event(call.call_id, f"Email failed: {str(e)}")
            if self.on_status_update:
                await self.on_status_update(f"Email failed: {str(e)}")

    async def handle_twilio_amd_status(self, call_sid: str, answered_by: str):
        """Handle Twilio AMD callback values (machine/human)."""
        if not self._current_call or not call_sid or call_sid != self._twilio_call_sid:
            return
        if self._voicemail_handled:
            return

        normalized = (answered_by or "").strip().lower()
        if not normalized:
            return

        if normalized.startswith("human"):
            if self.on_status_update:
                await self.on_status_update("Twilio AMD: human detected")
            return

        if normalized.startswith("machine"):
            self._voicemail_handled = True
            call = self._current_call
            call_log_provider = get_call_log_provider()
            await call_log_provider.update_call(call.call_id, voicemail_left=True)
            call.voicemail_left = True
            if self.on_status_update:
                await self.on_status_update(f"Twilio AMD: voicemail detected ({answered_by})")

            callback_number = get_callback_number().strip()
            if callback_number:
                message = (
                    "Hi, this is a call from Precise Imaging regarding scheduling. "
                    f"Please call us back at {callback_number}."
                )
            else:
                message = (
                    "Hi, this is a call from Precise Imaging regarding scheduling. "
                    "Please call us back at the number previously provided."
                )

            try:
                from app.services.twilio_voice_service import play_voicemail_and_hangup
                await asyncio.to_thread(play_voicemail_and_hangup, call_sid, message)
            except Exception as e:
                logger.warning("Failed to play voicemail for call %s: %s", call.call_id, e)
                if self.on_status_update:
                    await self.on_status_update(f"Voicemail playback failed: {str(e)}")

            await self.end_call(CallOutcome.VOICEMAIL)

    async def handle_twilio_call_status(
        self,
        call_sid: str,
        call_status: str,
        error_code_raw: str = "",
        sip_response_code_raw: str = "",
    ):
        """Handle Twilio failed/busy/no-answer callback statuses with carrier code mapping."""
        if not self._current_call or not call_sid or call_sid != self._twilio_call_sid:
            return

        error_code = self._parse_int_or_none(error_code_raw)
        sip_response_code = self._parse_int_or_none(sip_response_code_raw)
        status = (call_status or "").strip().lower()
        if not status:
            return
        if not self._is_carrier_failure(status, error_code, sip_response_code):
            return

        reason = self._map_twilio_failure_reason(status, error_code, sip_response_code)
        code_str = str(error_code) if error_code is not None else f"twilio_{status}"

        call_log_provider = get_call_log_provider()
        await call_log_provider.update_call(
            self._current_call.call_id,
            error_code=code_str,
            error_message=reason,
        )
        self._current_call.error_code = code_str
        self._current_call.error_message = reason
        await self._log_call_event(self._current_call.call_id, f"Carrier failure detected: {reason}")

        if self._should_flag_invalid_number(error_code, sip_response_code, reason) and self._current_patient:
            patient_provider = get_patient_provider()
            await patient_provider.mark_patient_invalid_number(self._current_patient.patient_id, reason)
            await self._log_call_event(
                self._current_call.call_id,
                f"Patient flagged invalid_number (no retry): {reason}",
            )
            if self.on_status_update:
                await self.on_status_update("Patient flagged as invalid/disconnected number (no retry)")

        if self.on_status_update:
            await self.on_status_update(f"Twilio carrier failure: {reason}")
        await self.end_call(CallOutcome.FAILED)

    async def start_call(self, patient_id: str, call_mode: str = "web") -> Optional[CallLog]:
        """Start an outbound call to a patient."""
        # Check if call already in progress
        call_log_provider = get_call_log_provider()
        if call_log_provider.has_active_call():
            if self.on_error:
                await self.on_error("A call is already in progress")
            return None

        # Get patient
        patient_provider = get_patient_provider()
        patient = await patient_provider.get_patient(patient_id)

        # Debug: log all patients in the queue
        all_patients = await patient_provider.get_all_patients()
        print(f"[START_CALL] Looking for patient_id={patient_id}")
        print(f"[START_CALL] All patients in PatientRow table ({len(all_patients)}):")
        for p in all_patients:
            print(f"[START_CALL]   - {p.patient_id}: {p.name}, {p.phone}")

        if not patient:
            if self.on_error:
                await self.on_error(f"Patient {patient_id} not found")
            return None

        print(f"[START_CALL] Found patient: {patient.name}, phone={patient.phone}")

        # Check queue state
        queue_provider = get_queue_provider()
        queue_state = queue_provider.get_state()

        # Create call log
        call = await call_log_provider.create_call(
            patient_id=patient.patient_id,
            patient_name=patient.name,
            phone=patient.phone,
            order_id=patient.order_id,
            priority_bucket=patient.priority_bucket,
            queue_snapshot=queue_state.to_dict(),
        )

        self._current_call = call
        self._current_patient = patient
        self._call_mode = call_mode
        self._web_voicemail_simulated = False

        if self.on_status_update:
            mode_label = "Twilio" if call_mode == "twilio" else "Web"
            await self.on_status_update(f"Connecting ({mode_label})...")

        # Choose audio format based on mode
        audio_format = "g711_ulaw" if call_mode == "twilio" else "pcm16"

        # Initialize voice service
        self._voice_service = RealtimeVoiceService(audio_format=audio_format)
        self._voice_service.on_transcript = self._handle_transcript
        self._voice_service.on_audio = self._handle_audio
        self._voice_service.on_function_call = self._handle_function_call
        self._voice_service.on_error = self._handle_voice_error
        self._voice_service.on_session_ended = self._handle_session_ended

        # Connect to OpenAI
        success = await self._voice_service.connect(
            call.call_id,
            patient.name,
            self._normalize_language_code(patient.language),
        )
        if not success:
            await call_log_provider.end_call(call.call_id, CallOutcome.FAILED)
            self._voice_service = None
            self._current_call = None
            self._current_patient = None
            return None

        # In Twilio mode, check safeguards then place the actual phone call
        if call_mode == "twilio":
            # Safeguard: check DB-level allow_live_calls setting
            settings_provider = get_settings_provider()
            settings = await settings_provider.get_settings()
            if not settings.allow_live_calls:
                error_msg = "Live calls are disabled in system settings. Enable 'Allow Live Calls' first."
                logger.warning(f"Twilio call blocked: {error_msg}")
                if self.on_error:
                    await self.on_error(error_msg)
                await call_log_provider.end_call(call.call_id, CallOutcome.FAILED)
                await self._voice_service.disconnect()
                self._voice_service = None
                self._current_call = None
                self._current_patient = None
                return None

            # Safeguard: check phone number allowlist
            if not settings.allowed_phones:
                error_msg = "No phone numbers in allowlist. Add allowed numbers in settings first."
                logger.warning(f"Twilio call blocked: {error_msg}")
                if self.on_error:
                    await self.on_error(error_msg)
                await call_log_provider.end_call(call.call_id, CallOutcome.FAILED)
                await self._voice_service.disconnect()
                self._voice_service = None
                self._current_call = None
                self._current_patient = None
                return None

            # Normalize phone numbers for comparison (remove spaces, dashes, parentheses)
            def normalize_phone(p: str) -> str:
                return ''.join(c for c in p if c.isdigit() or c == '+')

            normalized_patient_phone = normalize_phone(patient.phone)
            normalized_allowlist = [normalize_phone(p) for p in settings.allowed_phones]

            if normalized_patient_phone not in normalized_allowlist:
                error_msg = f"Phone number {patient.phone} is not in the allowlist."
                logger.warning(f"Twilio call blocked: {error_msg}")
                if self.on_error:
                    await self.on_error(error_msg)
                await call_log_provider.end_call(call.call_id, CallOutcome.FAILED)
                await self._voice_service.disconnect()
                self._voice_service = None
                self._current_call = None
                self._current_patient = None
                return None

            try:
                from app.services.twilio_voice_service import (
                    TwilioMediaBridge,
                    place_twilio_call,
                    generate_stream_id,
                    register_bridge,
                )

                stream_id = generate_stream_id()
                bridge = TwilioMediaBridge(self._voice_service)
                register_bridge(stream_id, bridge)
                self._twilio_bridge = bridge

                # Build TwiML URL — the backend serves the TwiML
                backend_host = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
                if not backend_host:
                    # Fallback to CORS origin or localhost
                    backend_host = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
                twiml_url = f"{backend_host}/api/twilio/twiml/{stream_id}"

                if self.on_status_update:
                    await self.on_status_update(f"Calling {patient.phone} via Twilio...")

                status_callback_url = f"{backend_host}/api/twilio/status"
                call_sid = place_twilio_call(
                    to_number=patient.phone,
                    twiml_url=twiml_url,
                    status_callback_url=status_callback_url,
                )
                self._twilio_call_sid = call_sid
                self._voicemail_handled = False

            except Exception as e:
                logger.error(f"Failed to place Twilio call: {e}")
                if self.on_error:
                    await self.on_error(f"Twilio call failed: {str(e)}")
                await call_log_provider.end_call(call.call_id, CallOutcome.FAILED)
                await self._voice_service.disconnect()
                self._voice_service = None
                self._current_call = None
                self._current_patient = None
                self._twilio_bridge = None
                return None
        else:
            if self.on_status_update:
                await self.on_status_update("Connected - AI Speaking")

        if self.on_call_started:
            await self.on_call_started(call)

        # Start the conversation (AI greeting)
        await self._voice_service.start_conversation()

        return call

    async def end_call(self, outcome: CallOutcome = CallOutcome.COMPLETED):
        """End the current call."""
        if not self._current_call:
            return

        # Capture and clear references first to prevent re-entrant calls
        # (disconnect -> on_session_ended -> end_call again)
        call = self._current_call
        patient = self._current_patient
        voice_service = self._voice_service
        call_mode = self._call_mode

        try:
            # Required notifications for wrong number / disconnected outcomes.
            await self._maybe_send_issue_email(call, outcome)

            # Auto-send callback SMS for all non-transferred ended calls.
            if outcome != CallOutcome.TRANSFERRED:
                await self._send_sms_for_call(
                    call=call,
                    patient=patient,
                    message_type="callback_info",
                    reason="auto_end_not_transferred",
                    call_mode=call_mode,
                )

            self._current_call = None
            self._current_patient = None
            self._voice_service = None
            self._twilio_bridge = None

            call_log_provider = get_call_log_provider()
            await call_log_provider.end_call(call.call_id, outcome)

            # Update patient record
            if patient:
                patient_provider = get_patient_provider()
                await patient_provider.update_patient_after_call(
                    patient.patient_id,
                    outcome.value,
                )

            # Disconnect voice service
            if voice_service:
                await voice_service.disconnect()

            if self.on_call_ended:
                await self.on_call_ended(call)

            if self.on_status_update:
                await self.on_status_update("Call Ended")
        finally:
            self._sms_locks.pop(call.call_id, None)
            self._sms_sent_call_ids.discard(call.call_id)
            self._email_sent_call_ids.discard(call.call_id)
            self._twilio_call_sid = None
            self._voicemail_handled = False
            self._web_voicemail_simulated = False
            self._call_mode = "web"

    async def send_audio(self, audio_data: bytes):
        """Send audio from the patient (browser) to OpenAI."""
        if self._voice_service and self._voice_service.is_connected:
            await self._voice_service.send_audio(audio_data)

    async def _handle_transcript(self, speaker: str, text: str):
        """Handle transcript updates from voice service."""
        if not self._current_call:
            return

        call_log_provider = get_call_log_provider()

        # Only log complete transcripts
        if speaker == "ai_complete":
            await call_log_provider.add_transcript(self._current_call.call_id, "ai", text)
            if self.on_transcript_update:
                await self.on_transcript_update("ai", text)
        elif speaker == "patient":
            await call_log_provider.add_transcript(self._current_call.call_id, "patient", text)
            if self.on_transcript_update:
                await self.on_transcript_update("patient", text)
            # Web-mode simulation of voicemail detection (Feature 3 parity).
            if (
                self._call_mode == "web"
                and not self._web_voicemail_simulated
                and self._looks_like_voicemail_signal(text)
            ):
                self._web_voicemail_simulated = True
                await call_log_provider.update_call(self._current_call.call_id, voicemail_left=True)
                self._current_call.voicemail_left = True
                if self.on_status_update:
                    await self.on_status_update("Web simulation: voicemail detected from transcript")
                await self.end_call(CallOutcome.VOICEMAIL)
        elif speaker == "ai":
            # Streaming delta - just forward for real-time display
            if self.on_transcript_update:
                await self.on_transcript_update("ai_delta", text)

    async def _handle_audio(self, audio_data: bytes):
        """Handle audio output from voice service."""
        if self.on_audio_output:
            await self.on_audio_output(audio_data)

    async def _handle_function_call(self, name: str, args: dict):
        """Handle function calls from AI."""
        if not self._current_call:
            return

        call_log_provider = get_call_log_provider()

        if name == "transfer_to_scheduler":
            if args.get("confirmed"):
                # Check queue state before transfer
                queue_provider = get_queue_provider()
                queue_state = queue_provider.get_state()

                await call_log_provider.update_call(
                    self._current_call.call_id,
                    transfer_attempted=True,
                )

                if await self._recent_patient_indicates_wrong_number(self._current_call.call_id):
                    if self.on_status_update:
                        await self.on_status_update("Transfer canceled - possible wrong number detected")
                    await self.end_call(CallOutcome.WRONG_NUMBER)
                    return

                patient_language = self._normalize_language_code(
                    self._current_patient.language if self._current_patient else None
                )
                target_queue = self._resolve_transfer_queue_for_language(
                    self._current_patient.language if self._current_patient else None
                )
                queue_info = self._find_queue_by_name(queue_state, target_queue)

                if queue_info is None:
                    await self._log_call_event(
                        self._current_call.call_id,
                        f"Transfer blocked: target queue '{target_queue}' not found for language '{patient_language}'",
                    )
                    if self.on_status_update:
                        await self.on_status_update(
                            f"Transfer unavailable for language '{patient_language}' (queue not configured)"
                        )
                    await self._send_sms_for_call(
                        call=self._current_call,
                        patient=self._current_patient,
                        message_type="callback_info",
                        reason="transfer_queue_missing",
                        call_mode=self._call_mode,
                    )
                    await self.end_call(CallOutcome.CALLBACK_REQUESTED)
                    return

                queue_has_capacity = (
                    queue_state.outbound_allowed
                    and queue_info.AvailableAgents >= 1
                )
                if queue_has_capacity:
                    transfer_context = (
                        f"lang={patient_language} queue={target_queue} "
                        f"available_agents={queue_info.AvailableAgents}"
                    )
                    await self._log_call_event(
                        self._current_call.call_id,
                        f"Transfer target resolved: {transfer_context}",
                    )

                    if self._call_mode == "twilio":
                        destination = self._resolve_transfer_destination_for_queue(target_queue)
                        if not destination:
                            await self._log_call_event(
                                self._current_call.call_id,
                                f"Transfer blocked: no destination configured for queue '{target_queue}'",
                            )
                            if self.on_status_update:
                                await self.on_status_update(
                                    f"Transfer unavailable for queue '{target_queue}' (missing destination config)"
                                )
                            await self._send_sms_for_call(
                                call=self._current_call,
                                patient=self._current_patient,
                                message_type="callback_info",
                                reason="transfer_destination_missing",
                                call_mode=self._call_mode,
                            )
                            await self.end_call(CallOutcome.CALLBACK_REQUESTED)
                            return

                        if not self._twilio_call_sid:
                            await self._log_call_event(
                                self._current_call.call_id,
                                "Transfer blocked: active Twilio call SID unavailable",
                            )
                            if self.on_status_update:
                                await self.on_status_update("Transfer unavailable right now; callback SMS sent")
                            await self._send_sms_for_call(
                                call=self._current_call,
                                patient=self._current_patient,
                                message_type="callback_info",
                                reason="transfer_missing_twilio_sid",
                                call_mode=self._call_mode,
                            )
                            await self.end_call(CallOutcome.CALLBACK_REQUESTED)
                            return

                        try:
                            from app.services.twilio_voice_service import transfer_call_to_destination
                            await asyncio.to_thread(
                                transfer_call_to_destination,
                                self._twilio_call_sid,
                                destination,
                            )
                            await self._log_call_event(
                                self._current_call.call_id,
                                f"Twilio transfer initiated to queue '{target_queue}' destination='{destination}'",
                            )
                        except Exception as e:
                            await self._log_call_event(
                                self._current_call.call_id,
                                f"Transfer failed for queue '{target_queue}': {str(e)}",
                            )
                            if self.on_status_update:
                                await self.on_status_update(
                                    f"Transfer failed for queue '{target_queue}'; callback SMS sent"
                                )
                            await self._send_sms_for_call(
                                call=self._current_call,
                                patient=self._current_patient,
                                message_type="callback_info",
                                reason="transfer_failed",
                                call_mode=self._call_mode,
                            )
                            await self.end_call(CallOutcome.CALLBACK_REQUESTED)
                            return

                    # Transfer would succeed
                    await call_log_provider.update_call(
                        self._current_call.call_id,
                        transfer_success=True,
                    )
                    if self.on_status_update:
                        await self.on_status_update(
                            f"Transferring to scheduler queue '{target_queue}' ({patient_language})..."
                        )

                    # End call as transferred
                    await self.end_call(CallOutcome.TRANSFERRED)
                else:
                    # Transfer not safe
                    await self._log_call_event(
                        self._current_call.call_id,
                        (
                            f"Transfer unavailable: queue '{target_queue}' has no capacity "
                            f"(available_agents={queue_info.AvailableAgents}, "
                            f"outbound_allowed={queue_state.outbound_allowed})"
                        ),
                    )
                    if self.on_status_update:
                        await self.on_status_update("Transfer not available - target language queue busy")
                    await self._send_sms_for_call(
                        call=self._current_call,
                        patient=self._current_patient,
                        message_type="callback_info",
                        reason="transfer_queue_unavailable",
                        call_mode=self._call_mode,
                    )
                    await self.end_call(CallOutcome.CALLBACK_REQUESTED)

        elif name == "end_call":
            reason = args.get("reason", "completed")
            callback = args.get("callback_requested", False)

            outcome_map = {
                "patient_busy": CallOutcome.CALLBACK_REQUESTED,
                "wrong_number": CallOutcome.WRONG_NUMBER,
                "voicemail": CallOutcome.VOICEMAIL,
                "completed": CallOutcome.COMPLETED,
                "patient_request": CallOutcome.COMPLETED,
            }
            outcome = outcome_map.get(reason, CallOutcome.COMPLETED)

            if callback:
                outcome = CallOutcome.CALLBACK_REQUESTED

            await self.end_call(outcome)

        elif name == "send_sms":
            await self._send_sms_for_call(
                call=self._current_call,
                patient=self._current_patient,
                message_type=args.get("message_type", "callback_info"),
                reason="ai_tool",
                call_mode=self._call_mode,
            )

    async def _handle_voice_error(self, error: str):
        """Handle errors from voice service."""
        if self._current_call:
            call_log_provider = get_call_log_provider()
            await call_log_provider.update_call(
                self._current_call.call_id,
                error_code="voice_error",
                error_message=error,
            )
            self._current_call.error_code = "voice_error"
            self._current_call.error_message = error
        if self.on_error:
            await self.on_error(error)

    async def _handle_session_ended(self):
        """Handle voice session ending unexpectedly."""
        if self._current_call and self._current_call.outcome == CallOutcome.IN_PROGRESS:
            await self.end_call(CallOutcome.FAILED)

    @property
    def is_call_active(self) -> bool:
        """Check if a call is currently active."""
        return self._current_call is not None

    @property
    def current_call(self) -> Optional[CallLog]:
        """Get the current call."""
        return self._current_call


# Global instance
_orchestrator: Optional[CallOrchestrator] = None


def get_orchestrator() -> CallOrchestrator:
    """Get the global call orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = CallOrchestrator()
    return _orchestrator
