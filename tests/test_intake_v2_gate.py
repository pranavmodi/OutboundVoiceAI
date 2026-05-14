"""Tests for IntakeV2Gate — the only place that consults v2 feature flags."""
import pytest

from app.models import IntakeV2Settings
from app.services.intake_v2_gate import (
    IntakeV2Gate,
    REASON_ELIGIBLE,
    REASON_MASTER_OFF,
    REASON_NO_ORDER_ID,
    REASON_OUTSIDE_CANARY,
    REASON_TENANT_NOT_ALLOWED,
    _canary_bucket,
)


def _gate(**overrides) -> IntakeV2Gate:
    defaults = dict(
        master_enabled=True,
        tenant_allowlist=[],
        order_canary_pct=100,
        mode_voice_capture=False,
        mode_portal_copilot=False,
        multi_call_resume=False,
    )
    defaults.update(overrides)
    return IntakeV2Gate(IntakeV2Settings(**defaults))


def test_master_off_blocks_everything():
    gate = _gate(master_enabled=False, order_canary_pct=100)
    assert gate.is_eligible("ORD-1") is False


def test_canary_zero_blocks_everything():
    gate = _gate(order_canary_pct=0)
    assert gate.is_eligible("ORD-1") is False


def test_canary_full_admits_everything():
    gate = _gate(order_canary_pct=100)
    assert gate.is_eligible("ORD-1") is True
    assert gate.is_eligible("ORD-2") is True
    assert gate.is_eligible("anything") is True


def test_missing_order_id_blocks():
    gate = _gate(order_canary_pct=100)
    assert gate.is_eligible(None) is False
    assert gate.is_eligible("") is False


def test_tenant_allowlist_filters():
    gate = _gate(tenant_allowlist=["PATHORA"])
    assert gate.is_eligible("ORD-1", tenant_id="PATHORA") is True
    assert gate.is_eligible("ORD-1", tenant_id="OTHER") is False
    assert gate.is_eligible("ORD-1", tenant_id=None) is False


def test_empty_allowlist_means_no_scoping():
    gate = _gate(tenant_allowlist=[])
    assert gate.is_eligible("ORD-1", tenant_id=None) is True
    assert gate.is_eligible("ORD-1", tenant_id="anything") is True


def test_canary_bucket_is_stable_per_order():
    # Same input must always produce the same bucket — multi-call resume
    # depends on this.
    a = _canary_bucket("ORD-42")
    b = _canary_bucket("ORD-42")
    assert a == b
    assert 0 <= a < 100


def test_canary_bucket_distributes_across_buckets():
    # Sanity check: not every order ID should fall in the same bucket.
    buckets = {_canary_bucket(f"ORD-{i}") for i in range(200)}
    assert len(buckets) > 50


def test_canary_partial_inclusion_is_stable():
    # An order that's eligible at 50% must still be eligible at 60%
    # (the bucket comparison is monotonic in pct).
    gate_50 = _gate(order_canary_pct=50)
    gate_60 = _gate(order_canary_pct=60)
    for i in range(50):
        oid = f"ORD-{i}"
        if gate_50.is_eligible(oid):
            assert gate_60.is_eligible(oid)


# -- evaluate() returns structured decisions with reason codes --------------

def test_evaluate_master_off_reports_master_off():
    decision = _gate(master_enabled=False).evaluate("ORD-1")
    assert decision.eligible is False
    assert decision.reason == REASON_MASTER_OFF


def test_evaluate_no_order_id_reports_no_order_id():
    decision = _gate().evaluate(None)
    assert decision.eligible is False
    assert decision.reason == REASON_NO_ORDER_ID
    assert _gate().evaluate("").reason == REASON_NO_ORDER_ID


def test_evaluate_tenant_blocked_reports_tenant_not_allowed():
    decision = _gate(tenant_allowlist=["PATHORA"]).evaluate("ORD-1", tenant_id="OTHER")
    assert decision.eligible is False
    assert decision.reason == REASON_TENANT_NOT_ALLOWED


def test_evaluate_outside_canary_reports_outside_canary():
    decision = _gate(order_canary_pct=0).evaluate("ORD-1")
    assert decision.eligible is False
    assert decision.reason == REASON_OUTSIDE_CANARY


def test_evaluate_admits_with_eligible_reason():
    decision = _gate(order_canary_pct=100).evaluate("ORD-1")
    assert decision.eligible is True
    assert decision.reason == REASON_ELIGIBLE


def test_master_off_takes_priority_over_missing_order_id():
    # When the master flag is off, we don't care why else the call is ineligible.
    decision = _gate(master_enabled=False, order_canary_pct=100).evaluate(None)
    assert decision.reason == REASON_MASTER_OFF
