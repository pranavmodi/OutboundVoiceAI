"""V2-test API — internal QA surface for the v2 intake flow.

Two endpoints today:
- ``GET /api/v2-test/scenarios`` — the scenario catalog, read from
  ``app/scenarios/v2_test/*.json`` at request time.
- ``POST /api/v2-test/gate-evaluate`` — runs ``IntakeV2Gate`` against a
  hypothetical order + flag overlay and returns ``{eligible, reason,
  canary_bucket}``. Lets the /v2-test page show why the gate would admit
  or skip a scenario before any call is started.

Both endpoints are pure reads — they never touch production settings,
never originate a call, and never write anything. The ``/start-call``
endpoint that actually constructs a synthetic ``CallSession`` lands in a
follow-up PR once the v2 voice flow has something to exercise.

Tenant safety: every scenario in the catalog is tagged
``tenant_id="TEST"``. The gate-evaluate endpoint requires the caller to
pass an explicit tenant_id, but doesn't itself impose a TEST check — it
is observation-only. The start-call endpoint (future PR) is where the
TEST-tenant gate enforcement will live.
"""
import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.intake import IntakeCategory
from app.models import IntakeV2Settings
from app.services.intake_v2_gate import IntakeV2Gate, _canary_bucket


router = APIRouter(prefix="/api/v2-test", tags=["v2-test"])


SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "v2_test"


# ---- Scenario shape (mirrors the JSON files) -----------------------------

class ScenarioPatient(BaseModel):
    name: str
    tenant_id: str = "TEST"
    order_id: str
    dob_on_order: str  # YYYY-MM-DD


class OutstandingTaskSpec(BaseModel):
    category: IntakeCategory
    field_id: str


class FlagOverrides(BaseModel):
    mode_voice_capture: bool = True
    mode_portal_copilot: bool = False
    multi_call_resume: bool = False


class Scenario(BaseModel):
    id: str
    name: str
    description: str
    patient: ScenarioPatient
    expected_patient_dob: str
    modality: str  # RADIATION / MR_NON_CONTRAST / MR_CONTRAST
    outstanding_tasks: List[OutstandingTaskSpec] = []
    flag_overrides: FlagOverrides = Field(default_factory=FlagOverrides)
    expected_handoff_reason: Optional[str] = None
    expected_behavior: Optional[str] = None


class ScenarioCatalogResponse(BaseModel):
    scenarios: List[Scenario]


@router.get("/scenarios", response_model=ScenarioCatalogResponse)
async def list_scenarios() -> ScenarioCatalogResponse:
    """Read all *.json files in app/scenarios/v2_test/ into memory.

    Re-read on every request so a dev can drop a new JSON without restart.
    The directory is tiny (a handful of files); the cost is negligible.
    """
    if not SCENARIOS_DIR.is_dir():
        return ScenarioCatalogResponse(scenarios=[])

    scenarios: List[Scenario] = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            scenarios.append(Scenario.model_validate(data))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load scenario {path.name}: {e}",
            )
    return ScenarioCatalogResponse(scenarios=scenarios)


# ---- Gate-evaluate (shadow-mode visibility) ------------------------------

class GateOverlay(BaseModel):
    """Optional flag overlay. When omitted, the gate is evaluated against
    defaults that admit any order under tenant=TEST at 100% canary — the
    same effective config a real /v2-test call would run under.
    """
    master_enabled: bool = True
    tenant_allowlist: List[str] = Field(default_factory=lambda: ["TEST"])
    order_canary_pct: int = 100


class GateEvaluateRequest(BaseModel):
    order_id: Optional[str] = None
    tenant_id: Optional[str] = "TEST"
    overlay: GateOverlay = Field(default_factory=GateOverlay)


class GateEvaluateResponse(BaseModel):
    eligible: bool
    reason: str
    canary_bucket: Optional[int] = None  # None when order_id is missing


