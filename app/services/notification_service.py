"""SMS and email notification service extracted from CallOrchestrator."""
import asyncio
import logging
from typing import Optional, Callable, Any

from app.models import CallLog, CallOutcome, Patient
from app.providers import get_call_log_provider
from app.services.email_notification_service import (
    send_wrong_number_email,
    send_disconnected_number_email,
)
from app.services.twilio_sms_service import (
    build_sms_message,
    send_sms,
    is_number_opted_out,
    is_twilio_opt_out_error,
)

logger = logging.getLogger(__name__)


class CallNotificationService:
    """Handles SMS and email notifications for call outcomes."""

    def __init__(self):
        self._sms_sent_call_ids: set[str] = set()
        self._sms_locks: dict[str, asyncio.Lock] = {}
        self._email_sent_call_ids: set[str] = set()
        self.on_status_update: Optional[Callable[[str], Any]] = None

    async def _log_call_event(self, call_id: str, message: str):
        call_log_provider = get_call_log_provider()
        await call_log_provider.add_transcript(call_id, "system", message)

    async def has_sms_been_sent(self, call_id: str) -> bool:
        """Check persisted call state to avoid duplicate SMS sends."""
        call_log_provider = get_call_log_provider()
        row = await call_log_provider.get_call(call_id)
        return bool(row and row.sms_sent)

    async def send_sms_for_call(
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
            if call.sms_sent or call.call_id in self._sms_sent_call_ids:
                await self._log_call_event(call.call_id, f"SMS skipped ({reason}): already sent")
                if self.on_status_update:
                    await self.on_status_update(f"SMS already sent for call {call.call_id[:8]}")
                return True

            if await self.has_sms_been_sent(call.call_id):
                call.sms_sent = True
                self._sms_sent_call_ids.add(call.call_id)
                await self._log_call_event(call.call_id, f"SMS skipped ({reason}): already sent")
                if self.on_status_update:
                    await self.on_status_update(f"SMS already sent for call {call.call_id[:8]}")
                return True

            mode = call_mode or "web"
            call_log_provider = get_call_log_provider()
            if is_number_opted_out(patient.phone):
                await self._log_call_event(
                    call.call_id,
                    f"SMS blocked ({reason}): recipient opted out [{patient.phone}]",
                )
                if self.on_status_update:
                    await self.on_status_update(f"SMS blocked ({reason}): recipient opted out")
                return False

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

    async def maybe_send_issue_email(self, call: CallLog, outcome: CallOutcome):
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
                outcome == CallOutcome.FAILED and _looks_like_disconnected_or_invalid(status_text)
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

    def cleanup_call(self, call_id: str):
        """Remove idempotency state for a completed call."""
        self._sms_locks.pop(call_id, None)
        self._sms_sent_call_ids.discard(call_id)
        self._email_sent_call_ids.discard(call_id)


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
