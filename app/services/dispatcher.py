"""Auto-call dispatcher service.

Runs a 10-second polling loop on the backend, evaluates all gating conditions,
and signals the frontend to initiate calls via the dashboard WebSocket.
"""
import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.providers import (
    get_queue_provider,
    get_patient_provider,
    get_call_log_provider,
    get_settings_provider,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 10
DISPATCH_TIMEOUT_SECONDS = 30
DECISION_LOG_MAX = 100


class DispatcherState(str, Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    DISPATCHED = "dispatched"
    CALL_ACTIVE = "call_active"


class AutoCallDispatcher:
    """Backend dispatcher that decides WHEN and WHO to call,
    then sends dispatch_call commands to connected frontends."""

    def __init__(self):
        self._state: DispatcherState = DispatcherState.STOPPED
        self._task: Optional[asyncio.Task] = None
        self._dispatched_at: Optional[float] = None
        self._dispatched_patient_id: Optional[str] = None
        self._decision_log: deque = deque(maxlen=DECISION_LOG_MAX)

    @property
    def state(self) -> DispatcherState:
        return self._state

    def start(self):
        """Start the dispatcher polling loop."""
        if self._task and not self._task.done():
            return
        self._state = DispatcherState.IDLE
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Dispatcher started")
        self._log_decision("started", "Dispatcher started")

    def stop(self):
        """Stop the dispatcher polling loop."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._state = DispatcherState.STOPPED
        self._dispatched_at = None
        self._dispatched_patient_id = None
        logger.info("Dispatcher stopped")
        self._log_decision("stopped", "Dispatcher stopped")

    async def _run_loop(self):
        """Main polling loop — runs every POLL_INTERVAL_SECONDS."""
        try:
            while True:
                await self._tick()
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Dispatcher loop cancelled")
        except Exception as e:
            logger.exception(f"Dispatcher loop error: {e}")
            self._state = DispatcherState.STOPPED

    async def _tick(self):
        """Single poll cycle: update queue, broadcast state, evaluate conditions."""
        from app.api.websocket import dashboard_clients, broadcast_to_dashboards

        # 1. Poll queue state
        queue_provider = get_queue_provider()
        queue_state = queue_provider.poll()

        # 2. Broadcast queue_update to all dashboards
        await broadcast_to_dashboards({
            "type": "queue_update",
            "queue_state": queue_state.to_dict(),
        })

        # 3. If DISPATCHED, check timeout
        if self._state == DispatcherState.DISPATCHED:
            if self._dispatched_at is not None:
                elapsed = asyncio.get_event_loop().time() - self._dispatched_at
                if elapsed > DISPATCH_TIMEOUT_SECONDS:
                    self._log_decision("dispatch_timeout",
                                       f"Dispatch timed out after {DISPATCH_TIMEOUT_SECONDS}s "
                                       f"for patient {self._dispatched_patient_id}")
                    self._state = DispatcherState.IDLE
                    self._dispatched_at = None
                    self._dispatched_patient_id = None
                else:
                    return  # Still waiting for frontend to start call

        # 4. If CALL_ACTIVE, skip
        if self._state == DispatcherState.CALL_ACTIVE:
            return

        # 5. If not IDLE, skip (e.g. STOPPED shouldn't reach here, but guard)
        if self._state != DispatcherState.IDLE:
            return

        # 6. Evaluate all gating conditions
        settings_provider = get_settings_provider()
        settings = settings_provider.get_settings()
        call_log_provider = get_call_log_provider()

        # system_enabled
        if not settings.system_enabled:
            self._log_decision("blocked", "system_enabled is false")
            return

        # is_within_business_hours
        if not settings_provider.is_within_business_hours():
            self._log_decision("blocked", "Outside business hours")
            return

        # ami_connected (reflected in queue state)
        if not queue_state.ami_connected:
            self._log_decision("blocked", "AMI not connected")
            return

        # outbound_allowed (agents, waits, stability)
        if not queue_state.outbound_allowed:
            self._log_decision("blocked", "Outbound not allowed by queue state")
            return

        # has_active_call
        if call_log_provider.has_active_call():
            self._log_decision("blocked", "Call already active")
            return

        # 7. Get next candidate patient
        patient_provider = get_patient_provider()
        candidate = patient_provider.get_next_candidate(max_attempts=3, min_hours_between=6)

        if candidate is None:
            self._log_decision("no_candidate", "No eligible patients in queue")
            return

        # 8. Check that at least one dashboard frontend is connected
        if not dashboard_clients:
            self._log_decision("no_frontend_connected",
                               f"Would dispatch {candidate.name} but no frontend connected")
            return

        # 9. Dispatch!
        self._state = DispatcherState.DISPATCHED
        self._dispatched_at = asyncio.get_event_loop().time()
        self._dispatched_patient_id = candidate.patient_id

        self._log_decision("dispatched",
                           f"Dispatching call to {candidate.name} (id={candidate.patient_id})")

        await broadcast_to_dashboards({
            "type": "dispatch_call",
            "patient_id": candidate.patient_id,
            "patient_name": candidate.name,
        })

    def notify_call_started(self, patient_id: str):
        """Transition DISPATCHED → CALL_ACTIVE when the frontend starts the call."""
        if self._state == DispatcherState.DISPATCHED:
            self._state = DispatcherState.CALL_ACTIVE
            self._dispatched_at = None
            self._log_decision("call_started",
                               f"Call started for patient {patient_id}")
        elif self._state == DispatcherState.IDLE:
            # Manual call started outside dispatcher
            self._state = DispatcherState.CALL_ACTIVE
            self._log_decision("call_started",
                               f"Manual call started for patient {patient_id}")

    def notify_call_ended(self):
        """Transition CALL_ACTIVE → IDLE when the call ends."""
        if self._state in (DispatcherState.CALL_ACTIVE, DispatcherState.DISPATCHED):
            self._state = DispatcherState.IDLE
            self._dispatched_at = None
            self._dispatched_patient_id = None
            self._log_decision("call_ended", "Call ended, returning to idle")

    def _log_decision(self, decision: str, detail: str):
        """Append to the circular decision buffer."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": decision,
            "detail": detail,
            "state": self._state.value,
        }
        self._decision_log.append(entry)
        logger.info(f"[Dispatcher] {decision}: {detail}")

    def get_status(self) -> dict:
        """Return current dispatcher status for API."""
        return {
            "state": self._state.value,
            "dispatched_patient_id": self._dispatched_patient_id,
            "running": self._task is not None and not self._task.done(),
            "recent_decisions": list(self._decision_log)[-5:],
        }

    def get_decision_log(self) -> list:
        """Return full decision log for debugging."""
        return list(self._decision_log)


# Singleton
_dispatcher: Optional[AutoCallDispatcher] = None


def get_dispatcher() -> AutoCallDispatcher:
    """Get the global dispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AutoCallDispatcher()
    return _dispatcher
