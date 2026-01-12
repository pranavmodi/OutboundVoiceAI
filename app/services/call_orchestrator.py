"""Call orchestrator service managing the call lifecycle."""
import asyncio
from typing import Optional, Callable, Any
from datetime import datetime

from app.models import CallLog, CallOutcome, Patient
from app.providers import get_queue_provider, get_patient_provider, get_call_log_provider
from app.services.realtime_voice import RealtimeVoiceService


class CallOrchestrator:
    """Orchestrates outbound calls with OpenAI Realtime voice."""

    def __init__(self):
        self._voice_service: Optional[RealtimeVoiceService] = None
        self._current_call: Optional[CallLog] = None
        self._current_patient: Optional[Patient] = None

        # Callbacks for UI updates
        self.on_call_started: Optional[Callable[[CallLog], Any]] = None
        self.on_call_ended: Optional[Callable[[CallLog], Any]] = None
        self.on_transcript_update: Optional[Callable[[str, str], Any]] = None
        self.on_audio_output: Optional[Callable[[bytes], Any]] = None
        self.on_status_update: Optional[Callable[[str], Any]] = None
        self.on_error: Optional[Callable[[str], Any]] = None

    async def start_call(self, patient_id: str) -> Optional[CallLog]:
        """Start an outbound call to a patient."""
        # Check if call already in progress
        call_log_provider = get_call_log_provider()
        if call_log_provider.has_active_call():
            if self.on_error:
                await self.on_error("A call is already in progress")
            return None

        # Get patient
        patient_provider = get_patient_provider()
        patient = patient_provider.get_patient(patient_id)
        if not patient:
            if self.on_error:
                await self.on_error(f"Patient {patient_id} not found")
            return None

        # Check queue state
        queue_provider = get_queue_provider()
        queue_state = queue_provider.get_state()

        # Create call log
        call = call_log_provider.create_call(
            patient_id=patient.patient_id,
            patient_name=patient.name,
            phone=patient.phone,
            order_id=patient.order_id,
            priority_bucket=patient.priority_bucket,
            queue_snapshot=queue_state.to_dict(),
        )

        self._current_call = call
        self._current_patient = patient

        if self.on_status_update:
            await self.on_status_update("Connecting...")

        # Initialize voice service
        self._voice_service = RealtimeVoiceService()
        self._voice_service.on_transcript = self._handle_transcript
        self._voice_service.on_audio = self._handle_audio
        self._voice_service.on_function_call = self._handle_function_call
        self._voice_service.on_error = self._handle_voice_error
        self._voice_service.on_session_ended = self._handle_session_ended

        # Connect to OpenAI
        success = await self._voice_service.connect(call.call_id, patient.name)
        if not success:
            call_log_provider.end_call(call.call_id, CallOutcome.FAILED)
            # Note: The actual error was already sent via on_error callback from voice service
            self._voice_service = None
            self._current_call = None
            self._current_patient = None
            return None

        if self.on_status_update:
            await self.on_status_update("Connected - AI Speaking")

        if self.on_call_started:
            await self.on_call_started(call)

        # Start the conversation
        await self._voice_service.start_conversation()

        return call

    async def end_call(self, outcome: CallOutcome = CallOutcome.COMPLETED):
        """End the current call."""
        if not self._current_call:
            return

        call_log_provider = get_call_log_provider()
        call_log_provider.end_call(self._current_call.call_id, outcome)

        # Update patient record
        if self._current_patient:
            patient_provider = get_patient_provider()
            patient_provider.update_patient_after_call(
                self._current_patient.patient_id,
                outcome.value,
            )

        # Disconnect voice service
        if self._voice_service:
            await self._voice_service.disconnect()
            self._voice_service = None

        if self.on_call_ended:
            await self.on_call_ended(self._current_call)

        if self.on_status_update:
            await self.on_status_update("Call Ended")

        self._current_call = None
        self._current_patient = None

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
            call_log_provider.add_transcript(self._current_call.call_id, "ai", text)
            if self.on_transcript_update:
                await self.on_transcript_update("ai", text)
        elif speaker == "patient":
            call_log_provider.add_transcript(self._current_call.call_id, "patient", text)
            if self.on_transcript_update:
                await self.on_transcript_update("patient", text)
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

                call_log_provider.update_call(
                    self._current_call.call_id,
                    transfer_attempted=True,
                )

                if queue_state.outbound_allowed and queue_state.global_agents_available >= 1:
                    # Transfer would succeed
                    call_log_provider.update_call(
                        self._current_call.call_id,
                        transfer_success=True,
                    )
                    if self.on_status_update:
                        await self.on_status_update("Transferring to scheduler...")

                    # End call as transferred
                    await self.end_call(CallOutcome.TRANSFERRED)
                else:
                    # Transfer not safe
                    if self.on_status_update:
                        await self.on_status_update("Transfer not available - queue busy")

        elif name == "end_call":
            reason = args.get("reason", "completed")
            callback = args.get("callback_requested", False)

            outcome_map = {
                "patient_busy": CallOutcome.CALLBACK_REQUESTED,
                "wrong_number": CallOutcome.WRONG_NUMBER,
                "completed": CallOutcome.COMPLETED,
                "patient_request": CallOutcome.COMPLETED,
            }
            outcome = outcome_map.get(reason, CallOutcome.COMPLETED)

            if callback:
                outcome = CallOutcome.CALLBACK_REQUESTED

            await self.end_call(outcome)

        elif name == "send_sms":
            call_log_provider.update_call(
                self._current_call.call_id,
                sms_sent=True,
            )
            if self.on_status_update:
                await self.on_status_update("SMS sent to patient")

    async def _handle_voice_error(self, error: str):
        """Handle errors from voice service."""
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
