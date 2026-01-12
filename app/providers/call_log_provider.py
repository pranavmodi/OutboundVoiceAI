"""Call log provider for storing call history."""
from datetime import datetime
from typing import Optional
from app.models import CallLog, CallOutcome


class CallLogProvider:
    """Stores and retrieves call logs."""

    def __init__(self):
        self._logs: dict[str, CallLog] = {}
        self._active_call: Optional[CallLog] = None

    def create_call(
        self,
        patient_id: str,
        patient_name: str,
        phone: str,
        order_id: Optional[str] = None,
        priority_bucket: int = 0,
        queue_snapshot: Optional[dict] = None,
    ) -> CallLog:
        """Create a new call log entry."""
        call = CallLog(
            patient_id=patient_id,
            patient_name=patient_name,
            phone=phone,
            order_id=order_id,
            priority_bucket=priority_bucket,
            queue_snapshot=queue_snapshot,
        )
        self._logs[call.call_id] = call
        self._active_call = call
        return call

    def get_call(self, call_id: str) -> Optional[CallLog]:
        """Get a specific call by ID."""
        return self._logs.get(call_id)

    def get_active_call(self) -> Optional[CallLog]:
        """Get the currently active call."""
        return self._active_call

    def get_all_calls(self, limit: int = 50) -> list[CallLog]:
        """Get all calls, most recent first."""
        calls = sorted(
            self._logs.values(),
            key=lambda c: c.started_at,
            reverse=True,
        )
        return calls[:limit]

    def get_calls_by_patient(self, patient_id: str) -> list[CallLog]:
        """Get all calls for a specific patient."""
        return [c for c in self._logs.values() if c.patient_id == patient_id]

    def add_transcript(self, call_id: str, speaker: str, text: str):
        """Add a transcript entry to a call."""
        call = self._logs.get(call_id)
        if call:
            call.add_transcript(speaker, text)

    def end_call(self, call_id: str, outcome: CallOutcome):
        """End a call with the given outcome."""
        call = self._logs.get(call_id)
        if call:
            call.end_call(outcome)
            if self._active_call and self._active_call.call_id == call_id:
                self._active_call = None

    def update_call(
        self,
        call_id: str,
        transfer_attempted: Optional[bool] = None,
        transfer_success: Optional[bool] = None,
        voicemail_left: Optional[bool] = None,
        sms_sent: Optional[bool] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Update call metadata."""
        call = self._logs.get(call_id)
        if call:
            if transfer_attempted is not None:
                call.transfer_attempted = transfer_attempted
            if transfer_success is not None:
                call.transfer_success = transfer_success
            if voicemail_left is not None:
                call.voicemail_left = voicemail_left
            if sms_sent is not None:
                call.sms_sent = sms_sent
            if error_code is not None:
                call.error_code = error_code
            if error_message is not None:
                call.error_message = error_message

    def clear_active_call(self):
        """Clear the active call reference."""
        self._active_call = None

    def has_active_call(self) -> bool:
        """Check if there's an active call."""
        return self._active_call is not None

    def get_statistics(self) -> dict:
        """Get call statistics."""
        total = len(self._logs)
        if total == 0:
            return {
                "total_calls": 0,
                "outcomes": {},
                "avg_duration_seconds": 0,
                "transfer_rate": 0,
            }

        outcomes = {}
        total_duration = 0
        transfers = 0

        for call in self._logs.values():
            outcome = call.outcome.value
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            total_duration += call.duration_seconds
            if call.transfer_success:
                transfers += 1

        return {
            "total_calls": total,
            "outcomes": outcomes,
            "avg_duration_seconds": total_duration / total if total > 0 else 0,
            "transfer_rate": transfers / total if total > 0 else 0,
        }


# Global instance
_call_log_provider: Optional[CallLogProvider] = None


def get_call_log_provider() -> CallLogProvider:
    """Get the global call log provider instance."""
    global _call_log_provider
    if _call_log_provider is None:
        _call_log_provider = CallLogProvider()
    return _call_log_provider
