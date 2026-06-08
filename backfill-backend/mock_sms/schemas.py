"""Pydantic models for mock SMS API."""
from datetime import datetime

from pydantic import BaseModel, Field


class MockSmsMessageOut(BaseModel):
    id: str
    direction: str
    campaign_id: int
    candidate_id: int | None
    patient_id: int | None
    patient_name: str | None
    from_number: str
    to_number: str
    body: str
    created_at: datetime


class MockSmsReplyRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=160)
    patient_id: int | None = None


class MockSmsReplyResponse(BaseModel):
    status: str
    campaign_id: int | None = None
    candidate_id: int | None = None
    message: str | None = None
