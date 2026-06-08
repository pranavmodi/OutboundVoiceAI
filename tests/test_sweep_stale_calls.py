"""Tests for sweep_stale_in_progress_calls — the startup cleanup that
marks orphaned in_progress call_log rows as DISCONNECTED.

We patch AsyncSessionLocal to avoid hitting a real DB; the test verifies
the SQL filter + state transitions, not the SQL execution itself.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import CallOutcome
from app.providers.call_log_provider import CallLogProvider


def _fake_row(call_id: str, outcome: str, started_minutes_ago: int):
    """Minimal CallLogRow stand-in. Only fields the sweep touches."""
    row = MagicMock()
    row.call_id = call_id
    row.outcome = outcome
    row.started_at = datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)
    row.ended_at = None
    row.duration_seconds = 0
    row.call_status = "in_progress"
    row.call_disposition = "in_progress"
    return row


def _session_cm_with_rows(rows):
    """Builds an AsyncSessionLocal mock that returns the given rows from
    execute(...).scalars().all() and supports .commit()."""
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self_inner):
            return session
        async def __aexit__(self_inner, *a):
            return False

    return _CM(), session


@pytest.mark.asyncio
async def test_sweep_marks_stale_row_completed():
    """Stale row → outcome=COMPLETED (not FAILED/TECHNICAL_ERROR). The
    history badge reads as a normal completed call; diagnostic detail
    lives in the dispatcher_events / voice_error log for that call_id."""
    stale = _fake_row("CALL-STALE", "in_progress", started_minutes_ago=15)
    cm, session = _session_cm_with_rows([stale])
    provider = CallLogProvider()
    provider._active_call_ids["CALL-STALE"] = None

    with patch("app.providers.call_log_provider.AsyncSessionLocal", return_value=cm):
        count = await provider.sweep_stale_in_progress_calls(older_than_minutes=10)

    assert count == 1
    assert stale.outcome == CallOutcome.COMPLETED.value
    assert stale.ended_at is not None
    assert stale.duration_seconds >= 15 * 60  # at least 15 minutes
    assert stale.call_status == "called"
    assert stale.call_disposition == "completed"
    session.commit.assert_awaited_once()
    # Active-call set is purged so dispatcher slots free up.
    assert "CALL-STALE" not in provider._active_call_ids


@pytest.mark.asyncio
async def test_sweep_with_no_rows_does_not_commit():
    """Empty result → no commit, count=0. Idempotent on clean DB."""
    cm, session = _session_cm_with_rows([])
    provider = CallLogProvider()

    with patch("app.providers.call_log_provider.AsyncSessionLocal", return_value=cm):
        count = await provider.sweep_stale_in_progress_calls()

    assert count == 0
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_handles_row_without_started_at():
    """A row with NULL started_at (shouldn't happen but defensive) gets
    marked disconnected without an arithmetic crash. Duration stays 0."""
    weird = _fake_row("CALL-WEIRD", "in_progress", started_minutes_ago=20)
    weird.started_at = None
    cm, session = _session_cm_with_rows([weird])
    provider = CallLogProvider()

    with patch("app.providers.call_log_provider.AsyncSessionLocal", return_value=cm):
        count = await provider.sweep_stale_in_progress_calls()

    assert count == 1
    assert weird.outcome == CallOutcome.COMPLETED.value
    # Started_at was None, so duration shouldn't be touched.
    assert weird.duration_seconds == 0


@pytest.mark.asyncio
async def test_sweep_drops_call_ids_from_active_set():
    """Even if the same row had been re-added to _active_call_ids by the
    in-memory tracker, the sweep must purge it so the dispatcher's
    concurrency counter doesn't keep counting ghosts."""
    stale = _fake_row("CALL-G1", "in_progress", started_minutes_ago=30)
    stale2 = _fake_row("CALL-G2", "in_progress", started_minutes_ago=30)
    cm, _session = _session_cm_with_rows([stale, stale2])
    provider = CallLogProvider()
    provider._active_call_ids["CALL-G1"] = None
    provider._active_call_ids["CALL-G2"] = None
    provider._active_call_ids["CALL-OK"] = None  # legitimate active call — keep

    with patch("app.providers.call_log_provider.AsyncSessionLocal", return_value=cm):
        await provider.sweep_stale_in_progress_calls()

    assert "CALL-G1" not in provider._active_call_ids
    assert "CALL-G2" not in provider._active_call_ids
    assert "CALL-OK" in provider._active_call_ids
