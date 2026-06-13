from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backfill import BackfillAgentSettings
from app.schemas.settings import SettingsOut, SettingsUpdate


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_or_create_settings(session: AsyncSession) -> BackfillAgentSettings:
    row = await session.get(BackfillAgentSettings, 1)
    if row is not None:
        return row
    row = BackfillAgentSettings(id=1)
    session.add(row)
    await session.flush()
    return row


def settings_to_out(row: BackfillAgentSettings) -> SettingsOut:
    blackout = row.agent_blackout_dates
    if blackout is not None and not isinstance(blackout, list):
        blackout = None
    return SettingsOut(
        id=row.id,
        enabled=row.enabled,
        minimum_cancellation_notice_hours=row.minimum_cancellation_notice_hours,
        sms_batch_size_per_wave=row.sms_batch_size_per_wave,
        delay_between_waves_minutes=row.delay_between_waves_minutes,
        max_waves=row.max_waves,
        ai_call_escalation_enabled=row.ai_call_escalation_enabled,
        ai_call_quantity_per_wave=row.ai_call_quantity_per_wave,
        allowed_contact_days=row.allowed_contact_days,
        contact_window_start=row.contact_window_start,
        contact_window_end=row.contact_window_end,
        contact_window_timezone=row.contact_window_timezone,
        use_shared_holiday_calendar=row.use_shared_holiday_calendar,
        agent_blackout_dates=blackout,
        same_facility_required=row.same_facility_required,
        same_cpt_required=row.same_cpt_required,
        exclude_no_show_enabled=row.exclude_no_show_enabled,
        campaign_timeout_minutes=row.campaign_timeout_minutes,
        late_response_closeout_enabled=row.late_response_closeout_enabled,
        allowed_sms_template_id=row.allowed_sms_template_id,
        allowed_voice_template_id=row.allowed_voice_template_id,
        closeout_message_template_id=row.closeout_message_template_id,
        updated_at=row.updated_at,
    )


async def update_settings(
    session: AsyncSession,
    row: BackfillAgentSettings,
    body: SettingsUpdate,
) -> BackfillAgentSettings:
    row.enabled = body.enabled
    row.minimum_cancellation_notice_hours = body.minimum_cancellation_notice_hours
    row.sms_batch_size_per_wave = body.sms_batch_size_per_wave
    row.delay_between_waves_minutes = body.delay_between_waves_minutes
    row.max_waves = body.max_waves
    row.ai_call_escalation_enabled = body.ai_call_escalation_enabled
    row.ai_call_quantity_per_wave = body.ai_call_quantity_per_wave
    row.allowed_contact_days = body.allowed_contact_days
    row.contact_window_start = body.contact_window_start
    row.contact_window_end = body.contact_window_end
    row.contact_window_timezone = body.contact_window_timezone
    row.use_shared_holiday_calendar = body.use_shared_holiday_calendar
    row.agent_blackout_dates = body.agent_blackout_dates
    row.same_facility_required = body.same_facility_required
    row.same_cpt_required = body.same_cpt_required
    row.exclude_no_show_enabled = body.exclude_no_show_enabled
    row.campaign_timeout_minutes = body.campaign_timeout_minutes
    row.late_response_closeout_enabled = body.late_response_closeout_enabled
    row.allowed_sms_template_id = body.allowed_sms_template_id
    row.allowed_voice_template_id = body.allowed_voice_template_id
    row.closeout_message_template_id = body.closeout_message_template_id
    row.updated_at = _utcnow()
    await session.flush()
    return row


def settings_snapshot(settings: BackfillAgentSettings) -> dict:
    return {
        "enabled": settings.enabled,
        "minimum_cancellation_notice_hours": settings.minimum_cancellation_notice_hours,
        "sms_batch_size_per_wave": settings.sms_batch_size_per_wave,
        "delay_between_waves_minutes": settings.delay_between_waves_minutes,
        "max_waves": settings.max_waves,
        "ai_call_escalation_enabled": settings.ai_call_escalation_enabled,
        "ai_call_quantity_per_wave": settings.ai_call_quantity_per_wave,
        "allowed_contact_days": settings.allowed_contact_days,
        "contact_window_start": settings.contact_window_start.isoformat(),
        "contact_window_end": settings.contact_window_end.isoformat(),
        "contact_window_timezone": settings.contact_window_timezone,
        "use_shared_holiday_calendar": settings.use_shared_holiday_calendar,
        "agent_blackout_dates": settings.agent_blackout_dates,
        "same_facility_required": settings.same_facility_required,
        "same_cpt_required": settings.same_cpt_required,
        "exclude_no_show_enabled": settings.exclude_no_show_enabled,
        "campaign_timeout_minutes": settings.campaign_timeout_minutes,
        "late_response_closeout_enabled": settings.late_response_closeout_enabled,
        "allowed_sms_template_id": settings.allowed_sms_template_id,
        "allowed_voice_template_id": settings.allowed_voice_template_id,
        "closeout_message_template_id": settings.closeout_message_template_id,
    }
