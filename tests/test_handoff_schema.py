"""Tests for the M1 handoff payload schema."""
import pytest
from pydantic import ValidationError

from app.models.handoff import HandoffPayload, TransferReason


def test_minimal_payload_validates():
    payload = HandoffPayload(
        call_id="CALL-1",
        transfer_reason=TransferReason.NO_INTAKE_NEEDED,
    )
    assert payload.call_id == "CALL-1"
    assert payload.identity_verified is False
    assert payload.transferred_at is not None


def test_all_m1_reasons_accepted():
    for reason in TransferReason:
        HandoffPayload(call_id="CALL-1", transfer_reason=reason)


def test_unknown_reason_rejected():
    with pytest.raises(ValidationError):
        HandoffPayload(call_id="CALL-1", transfer_reason="NOT_A_REASON")


def test_round_trip_through_json():
    original = HandoffPayload(
        call_id="CALL-1",
        order_id="ORD-1",
        patient_id="PAT-1",
        transfer_reason=TransferReason.IDENTITY_VERIFICATION_FAILED,
        identity_verified=False,
        call_summary="DOB mismatch",
    )
    parsed = HandoffPayload.model_validate_json(original.model_dump_json())
    assert parsed.transfer_reason is TransferReason.IDENTITY_VERIFICATION_FAILED
    assert parsed.order_id == "ORD-1"
    assert parsed.call_summary == "DOB mismatch"
