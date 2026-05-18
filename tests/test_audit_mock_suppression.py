"""Pin the audit-event suppression behavior for mock_mode calls.

The audit log is patient-facing: every entry implies a real external
action (SMS sent, email sent, HL7 posted). Mock calls don't take those
actions, so their audit events would be misleading noise.

The contract is a single ``mock_mode`` kwarg on ``log_audit_event``.
When True, the function returns without writing. Every notification-
service call site passes ``call.mock_mode`` through.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import audit_service


@pytest.mark.asyncio
async def test_mock_mode_true_writes_nothing():
    """The audit row must NOT be written when mock_mode=True."""
    fake_session = AsyncMock()
    fake_session.add = MagicMock()  # SQLAlchemy session.add is sync
    fake_session.commit = AsyncMock()

    class _SessionCM:
        async def __aenter__(self_inner):
            return fake_session
        async def __aexit__(self_inner, *a):
            return False

    with patch("app.services.audit_service.AsyncSessionLocal", return_value=_SessionCM()):
        await audit_service.log_audit_event(
            event_type="sms", action="send_sms", status="success",
            mock_mode=True,
        )

    fake_session.add.assert_not_called()
    fake_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mock_mode_false_writes_as_before():
    """Default behavior unchanged: mock_mode=False (or absent) writes."""
    fake_session = AsyncMock()
    fake_session.add = MagicMock()  # SQLAlchemy session.add is sync
    fake_session.commit = AsyncMock()

    class _SessionCM:
        async def __aenter__(self_inner):
            return fake_session
        async def __aexit__(self_inner, *a):
            return False

    with patch("app.services.audit_service.AsyncSessionLocal", return_value=_SessionCM()):
        await audit_service.log_audit_event(
            event_type="sms", action="send_sms", status="success",
            mock_mode=False,
        )

    fake_session.add.assert_called_once()
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mock_mode_default_is_false():
    """Existing call sites that don't pass mock_mode keep writing — the
    default must NOT silently start suppressing pre-Phase-B audit events."""
    fake_session = AsyncMock()
    fake_session.add = MagicMock()  # SQLAlchemy session.add is sync
    fake_session.commit = AsyncMock()

    class _SessionCM:
        async def __aenter__(self_inner):
            return fake_session
        async def __aexit__(self_inner, *a):
            return False

    with patch("app.services.audit_service.AsyncSessionLocal", return_value=_SessionCM()):
        await audit_service.log_audit_event(
            event_type="hl7", action="send_status", status="success",
        )

    fake_session.add.assert_called_once()
