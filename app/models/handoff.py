"""Structured handoff payload sent to the human scheduler at transfer time.

The v1 transfer is a bare SIP redirect — the human answers cold with no
context. v2 wraps every transfer with a payload that says *why* we're
handing off and *what* the agent already captured. Schedulers use this to
skip the questions they would otherwise have to ask the patient again.

This file defines only the M1 subset of reasons. Voice-mode and portal-mode
reasons (INTAKE_COMPLETE, PORTAL_REFUSED_FOR_ID_OR_LIEN, TECHNICAL_FAILURE,
PATIENT_DROPPED_BEFORE_COMPLETE) get added in M2/M3 when those flows ship.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TransferReason(str, Enum):
    V1_FALLBACK = "V1_FALLBACK"
    IDENTITY_VERIFICATION_FAILED = "IDENTITY_VERIFICATION_FAILED"
    PATIENT_REQUESTED_HUMAN = "PATIENT_REQUESTED_HUMAN"
    NO_INTAKE_NEEDED = "NO_INTAKE_NEEDED"


class HandoffPayload(BaseModel):
    call_id: str
    order_id: Optional[str] = None
    patient_id: Optional[str] = None
    transfer_reason: TransferReason
    identity_verified: bool = False
    call_summary: str = ""
    transcript_uri: Optional[str] = None
    transferred_at: datetime = Field(default_factory=datetime.utcnow)
