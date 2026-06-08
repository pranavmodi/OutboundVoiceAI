"""Milestone 2 Phase 2 — background wave worker scaffold.

This worker is intentionally conservative:
- gated by BACKFILL_WAVE_WORKER_ENABLED (default false)
- no SMS/voice dispatch yet
- only advances wave metadata and logs planned wave events
"""
import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.appointment_data import Patient
from app.models.backfill import BackfillCampaign, BackfillCandidate
from app.models.enums import ActionChannel, CampaignStatus, CandidateEligibilityStatus
from app.services.audit_service import log_action
from app.services.sms_provider import send_offer_sms
from app.services.suppression_service import get_sms_suppression_reason

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _settings_value(snapshot: dict[str, Any] | None, key: str, default: int) -> int:
    if not snapshot:
        return default
    raw = snapshot.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _campaign_max_waves(campaign: BackfillCampaign) -> int:
    return _settings_value(campaign.settings_snapshot, "max_waves", 3)


def _campaign_delay_minutes(campaign: BackfillCampaign) -> int:
    return _settings_value(campaign.settings_snapshot, "delay_between_waves_minutes", 10)


def _campaign_sms_batch_size(campaign: BackfillCampaign) -> int:
    return _settings_value(campaign.settings_snapshot, "sms_batch_size_per_wave", 3)


def _string_setting(snapshot: dict[str, Any] | None, key: str, default: str) -> str:
    if not snapshot:
        return default
    raw = snapshot.get(key, default)
    if not isinstance(raw, str):
        return default
    value = raw.strip()
    return value or default


def _time_setting(snapshot: dict[str, Any] | None, key: str, default: time) -> time:
    raw = _string_setting(snapshot, key, "")
    if not raw:
        return default
    try:
        return time.fromisoformat(raw)
    except ValueError:
        return default


def _allowed_weekdays(snapshot: dict[str, Any] | None) -> set[int]:
    mapping = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tues": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thur": 3,
        "thurs": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }
    raw_days = _string_setting(snapshot, "allowed_contact_days", "mon,tue,wed,thu,fri")
    result = {mapping[token.strip().lower()] for token in raw_days.split(",") if token.strip().lower() in mapping}
    return result or {0, 1, 2, 3, 4}


def _blackout_dates(snapshot: dict[str, Any] | None) -> set[date]:
    if not snapshot:
        return set()
    raw = snapshot.get("agent_blackout_dates")
    if not isinstance(raw, list):
        return set()
    parsed: set[date] = set()
    for value in raw:
        if not isinstance(value, str):
            continue
        try:
            parsed.add(date.fromisoformat(value))
        except ValueError:
            continue
    return parsed


def _contact_window_timezone(snapshot: dict[str, Any] | None) -> ZoneInfo:
    name = _string_setting(snapshot, "contact_window_timezone", "America/Los_Angeles")
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _is_contact_allowed_now(campaign: BackfillCampaign, now_utc: datetime) -> bool:
    snapshot = campaign.settings_snapshot
    tz = _contact_window_timezone(snapshot)
    local_now = now_utc.astimezone(tz)
    start = _time_setting(snapshot, "contact_window_start", time(8, 0))
    end = _time_setting(snapshot, "contact_window_end", time(18, 0))
    local_t = local_now.timetz().replace(tzinfo=None)
    allowed_days = _allowed_weekdays(snapshot)
    blackout = _blackout_dates(snapshot)

    if local_now.date() in blackout:
        return False
    if local_now.weekday() not in allowed_days:
        return False
    if end > start:
        return start <= local_t < end
    # Overnight window (e.g. 13:00 → 04:30 next calendar day).
    return local_t >= start or local_t < end


def _is_wave_due(campaign: BackfillCampaign, now: datetime) -> bool:
    if campaign.last_wave_at is None:
        return True
    delay = _campaign_delay_minutes(campaign)
    next_due = campaign.last_wave_at + timedelta(minutes=delay)
    return now >= next_due


async def _close_max_waves_reached(session, campaign: BackfillCampaign) -> None:
    campaign.campaign_status = CampaignStatus.CLOSED_MAX_WAVES_REACHED.value
    campaign.closed_reason = "Reached max waves (skeleton worker)"
    campaign.ended_at = _utcnow()
    await log_action(
        session,
        campaign_id=campaign.id,
        action_type="CampaignClosed",
        outcome=CampaignStatus.CLOSED_MAX_WAVES_REACHED.value,
    )


async def _plan_next_wave(session, campaign: BackfillCampaign, now: datetime) -> None:
    next_wave = (campaign.last_wave_number or 0) + 1
    campaign.last_wave_number = next_wave
    campaign.last_wave_at = now
    sent_count = await _dispatch_wave_sms(
        session=session,
        campaign=campaign,
        wave_number=next_wave,
        attempted_at=now,
    )
    await log_action(
        session,
        campaign_id=campaign.id,
        action_type="WavePlanned",
        outcome=f"SMS sent to {sent_count} candidate(s)",
        wave_number=next_wave,
    )
    if sent_count == 0:
        remaining = await _count_remaining_sms_candidates(session, campaign.id)
        if remaining == 0:
            campaign.campaign_status = CampaignStatus.CLOSED_EXHAUSTED.value
            campaign.closed_reason = "No remaining eligible candidates for SMS outreach"
            campaign.ended_at = now
            await log_action(
                session,
                campaign_id=campaign.id,
                action_type="CampaignClosed",
                outcome=CampaignStatus.CLOSED_EXHAUSTED.value,
                wave_number=next_wave,
            )


