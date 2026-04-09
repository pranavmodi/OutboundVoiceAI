"""Call log provider — DB-backed."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.db.models import CallLogRow
from app.models import (
    CallLog, CallOutcome, CallStatus, CallDisposition, TranscriptEntry,
    derive_status_and_disposition,
)


def _safe_enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


def _row_to_call_log(row: CallLogRow) -> CallLog:
    outcome = _safe_enum(CallOutcome, row.outcome, CallOutcome.IN_PROGRESS)
    call_status = _safe_enum(CallStatus, row.call_status, CallStatus.IN_PROGRESS)
    call_disposition = _safe_enum(CallDisposition, row.call_disposition, CallDisposition.IN_PROGRESS)

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
    cl.call_status = call_status
    cl.call_disposition = call_disposition
    cl.mock_mode = bool(row.mock_mode)
    cl.transfer_attempted = row.transfer_attempted
    cl.transfer_success = row.transfer_success
    cl.voicemail_left = row.voicemail_left
    cl.sms_sent = row.sms_sent
    cl.preferred_callback_time = row.preferred_callback_time
    cl.queue_snapshot = row.queue_snapshot
    cl.error_code = row.error_code
    cl.error_message = row.error_message
    cl.recording_sid = row.recording_sid
    cl.recording_path = row.recording_path
    cl.recording_size_bytes = row.recording_size_bytes
    cl.recording_duration_seconds = row.recording_duration_seconds
    cl.recording_format = row.recording_format

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
        mock_mode: bool = False,
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
                mock_mode=mock_mode,
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
        cl.call_status = CallStatus.IN_PROGRESS
        cl.call_disposition = CallDisposition.IN_PROGRESS
        cl.mock_mode = mock_mode
        cl.transfer_attempted = False
        cl.transfer_success = False
        cl.voicemail_left = False
        cl.sms_sent = False
        cl.preferred_callback_time = None
        cl.queue_snapshot = queue_snapshot
        cl.transcript = []
        cl.error_code = None
        cl.error_message = None
        cl.recording_sid = None
        cl.recording_path = None
        cl.recording_size_bytes = None
        cl.recording_duration_seconds = None
        cl.recording_format = None
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

    async def get_all_calls(self, limit: int = 50, offset: int = 0) -> list[CallLog]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow)
                .order_by(CallLogRow.started_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return [_row_to_call_log(r) for r in result.scalars().all()]

    async def get_total_call_count(self) -> int:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(func.count(CallLogRow.call_id)))
            return result.scalar() or 0

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

                # Derive call_status + call_disposition from the full context
                transcript = row.transcript or []
                had_patient_speech = any(
                    entry.get("speaker") == "patient" and (entry.get("text") or "").strip()
                    for entry in transcript
                )
                status, disposition = derive_status_and_disposition(
                    outcome=outcome,
                    error_code=row.error_code,
                    had_patient_speech=had_patient_speech,
                    duration_seconds=row.duration_seconds,
                )
                row.call_status = status.value
                row.call_disposition = disposition.value
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

    async def set_recording(
        self,
        call_id: str,
        recording_sid: str,
        recording_path: str,
        recording_size_bytes: int,
        recording_duration_seconds: int,
        recording_format: str = "mp3",
    ):
        """Attach a downloaded recording to a call log row."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CallLogRow).where(CallLogRow.call_id == call_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.recording_sid = recording_sid
                row.recording_path = recording_path
                row.recording_size_bytes = recording_size_bytes
                row.recording_duration_seconds = recording_duration_seconds
                row.recording_format = recording_format
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

    async def get_stats_for_date(self, target_date, tz_name: str = "America/Los_Angeles") -> dict:
        """Get a full disposition breakdown for a specific local date.

        Used by the daily Slack report.  `target_date` is a datetime.date
        interpreted in the given timezone; all calls started_at between
        local midnight and the next local midnight are counted.
        """
        from datetime import datetime as _dt, time as _time, timedelta as _td
        from zoneinfo import ZoneInfo

        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("America/Los_Angeles")
        local_start = _dt.combine(target_date, _time.min).replace(tzinfo=tz)
        local_end = local_start + _td(days=1)
        start_utc = local_start.astimezone(timezone.utc)
        end_utc = local_end.astimezone(timezone.utc)

        async with AsyncSessionLocal() as session:
            # Total
            total_result = await session.execute(
                select(func.count(CallLogRow.call_id))
                .where(CallLogRow.started_at >= start_utc)
                .where(CallLogRow.started_at < end_utc)
            )
            total = total_result.scalar() or 0

            # Disposition breakdown
            disp_result = await session.execute(
                select(CallLogRow.call_disposition, func.count(CallLogRow.call_id))
                .where(CallLogRow.started_at >= start_utc)
                .where(CallLogRow.started_at < end_utc)
                .group_by(CallLogRow.call_disposition)
            )
            dispositions = {row[0]: row[1] for row in disp_result.all()}

            # SMS count
            sms_result = await session.execute(
                select(func.count(CallLogRow.call_id))
                .where(CallLogRow.started_at >= start_utc)
                .where(CallLogRow.started_at < end_utc)
                .where(CallLogRow.sms_sent == True)  # noqa: E712
            )
            sms = sms_result.scalar() or 0

        return {
            "date": target_date.isoformat(),
            "timezone": tz_name,
            "total_calls": total,
            "dispositions": dispositions,
            "sms": sms,
        }

    async def get_today_kpis(self) -> dict:
        """Return today's headline numbers for the dashboard KPI row.

        'Today' is computed in the server's local timezone so the numbers
        line up with the operator's actual workday.
        """
        from datetime import datetime as _dt, time as _time
        # Midnight today in local time, then converted to an aware UTC datetime
        # to match how started_at is stored.
        local_midnight = _dt.combine(_dt.now().date(), _time.min).astimezone()
        start_utc = local_midnight.astimezone(timezone.utc)

        async with AsyncSessionLocal() as session:
            # Total calls placed today (any outcome)
            total_result = await session.execute(
                select(func.count(CallLogRow.call_id))
                .where(CallLogRow.started_at >= start_utc)
            )
            total_calls = total_result.scalar() or 0

            # Transferred today
            transferred_result = await session.execute(
                select(func.count(CallLogRow.call_id))
                .where(CallLogRow.started_at >= start_utc)
                .where(CallLogRow.transfer_success == True)  # noqa: E712
            )
            transferred = transferred_result.scalar() or 0

            # Voicemails left today
            vm_result = await session.execute(
                select(func.count(CallLogRow.call_id))
                .where(CallLogRow.started_at >= start_utc)
                .where(CallLogRow.voicemail_left == True)  # noqa: E712
            )
            voicemails = vm_result.scalar() or 0

            # SMS sent today
            sms_result = await session.execute(
                select(func.count(CallLogRow.call_id))
                .where(CallLogRow.started_at >= start_utc)
                .where(CallLogRow.sms_sent == True)  # noqa: E712
            )
            sms = sms_result.scalar() or 0

        return {
            "total_calls": total_calls,
            "transferred": transferred,
            "voicemails": voicemails,
            "sms": sms,
        }

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
