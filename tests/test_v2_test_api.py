"""Tests for the /api/v2-test scaffolding endpoints.

These endpoints are read-only and pure — they never originate calls,
never mutate settings, and never touch production patient data. The
tests pin that contract.
"""
import pytest

from app.api import intake as intake_api
from app.api.v2_test import (
    GateEvaluateRequest,
    GateOverlay,
    gate_evaluate,
    list_scenarios,
)


# ---- Scenario catalog ----------------------------------------------------

@pytest.mark.asyncio
async def test_scenarios_catalog_loads_all_starters():
    resp = await list_scenarios()
    ids = {s.id for s in resp.scenarios}
    # Pin the starter set so accidental file deletion is caught.
    assert {
        "clean_mr_contrast",
        "no_intake_needed",
        "identity_mismatch",
        "recording_refusal",
    }.issubset(ids)


@pytest.mark.asyncio
async def test_scenarios_all_use_test_tenant():
    # Safety invariant: every shipped scenario must target the TEST tenant.
    # If a real-looking tenant ever sneaks into the catalog, this trips.
    resp = await list_scenarios()
    for scenario in resp.scenarios:
        assert scenario.patient.tenant_id == "TEST"
        assert scenario.patient.order_id.startswith("TEST-")


@pytest.mark.asyncio
async def test_identity_mismatch_scenario_has_divergent_dobs():
    # Spot-check: the identity-mismatch scenario must actually have
    # different DOBs, otherwise it wouldn't exercise the failure path.
    resp = await list_scenarios()
    sc = next(s for s in resp.scenarios if s.id == "identity_mismatch")
    assert sc.patient.dob_on_order != sc.expected_patient_dob


# ---- Gate evaluate -------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_evaluate_default_overlay_admits_test_order():
    req = GateEvaluateRequest(order_id="TEST-ORD-001", tenant_id="TEST")
    resp = await gate_evaluate(req)
    assert resp.eligible is True
    assert resp.reason == "eligible"
    assert resp.canary_bucket is not None
    assert 0 <= resp.canary_bucket < 100


@pytest.mark.asyncio
async def test_gate_evaluate_master_off_overlay_blocks():
    req = GateEvaluateRequest(
        order_id="TEST-ORD-001",
        tenant_id="TEST",
        overlay=GateOverlay(master_enabled=False),
    )
    resp = await gate_evaluate(req)
    assert resp.eligible is False
    assert resp.reason == "master_off"


@pytest.mark.asyncio
async def test_gate_evaluate_zero_canary_blocks():
    req = GateEvaluateRequest(
        order_id="TEST-ORD-001",
        tenant_id="TEST",
        overlay=GateOverlay(order_canary_pct=0),
    )
    resp = await gate_evaluate(req)
    assert resp.eligible is False
    assert resp.reason == "outside_canary"


@pytest.mark.asyncio
async def test_gate_evaluate_non_test_tenant_blocked_by_default_allowlist():
    # Default overlay has tenant_allowlist=["TEST"], so a real-looking
    # tenant must be rejected even at 100% canary.
    req = GateEvaluateRequest(
        order_id="REAL-ORD-001",
        tenant_id="PROD",
    )
    resp = await gate_evaluate(req)
    assert resp.eligible is False
    assert resp.reason == "tenant_not_allowed"


@pytest.mark.asyncio
async def test_gate_evaluate_missing_order_id_returns_no_bucket():
    req = GateEvaluateRequest(order_id=None, tenant_id="TEST")
    resp = await gate_evaluate(req)
    assert resp.eligible is False
    assert resp.reason == "no_order_id"
    assert resp.canary_bucket is None


@pytest.mark.asyncio
async def test_gate_evaluate_bucket_stable_per_order():
    # Same order_id must always produce the same bucket; the /v2-test page
    # relies on this for "this order will always be admitted" messaging.
    a = (await gate_evaluate(GateEvaluateRequest(order_id="TEST-ORD-42", tenant_id="TEST"))).canary_bucket
    b = (await gate_evaluate(GateEvaluateRequest(order_id="TEST-ORD-42", tenant_id="TEST"))).canary_bucket
    assert a == b


# ---- Intake fixture hook -------------------------------------------------

@pytest.mark.asyncio
async def test_fixture_seeded_status_returns_outstanding_tasks():
    intake_api.clear_all_fixtures()
    try:
        intake_api.set_fixture(
            "TEST-ORD-XYZ",
            [intake_api.OutstandingTask(category=intake_api.IntakeCategory.PRESCREEN, field_id="x")],
        )
        resp = await intake_api.get_intake_status("TEST-ORD-XYZ")
        assert len(resp.outstanding_tasks) == 1
        assert resp.outstanding_tasks[0].field_id == "x"
        assert resp.is_complete is False
    finally:
        intake_api.clear_all_fixtures()


@pytest.mark.asyncio
async def test_fixture_unset_status_returns_empty():
    intake_api.clear_all_fixtures()
    resp = await intake_api.get_intake_status("ORD-WITHOUT-FIXTURE")
    assert resp.outstanding_tasks == []
    assert resp.is_complete is True


@pytest.mark.asyncio
async def test_fixture_clear_removes_seeded_data():
    intake_api.clear_all_fixtures()
    intake_api.set_fixture(
        "TEST-ORD-ZZ",
        [intake_api.OutstandingTask(category=intake_api.IntakeCategory.SIGNED_LIEN, field_id="lien")],
    )
    intake_api.clear_fixture("TEST-ORD-ZZ")
    resp = await intake_api.get_intake_status("TEST-ORD-ZZ")
    assert resp.outstanding_tasks == []
