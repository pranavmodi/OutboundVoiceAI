from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.deps import get_db
from app.models.appointment_data import Facility, Patient
from app.models.backfill import BackfillActionLog, BackfillCampaign, BackfillCandidate
from app.schemas.campaigns import (
    CampaignDetailOut,
    CampaignListResponse,
    CampaignOut,
    CandidateOut,
    TimelineEntryOut,
)
from app.services.campaign_query_service import (
    CancelledPatient,
    FilledPatient,
    campaign_to_out,
    count_candidates,
    fetch_candidates,
    list_campaigns_filtered,
)
from app.services.campaign_service import stop_campaign_manually

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _parse_csv_ints(value: str | None) -> list[int] | None:
    if not value or not value.strip():
        return None
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def _parse_csv_str(value: str | None) -> list[str] | None:
    if not value or not value.strip():
        return None
    return [x.strip() for x in value.split(",") if x.strip()]


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    session: AsyncSession = Depends(get_db),
    started_from: datetime | None = Query(None),
    started_to: datetime | None = Query(None),
    facility_id: str | None = Query(None, description="Comma-separated facility IDs"),
    status: str | None = Query(None, description="Comma-separated campaign statuses"),
    cpt_code: str | None = Query(None),
    filled: bool | None = Query(None, description="True=filled only, False=unfilled only"),
    sort: str = Query("started_at_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> CampaignListResponse:
    items, total = await list_campaigns_filtered(
        session,
        started_from=started_from,
        started_to=started_to,
        facility_ids=_parse_csv_ints(facility_id),
        statuses=_parse_csv_str(status),
        cpt_code=cpt_code,
        filled=filled,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return CampaignListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/{campaign_id}/stop", response_model=CampaignDetailOut)
async def stop_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_db),
) -> CampaignDetailOut:
    try:
        await stop_campaign_manually(session, campaign_id)
    except ValueError as e:
        msg = str(e)
        if msg == "Campaign not found":
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    return await get_campaign(campaign_id, session)


@router.get("/{campaign_id}/timeline", response_model=list[TimelineEntryOut])
async def get_campaign_timeline(
    campaign_id: int,
    session: AsyncSession = Depends(get_db),
) -> list[TimelineEntryOut]:
    campaign = await session.get(BackfillCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = await session.execute(
        select(BackfillActionLog, Patient.id, Patient.name)
        .outerjoin(
            BackfillCandidate,
            BackfillCandidate.id == BackfillActionLog.backfill_candidate_id,
        )
        .outerjoin(Patient, Patient.id == BackfillCandidate.patient_id)
        .where(BackfillActionLog.backfill_campaign_id == campaign_id)
        .order_by(BackfillActionLog.attempted_at.asc(), BackfillActionLog.id.asc())
    )

    return [
        TimelineEntryOut(
            id=log.id,
            attempted_at=log.attempted_at,
            action_type=log.action_type,
            patient_id=patient_id,
            patient_name=patient_name,
            channel=log.channel,
            wave_number=log.wave_number,
            outcome=log.outcome,
            provider_message_id=log.provider_message_id,
        )
        for log, patient_id, patient_name in result.all()
    ]


@router.get("/{campaign_id}/candidates", response_model=list[CandidateOut])
async def get_campaign_candidates(
    campaign_id: int,
    session: AsyncSession = Depends(get_db),
) -> list[CandidateOut]:
    campaign = await session.get(BackfillCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return await fetch_candidates(session, campaign_id)


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
async def get_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_db),
) -> CampaignDetailOut:
    result = await session.execute(
        select(BackfillCampaign, Facility.name, CancelledPatient.name, FilledPatient.name)
        .join(Facility, Facility.id == BackfillCampaign.facility_id)
        .join(CancelledPatient, CancelledPatient.id == BackfillCampaign.cancelled_patient_id)
        .outerjoin(FilledPatient, FilledPatient.id == BackfillCampaign.filled_by_patient_id)
        .where(BackfillCampaign.id == campaign_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign, facility_name, cancelled_name, filled_name = row

    candidates_out = await fetch_candidates(session, campaign_id)
    total_c, eligible_c = await count_candidates(session, campaign_id)

    base = campaign_to_out(
        campaign,
        facility_name,
        candidate_count=total_c,
        eligible_count=eligible_c,
        cancelled_patient_name=cancelled_name,
        filled_by_patient_name=filled_name,
    )
    return CampaignDetailOut(**base.model_dump(), candidates=candidates_out)