def _build_wave_sms_message(campaign: BackfillCampaign, wave_number: int) -> str:
    return (
        "Precise Imaging: An earlier appointment slot may be available. "
        "Reply YES to show interest or NO to decline. "
        f"(Campaign {campaign.id}, Wave {wave_number})"
    )


async def _count_remaining_sms_candidates(session, campaign_id: int) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(BackfillCandidate)
        .where(
            BackfillCandidate.backfill_campaign_id == campaign_id,
            BackfillCandidate.eligibility_status == CandidateEligibilityStatus.ELIGIBLE.value,
            BackfillCandidate.current_contact_status.is_(None),
        )
    )
    return count or 0


async def _fetch_sms_candidates(session, campaign: BackfillCampaign) -> list[tuple[BackfillCandidate, Patient]]:
    batch_size = _campaign_sms_batch_size(campaign)
    result = await session.execute(
        select(BackfillCandidate, Patient)
        .join(Patient, Patient.id == BackfillCandidate.patient_id)
        .where(
            BackfillCandidate.backfill_campaign_id == campaign.id,
            BackfillCandidate.eligibility_status == CandidateEligibilityStatus.ELIGIBLE.value,
            BackfillCandidate.current_contact_status.is_(None),
        )
        .order_by(BackfillCandidate.rank_order.asc(), BackfillCandidate.id.asc())
        .limit(batch_size)
    )
    return result.all()


async def _dispatch_wave_sms(
    session,
    campaign: BackfillCampaign,
    wave_number: int,
    attempted_at: datetime,
) -> int:
    sent_count = 0
    rows = await _fetch_sms_candidates(session, campaign)
    message_body = _build_wave_sms_message(campaign, wave_number)
    for candidate, patient in rows:
        suppression_reason = get_sms_suppression_reason(patient)
        if suppression_reason:
            candidate.eligibility_status = CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value
            candidate.exclusion_reason = suppression_reason
            candidate.current_contact_status = CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value
            await log_action(
                session,
                campaign_id=campaign.id,
                candidate_id=candidate.id,
                action_type="SmsSkipped",
                outcome=suppression_reason,
                channel=ActionChannel.SYSTEM.value,
                wave_number=wave_number,
            )
            continue
        if not patient.phone:
            candidate.eligibility_status = CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value
            candidate.exclusion_reason = "Missing phone number"
            candidate.current_contact_status = CandidateEligibilityStatus.EXCLUDED_INVALID_CONTACT.value
            await log_action(
                session,
                campaign_id=campaign.id,
                candidate_id=candidate.id,
                action_type="SmsSkipped",
                outcome="Missing phone number",
                channel=ActionChannel.SYSTEM.value,
                wave_number=wave_number,
            )
            continue
        try:
            provider_message_id = send_offer_sms(
                to_number=patient.phone,
                message_body=message_body,
                campaign_id=campaign.id,
                candidate_id=candidate.id,
                patient_id=patient.id,
                patient_name=patient.name,
            )
            if candidate.wave_number_first_contacted is None:
                candidate.wave_number_first_contacted = wave_number
            candidate.last_contacted_at = attempted_at
            candidate.current_contact_status = CandidateEligibilityStatus.TEXT_SENT.value
            sent_count += 1
            await log_action(
                session,
                campaign_id=campaign.id,
                candidate_id=candidate.id,
                action_type="SmsSent",
                outcome="Sent",
                channel=ActionChannel.SMS.value,
                wave_number=wave_number,
                provider_message_id=provider_message_id,
                payload={"to": patient.phone, "provider_message_id": provider_message_id},
            )
        except Exception as exc:
            candidate.current_contact_status = CandidateEligibilityStatus.ERROR.value
            await log_action(
                session,
                campaign_id=campaign.id,
                candidate_id=candidate.id,
                action_type="SmsSendFailed",
                outcome=str(exc)[:64],
                channel=ActionChannel.SMS.value,
                wave_number=wave_number,
            )
    return sent_count


async def process_running_campaigns_once(batch_size: int) -> int:
    """Poll running campaigns and apply skeleton wave progression."""
    now = _utcnow()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BackfillCampaign)
            .where(BackfillCampaign.campaign_status == CampaignStatus.RUNNING.value)
            .order_by(BackfillCampaign.started_at.asc(), BackfillCampaign.id.asc())
            .limit(max(1, batch_size))
        )
        campaigns = result.scalars().all()

        processed = 0
        for campaign in campaigns:
            processed += 1
            max_waves = _campaign_max_waves(campaign)
            current_wave = campaign.last_wave_number or 0

            if current_wave >= max_waves:
                await _close_max_waves_reached(session, campaign)
                continue

            if _is_wave_due(campaign, now) and _is_contact_allowed_now(campaign, now):
                await _plan_next_wave(session, campaign, now)

        await session.commit()
        return processed


class WaveWorker:
    """Async polling loop for campaign waves."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="backfill-wave-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        poll_seconds = max(1, settings.backfill_wave_worker_poll_seconds)
        batch_size = max(1, settings.backfill_wave_worker_batch_size)
        while not self._stop.is_set():
            try:
                await process_running_campaigns_once(batch_size=batch_size)
            except Exception as exc:
                # Keep worker alive even when one polling iteration fails.
                logger.exception("Wave worker iteration failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=poll_seconds)
            except asyncio.TimeoutError:
                continue
