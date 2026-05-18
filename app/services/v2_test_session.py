"""Factory for /v2-test mock calls.

Builds a synthetic ``Patient`` + ``SystemSettings`` overlay from a scenario,
seeds the intake-status fixture, and hands the singleton ``CallSession``
the overrides via ``patient_override`` / ``settings_override``. The
production patient table and DB-backed settings row are never touched.

Strict tenant scoping: every scenario passed in **must** have
``patient.tenant_id == "TEST"``. The endpoint layer also enforces this,
but we double-check here so an unguarded direct call can't slip through.

Concurrency: the singleton ``CallSession`` (web mode) holds one call at
a time. Operator console + /v2-test share that singleton; only one of
them can be active at any moment. That's an accepted limit for Phase B.
"""
import copy
import logging
import uuid

from fastapi import HTTPException

from app.api import intake as intake_api
from app.models import Language, Patient, SystemSettings
from app.providers import get_settings_provider
from app.services.call_orchestrator import get_orchestrator


logger = logging.getLogger(__name__)


# Tracks which order_id's fixture this module has seeded, keyed by call_id,
# so teardown clears exactly what was set up. Multiple concurrent test calls
# aren't supported today (singleton CallSession) but the map shape lets us
# add support later without changing the interface.
_FIXTURE_OWNERSHIP: dict[str, str] = {}


def _require_test_tenant(scenario_tenant_id: str) -> None:
    if (scenario_tenant_id or "").strip() != "TEST":
        raise HTTPException(
            status_code=400,
            detail=f"Refusing scenario with tenant_id={scenario_tenant_id!r}. "
                   "Only tenant_id='TEST' is allowed on /v2-test.",
        )


def _build_synthetic_patient(scenario_patient, modality: str) -> Patient:
    """Construct a Patient from a scenario. Never written to the DB.

    The patient_id is randomized per call so call_log queries can identify
    /v2-test rows via the ``TEST-PAT-`` prefix without collision risk.
    """
    return Patient(
        patient_id=f"TEST-PAT-{uuid.uuid4().hex[:8]}",
        name=scenario_patient.name or "Synthetic Test",
        # Phone is display-only in web mode (no Twilio originate). Use the
        # documented test number so logs are obvious.
        phone="+15550000000",
        language=Language.ENGLISH,
        order_id=scenario_patient.order_id,
    )


def _build_settings_overlay(base: SystemSettings, scenario) -> SystemSettings:
    """Deep-clone production settings then overlay v2-test flags.

    Deep-clone matters because dataclass fields like ``business_hours`` are
    nested dataclasses; mutating them on a shared instance would leak into
    later DB reads.
    """
    overlay = copy.deepcopy(base)
    overlay.mock_mode = True
    overlay.call_mode = "web"
    overlay.intake_v2.master_enabled = True
    overlay.intake_v2.tenant_allowlist = ["TEST"]
    overlay.intake_v2.order_canary_pct = 100
    overlay.intake_v2.mode_voice_capture = scenario.flag_overrides.mode_voice_capture
    overlay.intake_v2.mode_portal_copilot = scenario.flag_overrides.mode_portal_copilot
    overlay.intake_v2.multi_call_resume = scenario.flag_overrides.multi_call_resume
    return overlay


async def build_test_session(scenario) -> str:
    """Construct a synthetic call. Returns the new call_id.

    Steps:
    1. Validate tenant_id="TEST".
    2. Read live SystemSettings and deep-clone with v2 flags forced on.
    3. Synthesize a Patient (in-memory only).
    4. Seed the intake-status fixture from the scenario.
    5. Call orchestrator.start_call() with both overrides.
    6. Record fixture ownership so teardown knows what to clear.

    Raises HTTPException(400) on validation failure. Other exceptions
    propagate — callers should let FastAPI render them as 500 so we see
    them in logs.
    """
    _require_test_tenant(scenario.patient.tenant_id)

    base_settings = await get_settings_provider().get_settings()
    overlay = _build_settings_overlay(base_settings, scenario)
    patient = _build_synthetic_patient(scenario.patient, scenario.modality)

    orchestrator = get_orchestrator()
    if orchestrator.is_call_active:
        raise HTTPException(
            status_code=409,
            detail="Another web-mode call is already active. End it before starting a new test call.",
        )

    # Seed fixture BEFORE start_call so any read during the call hits the
    # populated map. We don't know the call_id until create_call runs, so
    # temporarily key on order_id; the ownership map is rewritten below.
    intake_api.set_fixture(
        scenario.patient.order_id,
        [intake_api.OutstandingTask(category=t.category, field_id=t.field_id)
         for t in scenario.outstanding_tasks],
    )

    try:
        call = await orchestrator.start_call(
            patient.patient_id,
            call_mode="web",
            patient_override=patient,
            settings_override=overlay,
        )
    except Exception:
        intake_api.clear_fixture(scenario.patient.order_id)
        raise

    if call is None:
        intake_api.clear_fixture(scenario.patient.order_id)
        raise HTTPException(
            status_code=500,
            detail=f"start_call returned None: {orchestrator._last_start_error or 'unknown'}",
        )

    _FIXTURE_OWNERSHIP[call.call_id] = scenario.patient.order_id
    logger.info(
        "v2_test_session started: call_id=%s order_id=%s patient=%s",
        call.call_id, scenario.patient.order_id, patient.patient_id,
    )
    return call.call_id


async def teardown_test_session(call_id: str) -> bool:
    """End the call and clear its intake fixture.

    Returns True if a session was actively torn down, False if there was
    nothing to do (e.g., call already ended). Never raises — failures
    are logged. End-of-call cleanup must be best-effort.
    """
    from app.models import CallOutcome

    order_id = _FIXTURE_OWNERSHIP.pop(call_id, None)
    if order_id:
        intake_api.clear_fixture(order_id)

    orchestrator = get_orchestrator()
    if not orchestrator.is_call_active:
        return False

    current = orchestrator._current_call
    if current and current.call_id != call_id:
        # Some other call is active — refuse to end it. Caller passed the
        # wrong call_id or our state drifted; either way, don't touch a
        # call we don't own.
        logger.warning(
            "teardown_test_session: refusing to end call_id=%s (active call is %s)",
            call_id, current.call_id,
        )
        return False

    try:
        await orchestrator.end_call(CallOutcome.COMPLETED)
        return True
    except Exception as e:
        logger.exception("teardown_test_session: end_call failed for %s: %s", call_id, e)
        return False
