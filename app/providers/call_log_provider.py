"""Call log provider — DB-backed."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.db.models import CallLogRow
from app.models import CallLog, CallOutcome, TranscriptEntry


def _row_to_call_log(row: CallLogRow) -> CallLog:
    try:
        outcome = CallOutcome(row.outcome)
    except ValueError:
        outcome = CallOutcome.IN_PROGRESS

    cl = CallLog.__new__(CallLog)
    cl.call_id = row.call_id
    cl.patient_id = row.patient_id
    cl.patient_name = row.patient_name
    cl.phone = row.phone
    cl.order_id = row.order_id
    cl.priority_bucket = row.priority_bucket
    cl.started_at = row.started_at
    cl.ended_at = row.ended_at
    cl.duration_seconds = row.duration_seconds
    cl.outcome = outcome
    cl.transfer_attempted = row.transfer_attempted
    cl.transfer_success = row.transfer_success
    cl.voicemail_left = row.voicemail_left
    cl.sms_sent = row.sms_sent
    cl.preferred_callback_time = row.preferred_callback_time
    cl.queue_snapshot = row.queue_snapshot
    cl.error_code = row.error_code
    cl.error_message = row.error_message

    # Convert JSONB transcript list to TranscriptEntry objects
    raw = row.transcript or []
    cl.transcript = []
    for entry in raw:
        te = TranscriptEntry.__new__(TranscriptEntry)
        te.speaker = entry.get("speaker", "")
        te.text = entry.get("text", "")
        ts = entry.get("timestamp")
        if ts:
            try:
                te.timestamp = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                te.timestamp = datetime.now(timezone.utc)
        else:
            te.timestamp = datetime.now(timezone.utc)
        cl.transcript.append(te)

    return cl


class CallLogProvider:
    """Stores and retrieves call logs in PostgreSQL."""

    def __init__(self):
        self._active_call_id: Optional[str] = None

    async def create_call(
        self,
        patient_id: str,
        patient_name: str,
        phone: str,
        order_id: Optional[str] = None,
        priority_bucket: int = 0,
        queue_snapshot: Optional[dict] = None,
    ) -> CallLog:
        call_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            row = CallLogRow(
                call_id=call_id,
                patient_id=patient_id,
                patient_name=patient_name,
                phone=phone,
                order_id=order_id,
                priority_bucket=priority_bucket,
                started_at=now,
                outcome="in_progress",
                queue_snapshot=queue_snapshot,
                transcript=[],
            )
            session.add(row)
            await session.commit()

        self._active_call_id = call_id
        # Return as dataclass
        cl = CallLog.__new__(CallLog)
        cl.call_id = call_id
        cl.patient_id = patient_id
        cl.patient_name = patient_name
        cl.phone = phone
        cl.order_id = order_id
        cl.priority_bucket = priority_bucket
        cl.started_at = now
        cl.ended_at = None
        cl.duration_seconds = 0
        cl.outcome = CallOutcome.IN_PROGRESS
        cl.transfer_attempted = False
        cl.transfer_success = False
        cl.voicemail_left = False
        cl.sms_sent = False
        cl.preferred_callback_time = None
        cl.queue_snapshot = queue_snapshot
        cl.transcript = []
        cl.error_code = None
        cl.error_message = None
        return cl

    async def get_call(self, call_id: str) -> Optional[CallLog]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow).where(CallLogRow.call_id == call_id)
            )
            row = result.scalar_one_or_none()
            return _row_to_call_log(row) if row else None

    async def get_active_call(self) -> Optional[CallLog]:
        if self._active_call_id is None:
            return None
        return await self.get_call(self._active_call_id)

    async def get_all_calls(self, limit: int = 50) -> list[CallLog]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow)
                .order_by(CallLogRow.started_at.desc())
                .limit(limit)
            )
            return [_row_to_call_log(r) for r in result.scalars().all()]

    async def get_calls_by_patient(self, patient_id: str) -> list[CallLog]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow)
                .where(CallLogRow.patient_id == patient_id)
                .order_by(CallLogRow.started_at.desc())
            )
            return [_row_to_call_log(r) for r in result.scalars().all()]

    async def add_transcript(self, call_id: str, speaker: str, text: str):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow).where(CallLogRow.call_id == call_id)
            )
            row = result.scalar_one_or_none()
            if row:
                current = list(row.transcript or [])
                current.append({
                    "speaker": speaker,
                    "text": text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                row.transcript = current
                await session.commit()

    async def end_call(self, call_id: str, outcome: CallOutcome):
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow).where(CallLogRow.call_id == call_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.ended_at = now
                row.outcome = outcome.value
                if row.started_at:
                    row.duration_seconds = int((now - row.started_at).total_seconds())
                await session.commit()
        if self._active_call_id == call_id:
            self._active_call_id = None

    async def update_call(
        self,
        call_id: str,
        transfer_attempted: Optional[bool] = None,
        transfer_success: Optional[bool] = None,
        voicemail_left: Optional[bool] = None,
        sms_sent: Optional[bool] = None,
        preferred_callback_time: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow).where(CallLogRow.call_id == call_id)
            )
            row = result.scalar_one_or_none()
            if row:
                if transfer_attempted is not None:
                    row.transfer_attempted = transfer_attempted
                if transfer_success is not None:
                    row.transfer_success = transfer_success
                if voicemail_left is not None:
                    row.voicemail_left = voicemail_left
                if sms_sent is not None:
                    row.sms_sent = sms_sent
                if preferred_callback_time is not None:
                    row.preferred_callback_time = preferred_callback_time
                if error_code is not None:
                    row.error_code = error_code
                if error_message is not None:
                    row.error_message = error_message
                await session.commit()

    def clear_active_call(self):
        self._active_call_id = None

    async def reset(self):
        async with AsyncSessionLocal() as session:
            await session.execute(delete(CallLogRow))
            await session.commit()
        self._active_call_id = None

    def has_active_call(self) -> bool:
        return self._active_call_id is not None

    async def get_statistics(self) -> dict:
        async with AsyncSessionLocal() as session:
            # Total count
            total_result = await session.execute(select(func.count(CallLogRow.call_id)))
            total = total_result.scalar() or 0

            if total == 0:
                return {
                    "total_calls": 0,
                    "outcomes": {},
                    "avg_duration_seconds": 0,
                    "transfer_rate": 0,
                }

            # Outcomes breakdown
            outcome_result = await session.execute(
                select(CallLogRow.outcome, func.count(CallLogRow.call_id))
                .group_by(CallLogRow.outcome)
            )
            outcomes = {row[0]: row[1] for row in outcome_result.all()}

            # Average duration
            avg_result = await session.execute(
                select(func.avg(CallLogRow.duration_seconds))
            )
            avg_duration = avg_result.scalar() or 0

            # Transfer rate
            transfer_result = await session.execute(
                select(func.count(CallLogRow.call_id))
                .where(CallLogRow.transfer_success == True)  # noqa: E712
            )
            transfers = transfer_result.scalar() or 0

            return {
                "total_calls": total,
                "outcomes": outcomes,
                "avg_duration_seconds": float(avg_duration),
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
