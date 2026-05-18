"""V2 intake API.

Stubs for the endpoints listed in section 6.3 of the v2 spec. Until the
MediFlow / RadFlow backend question is resolved (see docs/v2/plan.md), these
return safe empty responses so callers can wire their code paths without
waiting on the real backend.

Currently implemented (M1 Slice 1):
- GET /api/intake/status/{order_id} — empty by default; /v2-test can seed
  per-order fixtures via ``set_fixture`` so the future v2 voice flow has
  something to react to. Fixtures are in-memory and per-process — they
  vanish on restart and never touch production traffic when unset.

Deferred to later slices:
- GET /api/patient/{patient_id}
- POST /api/intake/capture
- GET /api/preq/config
- POST /portal/intake-session
- POST /api/call/transfer
"""
from enum import Enum
from typing import Dict, List

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/api/intake", tags=["intake"])


class IntakeCategory(str, Enum):
    DEMOGRAPHICS = "DEMOGRAPHICS"
    PRESCREEN = "PRESCREEN"
    PHOTO_ID = "PHOTO_ID"
    SIGNED_LIEN = "SIGNED_LIEN"


class OutstandingTask(BaseModel):
    category: IntakeCategory
    field_id: str


class IntakeStatusResponse(BaseModel):
    order_id: str
    outstanding_tasks: List[OutstandingTask] = []

    @property
    def is_complete(self) -> bool:
        return not self.outstanding_tasks


# Per-order test fixtures. Empty in production — only the v2-test endpoints
# write here, and they're gated to TEST-tenant scenarios. Keep the read path
# (`get_intake_status`) free of any tenant logic: if no fixture is set we
# return the same empty response we did before, so existing callers see
# byte-identical behavior.
_TEST_FIXTURES: Dict[str, List[OutstandingTask]] = {}


def set_fixture(order_id: str, tasks: List[OutstandingTask]) -> None:
    _TEST_FIXTURES[order_id] = list(tasks)


def clear_fixture(order_id: str) -> None:
    _TEST_FIXTURES.pop(order_id, None)


def clear_all_fixtures() -> None:
    _TEST_FIXTURES.clear()


@router.get("/status/{order_id}", response_model=IntakeStatusResponse)
async def get_intake_status(order_id: str) -> IntakeStatusResponse:
    """Returns outstanding intake tasks for an order.

    Real implementation will call the MediFlow / RadFlow backend. Until
    that lands, returns whatever ``/v2-test`` seeded for this order (or
    an empty list, which means "no intake needed").
    """
    return IntakeStatusResponse(
        order_id=order_id,
        outstanding_tasks=_TEST_FIXTURES.get(order_id, []),
    )
