"""Tests for /v2-test mock-call lifecycle.

Covers the tenant_id="TEST" guard, fixture seeding/clearing, overlay
construction, and the start-call/end-call/recent-runs endpoints.

We don't exercise a real voice connection — the singleton CallSession's
voice-service init is patched out. The tests focus on the override
contract and side effects (fixture, ownership map) that the factory owns.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import intake as intake_api
from app.api.v2_test import (
    FlagOverrides,
    OutstandingTaskSpec,
    Scenario,
    ScenarioPatient,
    end_call,
    recent_runs,
    start_call,
)
from app.models import CallLog, SystemSettings
from app.services import v2_test_session


def _scenario(
    *,
    tenant_id: str = "TEST",
    order_id: str = "TEST-ORD-X",
    tasks=None,
) -> Scenario:
    return Scenario(
        id="t",
        name="t",
        description="t",
        patient=ScenarioPatient(
            name="Test Patient",
            tenant_id=tenant_id,
            order_id=order_id,
            dob_on_order="1990-01-01",
        ),
        expected_patient_dob="1990-01-01",
        modality="MR_CONTRAST",
        outstanding_tasks=tasks or [
            OutstandingTaskSpec(category=intake_api.IntakeCategory.PRESCREEN, field_id="x"),
        ],
        flag_overrides=FlagOverrides(),
    )


def _call_log(call_id="CALL-T-1", patient_id="TEST-PAT-abc", order_id="TEST-ORD-X"):
    return CallLog(
        call_id=call_id,
        patient_id=patient_id,
        patient_name="Test Patient",
        phone="+15550000000",
        order_id=order_id,
        priority_bucket=0,
    )


# ---- build_test_session --------------------------------------------------

@pytest.mark.asyncio
async def test_non_test_tenant_rejected():
    """Hard guard: anything other than TEST must fail validation."""
    s = _scenario(tenant_id="PROD")
    with pytest.raises(HTTPException) as exc:
        await v2_test_session.build_test_session(s)
    assert exc.value.status_code == 400
    assert "TEST" in exc.value.detail


@pytest.mark.asyncio
async def test_blank_tenant_rejected():
    s = _scenario(tenant_id="")
    with pytest.raises(HTTPException) as exc:
        await v2_test_session.build_test_session(s)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_concurrent_call_rejected():
    """Singleton CallSession only allows one call at a time."""
    s = _scenario()
    orchestrator = MagicMock()
    orchestrator.is_call_active = True

    settings_provider = AsyncMock()
    settings_provider.get_settings = AsyncMock(return_value=SystemSettings())

    with patch("app.services.v2_test_session.get_orchestrator", return_value=orchestrator), \
         patch("app.services.v2_test_session.get_settings_provider", return_value=settings_provider):
        with pytest.raises(HTTPException) as exc:
            await v2_test_session.build_test_session(s)
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_successful_build_seeds_fixture_and_uses_overrides():
    """Happy path: fixture is set, overrides are passed to start_call,
    fixture ownership is recorded under the returned call_id."""
    intake_api.clear_all_fixtures()
    v2_test_session._FIXTURE_OWNERSHIP.clear()

    s = _scenario(order_id="TEST-ORD-HAPPY")
    orchestrator = AsyncMock()
    orchestrator.is_call_active = False
    orchestrator.start_call = AsyncMock(return_value=_call_log(call_id="CALL-HAPPY"))

    settings_provider = AsyncMock()
    settings_provider.get_settings = AsyncMock(return_value=SystemSettings())

    with patch("app.services.v2_test_session.get_orchestrator", return_value=orchestrator), \
         patch("app.services.v2_test_session.get_settings_provider", return_value=settings_provider):
        call_id = await v2_test_session.build_test_session(s)

    assert call_id == "CALL-HAPPY"

    # Fixture seeded
    resp = await intake_api.get_intake_status("TEST-ORD-HAPPY")
    assert len(resp.outstanding_tasks) == 1
    assert resp.outstanding_tasks[0].field_id == "x"

    # Overrides actually used
    orchestrator.start_call.assert_awaited_once()
    kwargs = orchestrator.start_call.await_args.kwargs
    assert kwargs["call_mode"] == "web"
    assert kwargs["patient_override"].order_id == "TEST-ORD-HAPPY"
    assert kwargs["patient_override"].patient_id.startswith("TEST-PAT-")
    overlay = kwargs["settings_override"]
    assert overlay.mock_mode is True
    assert overlay.call_mode == "web"
    assert overlay.intake_v2.master_enabled is True
    assert overlay.intake_v2.tenant_allowlist == ["TEST"]
    assert overlay.intake_v2.order_canary_pct == 100

    # Ownership recorded so teardown clears the right fixture
    assert v2_test_session._FIXTURE_OWNERSHIP["CALL-HAPPY"] == "TEST-ORD-HAPPY"

    intake_api.clear_all_fixtures()
    v2_test_session._FIXTURE_OWNERSHIP.clear()


@pytest.mark.asyncio
async def test_settings_overlay_is_deep_clone():
    """Mutating the overlay must NOT mutate the live SystemSettings — a
    shallow copy would leak v2-flag changes into prod reads."""
    s = _scenario()
    base = SystemSettings()
    assert base.intake_v2.master_enabled is False  # sanity

    orchestrator = AsyncMock()
    orchestrator.is_call_active = False
    orchestrator.start_call = AsyncMock(return_value=_call_log())

    settings_provider = AsyncMock()
    settings_provider.get_settings = AsyncMock(return_value=base)

    with patch("app.services.v2_test_session.get_orchestrator", return_value=orchestrator), \
         patch("app.services.v2_test_session.get_settings_provider", return_value=settings_provider):
        await v2_test_session.build_test_session(s)

    # Base must be untouched.
    assert base.intake_v2.master_enabled is False
    assert base.mock_mode is False

    intake_api.clear_all_fixtures()
    v2_test_session._FIXTURE_OWNERSHIP.clear()


@pytest.mark.asyncio
async def test_start_call_failure_clears_fixture():
    """If start_call raises, the fixture must be cleared so subsequent
    real-traffic reads of that order_id return empty as expected."""
    intake_api.clear_all_fixtures()
    v2_test_session._FIXTURE_OWNERSHIP.clear()

    s = _scenario(order_id="TEST-ORD-FAIL")
    orchestrator = AsyncMock()
    orchestrator.is_call_active = False
    orchestrator.start_call = AsyncMock(side_effect=RuntimeError("boom"))

    settings_provider = AsyncMock()
    settings_provider.get_settings = AsyncMock(return_value=SystemSettings())

    with patch("app.services.v2_test_session.get_orchestrator", return_value=orchestrator), \
         patch("app.services.v2_test_session.get_settings_provider", return_value=settings_provider):
        with pytest.raises(RuntimeError):
            await v2_test_session.build_test_session(s)

    resp = await intake_api.get_intake_status("TEST-ORD-FAIL")
    assert resp.outstanding_tasks == []


# ---- teardown_test_session -----------------------------------------------

@pytest.mark.asyncio
async def test_teardown_clears_fixture_and_ends_call():
    intake_api.clear_all_fixtures()
    v2_test_session._FIXTURE_OWNERSHIP.clear()

    intake_api.set_fixture(
        "TEST-ORD-T",
        [intake_api.OutstandingTask(
            category=intake_api.IntakeCategory.PRESCREEN, field_id="x")],
    )
    v2_test_session._FIXTURE_OWNERSHIP["CALL-T-2"] = "TEST-ORD-T"

    orchestrator = AsyncMock()
    orchestrator.is_call_active = True
    orchestrator._current_call = _call_log(call_id="CALL-T-2")
    orchestrator.end_call = AsyncMock()

    with patch("app.services.v2_test_session.get_orchestrator", return_value=orchestrator):
        ended = await v2_test_session.teardown_test_session("CALL-T-2")

    assert ended is True
    orchestrator.end_call.assert_awaited_once()
    # Fixture cleared
    resp = await intake_api.get_intake_status("TEST-ORD-T")
    assert resp.outstanding_tasks == []
    # Ownership cleared
    assert "CALL-T-2" not in v2_test_session._FIXTURE_OWNERSHIP


@pytest.mark.asyncio
async def test_teardown_refuses_to_end_unrelated_call():
    """If the singleton holds a different call than the one we want to
    tear down, we must NOT end it. Owned-call invariant."""
    v2_test_session._FIXTURE_OWNERSHIP.clear()

    orchestrator = AsyncMock()
    orchestrator.is_call_active = True
    orchestrator._current_call = _call_log(call_id="OTHER-CALL")
    orchestrator.end_call = AsyncMock()

    with patch("app.services.v2_test_session.get_orchestrator", return_value=orchestrator):
        ended = await v2_test_session.teardown_test_session("CALL-T-MISMATCH")

    assert ended is False
    orchestrator.end_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_teardown_when_no_active_call_returns_false():
    v2_test_session._FIXTURE_OWNERSHIP.clear()
    orchestrator = AsyncMock()
    orchestrator.is_call_active = False

    with patch("app.services.v2_test_session.get_orchestrator", return_value=orchestrator):
        ended = await v2_test_session.teardown_test_session("CALL-T-NONE")
    assert ended is False


# ---- Endpoints -----------------------------------------------------------

@pytest.mark.asyncio
async def test_start_call_endpoint_rejects_non_test_tenant():
    s = _scenario(tenant_id="PROD")
    with pytest.raises(HTTPException) as exc:
        await start_call(s)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_end_call_endpoint_returns_ended_flag():
    with patch(
        "app.services.v2_test_session.teardown_test_session",
        new=AsyncMock(return_value=True),
    ):
        resp = await end_call("CALL-T-1")
    assert resp.ended is True


@pytest.mark.asyncio
async def test_recent_runs_filters_to_test_calls_only():
    """Only mock_mode=True AND patient_id starts with TEST-PAT- should appear."""
    from datetime import datetime, timezone

    def _make(call_id, patient_id, mock_mode):
        c = CallLog(
            call_id=call_id,
            patient_id=patient_id,
            patient_name="X",
            phone="+15550000000",
            order_id="O",
            priority_bucket=0,
        )
        c.mock_mode = mock_mode
        c.started_at = datetime.now(timezone.utc)
        c.duration_seconds = 5
        return c

    test_call = _make("CALL-T", "TEST-PAT-abc", True)
    real_mock = _make("CALL-M", "PRE001", True)        # mock but real patient
    real_call = _make("CALL-R", "PRE001", False)        # real prod call
    test_mode_off = _make("CALL-X", "TEST-PAT-def", False)  # weird: TEST id but not mock

    provider = AsyncMock()
    provider.get_all_calls = AsyncMock(
        return_value=[test_call, real_mock, real_call, test_mode_off]
    )
    with patch("app.providers.get_call_log_provider", return_value=provider):
        resp = await recent_runs(limit=20)

    ids = {r.call_id for r in resp.runs}
    assert ids == {"CALL-T"}
