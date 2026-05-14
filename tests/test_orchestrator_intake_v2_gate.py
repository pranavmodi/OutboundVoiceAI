"""Tests for CallOrchestrator._evaluate_intake_v2_gate.

The helper is shadow-mode-only in M1 Slice 2: it logs the gate decision
to dispatcher_events and, when eligible, hits the stubbed status endpoint.
It must not change call flow.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.models import CallLog, IntakeV2Settings, Patient, Language
from app.services.call_orchestrator import CallSession


@pytest.fixture
def call_and_patient():
    call = CallLog(
        call_id="CALL-001",
        patient_id="PAT-001",
        patient_name="Jane Doe",
        phone="+15551234567",
        order_id="ORD-001",
        priority_bucket=1,
    )
    patient = Patient(
        patient_id="PAT-001",
        name="Jane Doe",
        phone="+15551234567",
        language=Language.ENGLISH,
        order_id="ORD-001",
    )
    return call, patient


def _settings(**overrides) -> IntakeV2Settings:
    defaults = dict(
        master_enabled=False,
        tenant_allowlist=[],
        order_canary_pct=0,
        mode_voice_capture=False,
        mode_portal_copilot=False,
        multi_call_resume=False,
    )
    defaults.update(overrides)
    return IntakeV2Settings(**defaults)


@pytest.mark.asyncio
async def test_master_off_logs_skipped_and_does_not_hit_stub(call_and_patient):
    call, patient = call_and_patient
    session = CallSession()
    fake_dispatcher = MagicMock()

    with patch("app.services.dispatcher.get_dispatcher", return_value=fake_dispatcher), \
         patch("app.api.intake.get_intake_status") as mock_status:
        await session._evaluate_intake_v2_gate(call, patient, _settings(master_enabled=False))

    mock_status.assert_not_called()
    fake_dispatcher._log_decision.assert_called_once()
    decision_label, detail = fake_dispatcher._log_decision.call_args.args
    assert decision_label == "intake_v2_skipped"
    assert "reason=master_off" in detail
    assert "call_id=CALL-001" in detail


@pytest.mark.asyncio
async def test_eligible_logs_eligible_and_hits_stub(call_and_patient):
    call, patient = call_and_patient
    session = CallSession()
    fake_dispatcher = MagicMock()
    settings = _settings(master_enabled=True, order_canary_pct=100)

    with patch("app.services.dispatcher.get_dispatcher", return_value=fake_dispatcher):
        await session._evaluate_intake_v2_gate(call, patient, settings)

    fake_dispatcher._log_decision.assert_called_once()
    decision_label, detail = fake_dispatcher._log_decision.call_args.args
    assert decision_label == "intake_v2_eligible"
    assert "call_id=CALL-001" in detail
    assert "order_id=ORD-001" in detail
    # Stub always returns 0 outstanding tasks today.
    assert "outstanding=0" in detail


@pytest.mark.asyncio
async def test_outside_canary_logs_skipped(call_and_patient):
    call, patient = call_and_patient
    session = CallSession()
    fake_dispatcher = MagicMock()
    # master ON but canary 0 — every order falls outside the bucket.
    settings = _settings(master_enabled=True, order_canary_pct=0)

    with patch("app.services.dispatcher.get_dispatcher", return_value=fake_dispatcher), \
         patch("app.api.intake.get_intake_status") as mock_status:
        await session._evaluate_intake_v2_gate(call, patient, settings)

    mock_status.assert_not_called()
    decision_label, detail = fake_dispatcher._log_decision.call_args.args
    assert decision_label == "intake_v2_skipped"
    assert "reason=outside_canary" in detail


@pytest.mark.asyncio
async def test_stub_failure_does_not_raise(call_and_patient):
    call, patient = call_and_patient
    session = CallSession()
    fake_dispatcher = MagicMock()
    settings = _settings(master_enabled=True, order_canary_pct=100)

    async def _boom(_order_id):
        raise RuntimeError("backend down")

    with patch("app.services.dispatcher.get_dispatcher", return_value=fake_dispatcher), \
         patch("app.api.intake.get_intake_status", side_effect=_boom):
        # The orchestrator must not propagate stub failures — the gate is
        # shadow-mode and cannot fail the call.
        await session._evaluate_intake_v2_gate(call, patient, settings)

    decision_label, detail = fake_dispatcher._log_decision.call_args.args
    assert decision_label == "intake_v2_eligible"
    # Sentinel value for failed stub call.
    assert "outstanding=-1" in detail


@pytest.mark.asyncio
async def test_dispatcher_logging_failure_does_not_raise(call_and_patient):
    call, patient = call_and_patient
    session = CallSession()
    fake_dispatcher = MagicMock()
    fake_dispatcher._log_decision.side_effect = RuntimeError("DB down")

    # Even if the dispatcher logger blows up, the gate evaluation must not
    # break the call. v1 fall-through is sacred.
    with patch("app.services.dispatcher.get_dispatcher", return_value=fake_dispatcher):
        await session._evaluate_intake_v2_gate(call, patient, _settings(master_enabled=False))
