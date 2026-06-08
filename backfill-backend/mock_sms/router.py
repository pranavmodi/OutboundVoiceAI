"""Dev-only mock SMS API — mounted when BACKFILL_SMS_PROVIDER=mock."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from mock_sms import store
from mock_sms.schemas import MockSmsMessageOut, MockSmsReplyRequest, MockSmsReplyResponse
from mock_sms.service import simulate_reply

router = APIRouter(tags=["mock-sms"])


@router.get("/campaigns/{campaign_id}/messages", response_model=list[MockSmsMessageOut])
async def list_campaign_messages(campaign_id: int) -> list[MockSmsMessageOut]:
    rows = store.list_for_campaign(campaign_id)
    return [
        MockSmsMessageOut(
            id=m.id,
            direction=m.direction,
            campaign_id=m.campaign_id,
            candidate_id=m.candidate_id,
            patient_id=m.patient_id,
            patient_name=m.patient_name,
            from_number=m.from_number,
            to_number=m.to_number,
            body=m.body,
            created_at=m.created_at,
        )
        for m in sorted(rows, key=lambda x: x.created_at)
    ]


@router.post("/campaigns/{campaign_id}/reply", response_model=MockSmsReplyResponse)
async def reply_to_campaign(
    campaign_id: int,
    body: MockSmsReplyRequest,
    session: AsyncSession = Depends(get_db),
) -> MockSmsReplyResponse:
    status, cid, cand_id, message = await simulate_reply(
        session,
        campaign_id=campaign_id,
        body=body.body,
        patient_id=body.patient_id,
    )
    if status == "not_found":
        raise HTTPException(status_code=404, detail=message)
    if status == "campaign_not_running":
        raise HTTPException(status_code=400, detail=message)
    if status == "no_candidate":
        raise HTTPException(status_code=400, detail=message)
    if status == "no_phone":
        raise HTTPException(status_code=400, detail=message)
    if status == "already_responded":
        raise HTTPException(status_code=400, detail=message)
    return MockSmsReplyResponse(
        status=status,
        campaign_id=cid,
        candidate_id=cand_id,
        message=message,
    )
