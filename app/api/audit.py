"""Audit log API endpoints."""
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import Response

from app.services.audit_service import query_audit_events, events_to_csv

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def get_audit_log(
    limit: int = 50,
    offset: int = 0,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    patient_id: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    format: str = "json",
):
    """Get audit events with filters. Use format=csv for CSV download."""
    # For CSV export, fetch up to 10k rows
    fetch_limit = 10000 if format == "csv" else limit

    events, total = await query_audit_events(
        limit=fetch_limit,
        offset=0 if format == "csv" else offset,
        event_type=event_type,
        status_filter=status,
        patient_id=patient_id,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )

    if format == "csv":
        csv_content = events_to_csv(events)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
        )

    return {"events": events, "total": total}