@router.post("/gate-evaluate", response_model=GateEvaluateResponse)
async def gate_evaluate(req: GateEvaluateRequest) -> GateEvaluateResponse:
    """Run IntakeV2Gate against a hypothetical scenario.

    Lets the /v2-test UI show "the gate would admit this because canary=100
    and tenant=TEST" or "the gate would skip this because master_enabled is
    off in the overlay." Pure function — never mutates any settings.
    """
    settings = IntakeV2Settings(
        master_enabled=req.overlay.master_enabled,
        tenant_allowlist=list(req.overlay.tenant_allowlist),
        order_canary_pct=req.overlay.order_canary_pct,
    )
    decision = IntakeV2Gate(settings).evaluate(req.order_id, tenant_id=req.tenant_id)
    bucket = _canary_bucket(req.order_id) if req.order_id else None
    return GateEvaluateResponse(
        eligible=decision.eligible,
        reason=decision.reason,
        canary_bucket=bucket,
    )


# ---- Mock-call lifecycle ------------------------------------------------

class StartCallResponse(BaseModel):
    call_id: str


class EndCallResponse(BaseModel):
    ended: bool


class RecentRunSummary(BaseModel):
    call_id: str
    patient_name: str
    order_id: str | None
    started_at: str | None
    ended_at: str | None
    outcome: str
    duration_seconds: int


class RecentRunsResponse(BaseModel):
    runs: list[RecentRunSummary]


@router.post("/start-call", response_model=StartCallResponse)
async def start_call(scenario: Scenario) -> StartCallResponse:
    """Start a synthetic /v2-test call.

    Bypasses the dispatcher entirely. Constructs an in-memory Patient +
    SystemSettings overlay, seeds the intake fixture, and hands the
    singleton CallSession both overrides. Web mode only — no Twilio
    originate, no real phone dialed.
    """
    from app.services.v2_test_session import build_test_session
    call_id = await build_test_session(scenario)
    return StartCallResponse(call_id=call_id)


@router.post("/end-call/{call_id}", response_model=EndCallResponse)
async def end_call(call_id: str) -> EndCallResponse:
    """End a /v2-test call and clear its intake fixture."""
    from app.services.v2_test_session import teardown_test_session
    ended = await teardown_test_session(call_id)
    return EndCallResponse(ended=ended)


@router.get("/recent-runs", response_model=RecentRunsResponse)
async def recent_runs(limit: int = 20) -> RecentRunsResponse:
    """Recent /v2-test calls — filtered to mock_mode=true AND TEST-PAT-*.

    The TEST-PAT- prefix is stamped on every synthetic patient_id by
    ``v2_test_session._build_synthetic_patient``, so this filter is
    exact even though tenant_id isn't stored on call_logs.
    """
    from app.providers import get_call_log_provider
    provider = get_call_log_provider()
    # We don't have a dedicated "filter by patient_id prefix + mock_mode"
    # query yet, so reuse get_all_calls and filter in Python. The limit is
    # small (20) so the over-fetch is negligible.
    # include_test=True so we see the mock_mode rows we're filtering for —
    # otherwise the default filter would hide every /v2-test call from us.
    all_calls = await provider.get_all_calls(
        limit=max(limit * 5, 100), offset=0, include_test=True,
    )
    runs: list[RecentRunSummary] = []
    for c in all_calls:
        if not c.mock_mode:
            continue
        if not (c.patient_id or "").startswith("TEST-PAT-"):
            continue
        runs.append(RecentRunSummary(
            call_id=c.call_id,
            patient_name=c.patient_name,
            order_id=c.order_id,
            started_at=c.started_at.isoformat() if c.started_at else None,
            ended_at=c.ended_at.isoformat() if c.ended_at else None,
            outcome=str(getattr(c.outcome, "value", c.outcome) or ""),
            duration_seconds=c.duration_seconds or 0,
        ))
        if len(runs) >= limit:
            break
    return RecentRunsResponse(runs=runs)
