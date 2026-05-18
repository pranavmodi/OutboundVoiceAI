"""Decides whether a given order should follow the v2 intake path or v1.

The gate is the only place that should consult the v2 feature flags. Every
caller that wants to know "is this order on v2?" funnels through
``evaluate`` (or the bool-only ``is_eligible``). Keeping this in one place
means we can change the flag shape, add tenant logic, or swap the canary
mechanism without hunting through callsites.

Decision rule (all must be true):
1. ``intake_v2.master_enabled`` is True.
2. The order has a non-empty order_id.
3. If ``tenant_allowlist`` is non-empty, the order's tenant is in the list.
   An empty list means "no tenant scoping" — any tenant is allowed.
4. The order's stable hash falls inside ``order_canary_pct``.

Hashing is SHA-256(order_id) mod 100. Same order always lands in the same
bucket, so canary membership is stable across restarts and across calls
within a multi-call workflow.
"""
import hashlib
from dataclasses import dataclass
from typing import Optional

from app.models import IntakeV2Settings


# Reason codes — also serve as the `decision` value in dispatcher_events.
REASON_MASTER_OFF = "master_off"
REASON_NO_ORDER_ID = "no_order_id"
REASON_TENANT_NOT_ALLOWED = "tenant_not_allowed"
REASON_OUTSIDE_CANARY = "outside_canary"
REASON_ELIGIBLE = "eligible"


@dataclass(frozen=True)
class GateDecision:
    eligible: bool
    reason: str  # one of the REASON_* constants above


def _canary_bucket(order_id: str) -> int:
    """Stable 0-99 bucket for an order ID."""
    digest = hashlib.sha256(order_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100


class IntakeV2Gate:
    def __init__(self, settings: IntakeV2Settings):
        self._settings = settings

    def evaluate(self, order_id: Optional[str], tenant_id: Optional[str] = None) -> GateDecision:
        if not self._settings.master_enabled:
            return GateDecision(False, REASON_MASTER_OFF)
        if not order_id:
            return GateDecision(False, REASON_NO_ORDER_ID)
        allowlist = self._settings.tenant_allowlist
        if allowlist and (tenant_id or "") not in allowlist:
            return GateDecision(False, REASON_TENANT_NOT_ALLOWED)
        pct = self._settings.order_canary_pct
        if pct <= 0:
            return GateDecision(False, REASON_OUTSIDE_CANARY)
        if pct >= 100 or _canary_bucket(order_id) < pct:
            return GateDecision(True, REASON_ELIGIBLE)
        return GateDecision(False, REASON_OUTSIDE_CANARY)

    def is_eligible(self, order_id: Optional[str], tenant_id: Optional[str] = None) -> bool:
        return self.evaluate(order_id, tenant_id).eligible
