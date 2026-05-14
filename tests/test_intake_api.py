"""Tests for the stubbed v2 intake API."""
import pytest

from app.api.intake import IntakeStatusResponse, get_intake_status


@pytest.mark.asyncio
async def test_stub_returns_no_outstanding_tasks():
    resp = await get_intake_status("ORD-42")
    assert isinstance(resp, IntakeStatusResponse)
    assert resp.order_id == "ORD-42"
    assert resp.outstanding_tasks == []
    assert resp.is_complete is True


@pytest.mark.asyncio
async def test_stub_echoes_arbitrary_order_id():
    resp = await get_intake_status("anything-goes-here")
    assert resp.order_id == "anything-goes-here"
