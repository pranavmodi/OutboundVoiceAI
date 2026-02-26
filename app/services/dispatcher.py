"""Auto-call dispatcher service.

Runs a 10-second polling loop on the backend, evaluates all gating conditions,
and initiates calls directly (backend-driven). The frontend/dashboard is used
only for visibility and audio transport in web-call mode.
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

DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_DISPATCH_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MIN_HOURS_BETWEEN = 6
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
        # Configurable parameters
        self.poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS
        self.dispatch_timeout: int = DEFAULT_DISPATCH_TIMEOUT_SECONDS
        self.max_attempts: int = DEFAULT_MAX_ATTEMPTS
        self.min_hours_between: int = DEFAULT_MIN_HOURS_BETWEEN

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

    def update_config(self, poll_interval: int, dispatch_timeout: int,
                       max_attempts: int, min_hours_between: int):
        """Update dispatcher configuration."""
        self.poll_interval = poll_interval
        self.dispatch_timeout = dispatch_timeout
        self.max_attempts = max_attempts
        self.min_hours_between = min_hours_between
        self._log_decision("config_updated",
                           f"Config updated: poll={poll_interval}s, timeout={dispatch_timeout}s, "
                           f"max_attempts={max_attempts}, min_hours={min_hours_between}")

    def restart(self):
        """Restart the dispatcher (stop + start)."""
        self.stop()
        self.start()

    async def _run_loop(self):
        """Main polling loop — runs every poll_interval seconds."""
        try:
            while True:
                await self._tick()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.info("Dispatcher loop cancelled")
        except Exception as e:
            logger.exception(f"Dispatcher loop error: {e}")
            self._state = DispatcherState.STOPPED

    async def _tick(self):
        """Single poll cycle: update queue, broadcast state, evaluate conditions."""
        from app.api.websocket import dashboard_clients, voice_clients, broadcast_to_dashboards
        from app.services.call_orchestrator import get_orchestrator

        # 1. Poll queue state
        queue_provider = get_queue_provider()
        queue_state = await queue_provider.poll()

        # Track the decision made this tick (broadcast at end)
        tick_decision = None

        # 3. If DISPATCHED, either start call when prerequisites are met, or check timeout
        if self._state == DispatcherState.DISPATCHED:
            if self._dispatched_at is not None:
                elapsed = asyncio.get_event_loop().time() - self._dispatched_at
                if elapsed > self.dispatch_timeout:
                    tick_decision = self._log_decision(
                        "dispatch_timeout",
                        f"Dispatch timed out after {self.dispatch_timeout}s "
                        f"for patient {self._dispatched_patient_id}")
                    self._state = DispatcherState.IDLE
                    self._dispatched_at = None
                    self._dispatched_patient_id = None
                else:
                    # If we're in web mode and a voice client has connected, start the call now
                    settings_provider = get_settings_provider()
                    settings = await settings_provider.get_settings()
                    call_mode = settings.call_mode or "web"
                    if call_mode == "web" and voice_clients and self._dispatched_patient_id:
                        orchestrator = get_orchestrator()
                        call = await orchestrator.start_call(self._dispatched_patient_id, call_mode=call_mode)
                        if call:
                            self.notify_call_started(self._dispatched_patient_id)
                            await broadcast_to_dashboards({
                                "type": "call_started",
                                "call": call.to_dict(),
                            })
                            tick_decision = self._log_decision(
                                "call_starting",
                                f"Voice client connected; starting call for patient {self._dispatched_patient_id}")
                        else:
                            # Failed to start; reset state
                            self._state = DispatcherState.IDLE
                            self._dispatched_at = None
                            self._dispatched_patient_id = None
                            tick_decision = self._log_decision(
                                "start_failed",
                                "Failed to start call after voice client connected")
                    else:
                        tick_decision = {"decision": "waiting", "detail": "Waiting for voice client or prerequisites", "state": self._state.value}

        # 4. If CALL_ACTIVE, skip
        elif self._state == DispatcherState.CALL_ACTIVE:
            tick_decision = {"decision": "call_active", "detail": "Call in progress, skipping", "state": self._state.value}

        # 5. If not IDLE, skip
        elif self._state != DispatcherState.IDLE:
            pass

        else:
            # 6. Evaluate all gating conditions
            settings_provider = get_settings_provider()
            settings = await settings_provider.get_settings()
            call_log_provider = get_call_log_provider()

            # system_enabled
            if not settings.system_enabled:
                tick_decision = self._log_decision("blocked", "System is disabled")

            # is_within_business_hours
            elif (business_hours_reason := await settings_provider.get_business_hours_block_reason()):
                tick_decision = self._log_decision("blocked", business_hours_reason)

            # ami_connected (reflected in queue state)
            elif not queue_state.ami_connected:
                tick_decision = self._log_decision("blocked", "AMI connection lost")

            # outbound_allowed (agents, waits, stability)
            elif not queue_state.outbound_allowed:
                # Provide specific reason why outbound is blocked
                if queue_state.global_agents_available == 0:
                    reason = "No agents available"
                elif queue_state.global_calls_waiting > 0:
                    reason = f"{queue_state.global_calls_waiting} calls waiting, holdtime {queue_state.global_max_holdtime}s"
                elif queue_state.stable_polls_count < 3:
                    reason = f"Waiting for stable queue ({queue_state.stable_polls_count}/3 polls)"
                else:
                    reason = "Queue thresholds not met"
                tick_decision = self._log_decision("blocked", reason)

            # has_active_call
            elif call_log_provider.has_active_call():
                tick_decision = self._log_decision("blocked", "Call already in progress")

            else:
                # 7. Get next candidate patient
                patient_provider = get_patient_provider()
                candidate = await patient_provider.get_next_candidate(
                    max_attempts=self.max_attempts,
                    min_hours_between=self.min_hours_between)

                if candidate is None:
                    tick_decision = self._log_decision("no_candidate", "No eligible patients in queue")

                else:
                    # 8. Determine call mode and required connectivity
                    settings_provider = get_settings_provider()
                    settings = await settings_provider.get_settings()
                    call_mode = settings.call_mode or "web"

                    # In web mode, if no voice client is connected, pre-dispatch to trigger the frontend to connect voice
                    if call_mode == "web" and not voice_clients:
                        self._state = DispatcherState.DISPATCHED
                        self._dispatched_at = asyncio.get_event_loop().time()
                        self._dispatched_patient_id = candidate.patient_id
                        tick_decision = self._log_decision(
                            "waiting_for_voice_client",
                            f"Ready to call {candidate.name}; requesting voice client to connect")
                        await broadcast_to_dashboards({
                            "type": "dispatch_call",
                            "patient_id": candidate.patient_id,
                            "patient_name": candidate.name,
                        })
                    else:
                        # 9. Start call directly (backend-driven)
                        self._state = DispatcherState.DISPATCHED
                        self._dispatched_at = asyncio.get_event_loop().time()
                        self._dispatched_patient_id = candidate.patient_id

                        tick_decision = self._log_decision(
                            "starting_call",
                            f"Starting call to {candidate.name} ({candidate.phone}, mode={call_mode})")

                        orchestrator = get_orchestrator()
                        call = await orchestrator.start_call(candidate.patient_id, call_mode=call_mode)

                        if call is None:
                            # Failed to start; reset state
                            self._state = DispatcherState.IDLE
                            self._dispatched_at = None
                            self._dispatched_patient_id = None
                            tick_decision = self._log_decision(
                                "start_failed",
                                f"Failed to start call to {candidate.name}")
                        else:
                            # Mark active immediately; voice/ws callbacks will also keep state in sync
                            self.notify_call_started(candidate.patient_id)
                            await broadcast_to_dashboards({
                                "type": "call_started",
                                "call": call.to_dict(),
                            })

        # 2. Broadcast queue_update + decision to all dashboards
        await broadcast_to_dashboards({
            "type": "queue_update",
            "queue_state": queue_state.to_dict(),
            "decision": tick_decision,
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

    def _log_decision(self, decision: str, detail: str) -> dict:
        """Append to the circular decision buffer, persist to DB, and return the entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": decision,
            "detail": detail,
            "state": self._state.value,
        }
        self._decision_log.append(entry)
        logger.info(f"[Dispatcher] {decision}: {detail}")

        # Fire-and-forget DB persistence
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from app.services import safe_create_task
                safe_create_task(
                    self._persist_event(decision, detail),
                    logger,
                    f"dispatcher_persist_event decision={decision}",
                )
        except RuntimeError:
            pass

        return entry

    async def _persist_event(self, decision: str, detail: str):
        """Persist a dispatcher event to the database."""
        try:
            from app.db import AsyncSessionLocal
            from app.db.models import DispatcherEventRow

            async with AsyncSessionLocal() as session:
                row = DispatcherEventRow(
                    decision=decision,
                    detail=detail,
                    state=self._state.value,
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist dispatcher event: %s", e)

    def get_status(self) -> dict:
        """Return current dispatcher status for API."""
        return {
            "state": self._state.value,
            "dispatched_patient_id": self._dispatched_patient_id,
            "running": self._task is not None and not self._task.done(),
            "recent_decisions": list(self._decision_log)[-5:],
            "config": {
                "poll_interval": self.poll_interval,
                "dispatch_timeout": self.dispatch_timeout,
                "max_attempts": self.max_attempts,
                "min_hours_between": self.min_hours_between,
            },
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
