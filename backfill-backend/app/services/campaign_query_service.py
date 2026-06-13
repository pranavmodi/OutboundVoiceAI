"""Campaign list/detail query helpers — filters, pagination, counts."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.appointment_data import Facility, Patient
from app.models.backfill import BackfillCampaign, BackfillCandidate
from app.models.enums import CampaignStatus, CandidateEligibilityStatus
from app.schemas.campaigns import CampaignOut, CandidateOut

CancelledPatient = aliased(Patient)
FilledPatient = aliased(Patient)

SORT_COLUMNS = {
    "started_at": BackfillCampaign.started_at,
    "open_slot_start_at": BackfillCampaign.open_slot_start_at,
    "campaign_status": BackfillCampaign.campaign_status,
    "id": BackfillCampaign.id,
}


async def count_candidates(
    session: AsyncSession, campaign_id: int
) -> tuple[int, int]:
    total = await session.scalar(
        select(func.count())
        .select_from(BackfillCandidate)
        .where(BackfillCandidate.backfill_campaign_id == campaign_id)
    )
    eligible = await session.scalar(
        select(func.count())
        .select_from(BackfillCandidate)
        .where(
            BackfillCandidate.backfill_campaign_id == campaign_id,
            BackfillCandidate.eligibility_status == CandidateEligibilityStatus.ELIGIBLE.value,
        )
    )
    return total or 0, eligible or 0


def campaign_to_out(
    campaign: BackfillCampaign,
    facility_name: str | None,
    *,
    candidate_count: int,
    eligible_count: int,
    cancelled_patient_name: str | None = None,
    filled_by_patient_name: str | None = None,
) -> CampaignOut:
    return CampaignOut(
        id=campaign.id,
        cancelled_appointment_id=campaign.cancelled_appointment_id,
        cancelled_patient_id=campaign.cancelled_patient_id,
        cancelled_patient_name=cancelled_patient_name,
        facility_id=campaign.facility_id,
        facility_name=facility_name,
        cpt_code=campaign.cpt_code,
        open_slot_start_at=campaign.open_slot_start_at,
        cancellation_at=campaign.cancellation_at,
        campaign_status=campaign.campaign_status,
        started_at=campaign.started_at,
        ended_at=campaign.ended_at,
        closed_reason=campaign.closed_reason,
        filled_by_patient_id=campaign.filled_by_patient_id,
        filled_by_patient_name=filled_by_patient_name,
        filled_by_appointment_id=campaign.filled_by_appointment_id,
        candidate_count=candidate_count,
        eligible_count=eligible_count,
    )


def _apply_campaign_filters(
    query,
    *,
    started_from: datetime | None,
    started_to: datetime | None,
    facility_ids: list[int] | None,
    statuses: list[str] | None,
    cpt_code: str | None,
    filled: bool | None,
):
    if started_from is not None:
        query = query.where(BackfillCampaign.started_at >= started_from)
    if started_to is not None:
        query = query.where(BackfillCampaign.started_at <= started_to)
    if facility_ids:
        query = query.where(BackfillCampaign.facility_id.in_(facility_ids))
    if statuses:
        query = query.where(BackfillCampaign.campaign_status.in_(statuses))
    if cpt_code:
        query = query.where(BackfillCampaign.cpt_code.ilike(f"%{cpt_code.strip()}%"))
    if filled is True:
        query = query.where(BackfillCampaign.campaign_status == CampaignStatus.FILLED.value)
    elif filled is False:
        query = query.where(BackfillCampaign.campaign_status != CampaignStatus.FILLED.value)
    return query


async def list_campaigns_filtered(
    session: AsyncSession,
    *,
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    facility_ids: list[int] | None = None,
    statuses: list[str] | None = None,
    cpt_code: str | None = None,
    filled: bool | None = None,
    sort: str = "started_at_desc",
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[CampaignOut], int]:
    filter_kwargs = dict(
        started_from=started_from,
        started_to=started_to,
        facility_ids=facility_ids,
        statuses=statuses,
        cpt_code=cpt_code,
        filled=filled,
    )

    count_q = _apply_campaign_filters(
        select(func.count()).select_from(BackfillCampaign), **filter_kwargs
    )
    total = await session.scalar(count_q) or 0

    base = _apply_campaign_filters(
        select(BackfillCampaign, Facility.name, CancelledPatient.name, FilledPatient.name)
        .join(Facility, Facility.id == BackfillCampaign.facility_id)
        .join(CancelledPatient, CancelledPatient.id == BackfillCampaign.cancelled_patient_id)
        .outerjoin(FilledPatient, FilledPatient.id == BackfillCampaign.filled_by_patient_id),
        **filter_kwargs,
    )

    sort_key = sort.rsplit("_", 1)
    if len(sort_key) == 2 and sort_key[0] in SORT_COLUMNS and sort_key[1] in ("asc", "desc"):
        col = SORT_COLUMNS[sort_key[0]]
        order = col.asc() if sort_key[1] == "asc" else col.desc()
    else:
        order = BackfillCampaign.started_at.desc()

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    result = await session.execute(base.order_by(order).offset(offset).limit(page_size))
    items: list[CampaignOut] = []
    for campaign, facility_name, cancelled_name, filled_name in result.all():
        total_c, eligible_c = await count_candidates(session, campaign.id)
        items.append(
            campaign_to_out(
                campaign,
                facility_name,
                candidate_count=total_c,
                eligible_count=eligible_c,
                cancelled_patient_name=cancelled_name,
                filled_by_patient_name=filled_name,
            )
        )
    return items, total


async def fetch_candidates(
    session: AsyncSession, campaign_id: int
) -> list[CandidateOut]:
    result = await session.execute(
        select(BackfillCandidate, Patient.name)
        .join(Patient, Patient.id == BackfillCandidate.patient_id)
        .where(BackfillCandidate.backfill_campaign_id == campaign_id)
        .order_by(BackfillCandidate.rank_order, BackfillCandidate.id)
    )
    return [
        CandidateOut(
            id=cand.id,
            patient_id=cand.patient_id,
            patient_name=patient_name,
            appointment_id=cand.appointment_id,
            scheduled_appointment_at=cand.scheduled_appointment_at,
            rank_order=cand.rank_order,
            eligibility_status=cand.eligibility_status,
            exclusion_reason=cand.exclusion_reason,
            wave_number_first_contacted=cand.wave_number_first_contacted,
            last_contacted_at=cand.last_contacted_at,
            current_contact_status=cand.current_contact_status,
            interested_flag=cand.interested_flag,
            declined_flag=cand.declined_flag,
            no_response_flag=cand.no_response_flag,
            won_slot_flag=cand.won_slot_flag,
            lost_slot_flag=cand.lost_slot_flag,
            response_at=cand.response_at,
        )
        for cand, patient_name in result.all()
    ]
