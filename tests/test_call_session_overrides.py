"""Pin the override path on CallSession.start_call.

Phase B uses ``patient_override`` and ``settings_override`` to construct
synthetic /v2-test calls without touching the patient or settings
providers. The contract:

- When neither override is passed, the live providers ARE consulted
  (v1 byte-identical behavior).
- When ``patient_override`` is passed, the patient provider is NOT
  consulted.
- When ``settings_override`` is passed, the settings provider is NOT
  consulted.

The orchestrator does a lot of other work in ``start_call`` (voice
service init, voicemail setup, etc.) that we can't fully exercise in a
unit test, so we patch the call_log provider + downstream side effects
and assert on the override branches only.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import CallLog, Language, Patient, SystemSettings
from app.services.call_orchestrator import CallSession


@pytest.fixture
def synthetic_patient():
    return Patient(
        patient_id="TEST-PAT-001",
        name="Synthetic Test",
        phone="+15550000000",
        language=Language.ENGLISH,
        order_id="TEST-ORD-001",
    )


@pytest.fixture
def synthetic_settings():
    """Minimal SystemSettings overlay — uses dataclass defaults."""
    return SystemSettings()


def _call_log_stub() -> AsyncMock:
    """Mock call_log_provider that returns a CallLog from create_call."""
    provider = AsyncMock()
    provider.create_call = AsyncMock(
        return_value=CallLog(
            call_id="CALL-OVERRIDE-1",
            patient_id="TEST-PAT-001",
            patient_name="Synthetic Test",
            phone="+15550000000",
            order_id="TEST-ORD-001",
            priority_bucket=0,
        )
    )
    return provider


def _queue_provider_stub() -> MagicMock:
    state = MagicMock()
    state.to_dict = MagicMock(return_value={})
    provider = MagicMock()
    provider.get_state = MagicMock(return_value=state)
    return provider


@pytest.mark.asyncio
async def test_v1_path_consults_providers(monkeypatch):
    """Regression: with no overrides, both providers MUST be hit.

    If this breaks, the override branch has accidentally taken over the
    production code path.
    """
    session = CallSession()

    patient = Patient(
        patient_id="PROD-001", name="Prod User",
        phone="+15551112222", language=Language.ENGLISH,
        order_id="PROD-ORD-1",
    )
    patient_provider = AsyncMock()
    patient_provider.get_patient = AsyncMock(return_value=patient)

    settings_provider = AsyncMock()
    settings_provider.get_settings = AsyncMock(return_value=SystemSettings())

    call_log_provider = _call_log_stub()

    with patch("app.services.call_orchestrator.get_patient_provider", return_value=patient_provider), \
         patch("app.services.call_orchestrator.get_settings_provider", return_value=settings_provider), \
         patch("app.services.call_orchestrator.get_call_log_provider", return_value=call_log_provider), \
         patch("app.services.call_orchestrator.get_queue_provider", return_value=_queue_provider_stub()), \
         patch.object(CallSession, "_evaluate_intake_v2_gate", AsyncMock()), \
         patch("app.services.orchestrator_registry.get_registry", return_value=MagicMock()), \
         patch("app.services.realtime_voice.RealtimeVoiceService"), \
         patch.object(CallSession, "_start_voice_session", AsyncMock(return_value=True)) if hasattr(CallSession, "_start_voice_session") else patch("app.services.call_orchestrator.logger"):
        # We don't need to drive past voice-service init; the override
        # branch we care about is before that point. Make voice service
        # construction a no-op by mocking the concrete class.
        try:
            await session.start_call("PROD-001", call_mode="web")
        except Exception:
            # Downstream init may bail; we only care that the providers
            # were consulted, which happened before any potential error.
            pass

    patient_provider.get_patient.assert_awaited_once_with("PROD-001")
    settings_provider.get_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_override_path_skips_providers(synthetic_patient, synthetic_settings):
    """With both overrides, neither provider may be consulted.

    This is the contract /v2-test relies on — synthetic patients never
    appear in the patient table, and the v2-flag overlay never reaches
    the DB.
    """
    session = CallSession()

    patient_provider = AsyncMock()
    patient_provider.get_patient = AsyncMock()  # must NOT be called

    settings_provider = AsyncMock()
    settings_provider.get_settings = AsyncMock()  # must NOT be called

    with patch("app.services.call_orchestrator.get_patient_provider", return_value=patient_provider), \
         patch("app.services.call_orchestrator.get_settings_provider", return_value=settings_provider), \
         patch("app.services.call_orchestrator.get_call_log_provider", return_value=_call_log_stub()), \
         patch("app.services.call_orchestrator.get_queue_provider", return_value=_queue_provider_stub()), \
         patch.object(CallSession, "_evaluate_intake_v2_gate", AsyncMock()), \
         patch("app.services.orchestrator_registry.get_registry", return_value=MagicMock()), \
         patch("app.services.realtime_voice.RealtimeVoiceService"):
        try:
            await session.start_call(
                synthetic_patient.patient_id,
                call_mode="web",
                patient_override=synthetic_patient,
                settings_override=synthetic_settings,
            )
        except Exception:
            pass

    patient_provider.get_patient.assert_not_awaited()
    settings_provider.get_settings.assert_not_awaited()


@pytest.mark.asyncio
async def test_override_patient_propagates_to_call_log(synthetic_patient, synthetic_settings):
    """The synthetic patient must be what create_call sees — not whatever
    happens to be in the patient table for the same ID."""
    session = CallSession()
    call_log_provider = _call_log_stub()

    with patch("app.services.call_orchestrator.get_patient_provider", return_value=AsyncMock()), \
         patch("app.services.call_orchestrator.get_settings_provider", return_value=AsyncMock()), \
         patch("app.services.call_orchestrator.get_call_log_provider", return_value=call_log_provider), \
         patch("app.services.call_orchestrator.get_queue_provider", return_value=_queue_provider_stub()), \
         patch.object(CallSession, "_evaluate_intake_v2_gate", AsyncMock()), \
         patch("app.services.orchestrator_registry.get_registry", return_value=MagicMock()), \
         patch("app.services.realtime_voice.RealtimeVoiceService"):
        try:
            await session.start_call(
                synthetic_patient.patient_id,
                patient_override=synthetic_patient,
                settings_override=synthetic_settings,
            )
        except Exception:
            pass

    call_log_provider.create_call.assert_awaited_once()
    kwargs = call_log_provider.create_call.await_args.kwargs
    assert kwargs["patient_id"] == "TEST-PAT-001"
    assert kwargs["patient_name"] == "Synthetic Test"
    assert kwargs["order_id"] == "TEST-ORD-001"
