"""Audit event logging and query service.

Every external API call (RadFlow, HL7, SMS, email, Slack) is logged here
so Danny has a single view of everything the system did to each patient.
"""
import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.db.models import AuditEventRow

logger = logging.getLogger(__name__)


async def log_audit_event(
    event_type: str,
    action: str,
    status: str,
    request_summary: str = "",
    call_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    patient_name: str = "",
    order_id: Optional[str] = None,
    request_payload: Optional[dict] = None,
    response_status: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Insert an audit event row. Best-effort — never raises."""
    try:
        async with AsyncSessionLocal() as session:
            row = AuditEventRow(
                call_id=call_id,
                patient_id=patient_id,
                patient_name=patient_name,
                order_id=order_id,
                event_type=event_type,
                action=action,
                status=status,
                request_summary=request_summary,
                request_payload=request_payload,
                response_status=response_status,
                error_message=error_message,
            )
            session.add(row)
            await session.commit()
    except Exception as e:
        logger.warning("Failed to log audit event (%s/%s): %s", event_type, action, e)


async def query_audit_events(
    limit: int = 50,
    offset: int = 0,
    event_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    patient_id: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Query audit events with filters. Returns (events, total_count)."""
    async with AsyncSessionLocal() as session:
        base = select(AuditEventRow)
        count_base = select(func.count(AuditEventRow.id))

        conditions = []
        if event_type and event_type != "all":
            conditions.append(AuditEventRow.event_type == event_type)
        if status_filter and status_filter != "all":
            conditions.append(AuditEventRow.status == status_filter)
        if patient_id:
            conditions.append(AuditEventRow.patient_id == patient_id)
        if start_date:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo("America/Los_Angeles")
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
                conditions.append(AuditEventRow.created_at >= start_dt.astimezone(timezone.utc))
            except Exception:
                pass
        if end_date:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo("America/Los_Angeles")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=tz) + timedelta(days=1)
                conditions.append(AuditEventRow.created_at < end_dt.astimezone(timezone.utc))
            except Exception:
                pass
        if search and search.strip():
            q = f"%{search.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(AuditEventRow.patient_name).like(q),
                    func.lower(AuditEventRow.patient_id).like(q),
                    func.lower(AuditEventRow.order_id).like(q),
                    func.lower(AuditEventRow.request_summary).like(q),
                    func.lower(AuditEventRow.action).like(q),
                )
            )

        for cond in conditions:
            base = base.where(cond)
            count_base = count_base.where(cond)

        total_result = await session.execute(count_base)
        total = total_result.scalar() or 0

        result = await session.execute(
            base.order_by(AuditEventRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = result.scalars().all()

        events = [
            {
                "id": r.id,
                "call_id": r.call_id,
                "patient_id": r.patient_id,
                "patient_name": r.patient_name,
                "order_id": r.order_id,
                "event_type": r.event_type,
                "action": r.action,
                "status": r.status,
                "request_summary": r.request_summary,
                "request_payload": r.request_payload,
                "response_status": r.response_status,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    return events, total


def events_to_csv(events: list[dict]) -> str:
    """Convert audit events to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "Patient ID", "Patient Name", "Order ID",
        "Event Type", "Action", "Status", "Summary",
        "HTTP Status", "Error", "Call ID",
    ])
    for e in events:
        writer.writerow([
            e.get("created_at", ""),
            e.get("patient_id", ""),
            e.get("patient_name", ""),
            e.get("order_id", ""),
            e.get("event_type", ""),
            e.get("action", ""),
            e.get("status", ""),
            e.get("request_summary", ""),
            e.get("response_status", ""),
            e.get("error_message", ""),
            e.get("call_id", ""),
        ])
    return output.getvalue()
