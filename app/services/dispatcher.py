"""Auto-call dispatcher service.

Runs a 10-second polling loop on the backend, evaluates all gating conditions,
and initiates calls directly (backend-driven). The frontend/dashboard is used
only for visibility and audio transport in web-call mode.
"""
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
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
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_MIN_HOURS_BETWEEN = 6
# Backoff window after a FAILED start_call (prevents a broken candidate from being
# hammered on the next tick). Distinct from dispatch pacing, which just spaces
# out normal call starts.
DEFAULT_COOLDOWN_SECONDS = 5
# Phase 4: minimum gap between successive call starts. Guards against burst
# throttling by Twilio when max_parallel_calls is raised. 1s is enough for
# current carrier limits; turn it up if we hit 20429 rate errors.
DEFAULT_DISPATCH_PACING_SECONDS = 1
DECISION_LOG_MAX = 100

# Phase 7: replaced by AutoCallDispatcher.max_parallel_calls (loaded from
# DispatcherSettings). The constant remains as a *fallback default* used
# at __init__ time before settings are first read, and as a tripwire ceiling.
DEFAULT_MAX_PARALLEL_CALLS = 1
MAX_PARALLEL_CALLS_HARD_CEILING = 10  # mirrors settings_provider clamp


class DispatcherState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"


@dataclass
class ActiveCall:
    """Per-call state tracked by the dispatcher."""
    patient_id: str
    patient_name: str
    dispatched_at: float
    phase: str = "dispatched"  # "dispatched" | "active" | "voicemail"
    call_id: Optional[str] = None
    # The lock string we wrote into patients.dialing_call_id when claiming
    # this patient. Starts as a provisional "dispatch-<uuid>" before the
    # real call_id is known, then gets rekeyed to call_id once start_call
    # succeeds. Tracked so re-key/release operations target the right value.
    lock_id: Optional[str] = None


class AutoCallDispatcher:
    """Backend dispatcher that decides WHEN and WHO to call,
    then sends dispatch_call commands to connected frontends."""

    def __init__(self):
        self._state: DispatcherState = DispatcherState.STOPPED
        self._task: Optional[asyncio.Task] = None
        self._active_calls: dict[str, ActiveCall] = {}  # keyed by patient_id
        self._decision_log: deque = deque(maxlen=DECISION_LOG_MAX)
        # Only set by start_call failures — per-patient retry gating uses
        # min_hours_between/last_attempt_at instead of a global cooldown.
        self._last_start_failure_at: Optional[float] = None
        self._last_dispatch_started_at: Optional[float] = None
        # Serializes pick + reserve + start so two concurrent ticks (or a
        # tick + a manual notify_call_started) can't both pass the
        # _occupied_slots check before either has reserved the patient.
        # Created lazily inside the loop so we don't bind to a non-running
        # event loop at module import time.
        self._pick_lock: Optional[asyncio.Lock] = None
        # Configurable parameters
        self.poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS
        self.dispatch_timeout: int = DEFAULT_DISPATCH_TIMEOUT_SECONDS
        self.max_attempts_ordered: int = DEFAULT_MAX_ATTEMPTS
        self.max_attempts_other: int = DEFAULT_MAX_ATTEMPTS
        self.min_hours_between: int = DEFAULT_MIN_HOURS_BETWEEN
        self.cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS
        self.dispatch_pacing_seconds: int = DEFAULT_DISPATCH_PACING_SECONDS
        self.max_parallel_calls: int = DEFAULT_MAX_PARALLEL_CALLS
        self.verbose: bool = False

    @property
    def state(self) -> DispatcherState:
        return self._state

    def start(self):
        """Start the dispatcher polling loop."""
        if self._task and not self._task.done():
            return
        self._state = DispatcherState.RUNNING
        self._task = asyncio.create_task(self._run_loop())
        # Clear any stale dialing locks left over from a crashed previous run.
        from app.services import safe_create_task

        async def _boot_cleanup():
            try:
                cleared = await get_patient_provider().clear_all_dialing()
                if cleared:
                    logger.info("Dispatcher boot: cleared %s stale dialing lock(s)", cleared)
            except Exception as e:
                logger.warning("Dispatcher boot: clear_all_dialing failed: %s", e)

        safe_create_task(_boot_cleanup(), logger, "dispatcher_boot_clear_dialing")
        # Sanity check Twilio capacity — useful when the cap is raised in Phase 7.
        import os as _os
        from_numbers = [n for n in (_os.getenv("TWILIO_FROM_NUMBERS", "") or _os.getenv("TWILIO_FROM_NUMBER", "")).split(",") if n.strip()]
        logger.info(
            "Dispatcher started: max_parallel_calls=%s, twilio_from_numbers=%s",
            self.max_parallel_calls, len(from_numbers) or "(unset)",
        )
        if self.max_parallel_calls > max(len(from_numbers), 1):
            logger.warning(
                "max_parallel_calls=%s exceeds configured Twilio from-numbers=%s — "
                "may trip per-number concurrency limits",
                self.max_parallel_calls, len(from_numbers) or 1,
            )
        self._log_decision("started", "Dispatcher started")

    def stop(self):
        """Stop the dispatcher polling loop."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._state = DispatcherState.STOPPED
        self._active_calls.clear()
        # Drop the lock so the next start() rebuilds a fresh one bound to
        # the (potentially new) event loop.
        self._pick_lock = None
        logger.info("Dispatcher stopped")
        self._log_decision("stopped", "Dispatcher stopped")

    def update_config(self, poll_interval: int, dispatch_timeout: int,
                       max_attempts_ordered: int, max_attempts_other: int,
                       min_hours_between: int,
                       verbose_logging: bool = False,
                       cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
                       max_parallel_calls: int = DEFAULT_MAX_PARALLEL_CALLS,
                       dispatch_pacing_seconds: int = DEFAULT_DISPATCH_PACING_SECONDS):
        """Update dispatcher configuration."""
        self.poll_interval = poll_interval
        self.dispatch_timeout = dispatch_timeout
        self.max_attempts_ordered = max_attempts_ordered
        self.max_attempts_other = max_attempts_other
        self.min_hours_between = min_hours_between
        self.cooldown_seconds = cooldown_seconds
        # Clamp to the same ceiling the settings provider enforces.
        capped = max(1, min(int(max_parallel_calls), MAX_PARALLEL_CALLS_HARD_CEILING))
        if capped != int(max_parallel_calls):
            logger.warning(
                "max_parallel_calls=%s clamped to %s (ceiling=%s)",
                max_parallel_calls, capped, MAX_PARALLEL_CALLS_HARD_CEILING,
            )
        self.max_parallel_calls = capped
        self.dispatch_pacing_seconds = max(0, int(dispatch_pacing_seconds))
        self.verbose = verbose_logging
        self._log_decision("config_updated",
                           f"Config updated: poll={poll_interval}s, timeout={dispatch_timeout}s, "
                           f"max_attempts=ordered:{max_attempts_ordered}/other:{max_attempts_other}, "
                           f"min_hours={min_hours_between}, cooldown={cooldown_seconds}s, "
                           f"max_parallel={self.max_parallel_calls}, "
                           f"pacing={self.dispatch_pacing_seconds}s, verbose={verbose_logging}")

    def restart(self):
        """Restart the dispatcher (stop + start)."""
        self.stop()
        self.start()

    def _verbose_log(self, msg: str):
        """Print a message only when verbose logging is enabled."""
        if self.verbose:
            print(f"[Dispatcher] {msg}")

    async def _run_loop(self):
        """Main polling loop — runs every poll_interval seconds."""
        try:
            while True:
                self._verbose_log(f"Tick start — state={self._state.value} active={len(self._active_calls)}")
                await self._tick()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.info("Dispatcher loop cancelled")
        except Exception as e:
            logger.exception(f"Dispatcher loop error: {e}")
            self._state = DispatcherState.STOPPED

    def _wire_session_callbacks(self, session) -> None:
        """Attach dispatcher-owned callbacks to a CallSession.

        Idempotent for the legacy default session (only sets if unset),
        mandatory for fresh sessions returned by manager.create_session().
        Safe to call repeatedly — both modes converge on the same wiring.
        """
        from app.api.websocket import broadcast_to_dashboards

        async def _on_call_ended(call):
            self.notify_call_ended(getattr(call, "patient_id", None))
            await broadcast_to_dashboards({
                "type": "call_ended",
                "call": call.to_dict(),
            })

        async def _on_status(status):
            await broadcast_to_dashboards({
                "type": "status_update",
                "status": status,
            })

        async def _on_transcript(speaker, text):
            if speaker in ("ai", "patient"):
                await broadcast_to_dashboards({
                    "type": "transcript",
                    "speaker": speaker,
                    "text": text,
                })

        # Don't clobber existing callbacks on the legacy default session
        # (the voice WS attaches its own); for fresh sessions every slot
        # is empty so we win unconditionally.
        if not session.on_call_ended:
            session.on_call_ended = _on_call_ended
        if not session.on_status_update:
            session.on_status_update = _on_status
        if not session.on_transcript_update:
            session.on_transcript_update = _on_transcript

    def _occupied_slots(self) -> int:
        """Count active-call slots against max_parallel_calls.

        Voicemail-phase entries don't count — once we've detected an
        answering machine we consider the patient 'done' from the
        dispatcher's POV and free the slot so the next call can start
        while the AI finishes leaving the message.
        """
        return sum(1 for e in self._active_calls.values() if e.phase != "voicemail")

    async def _tick(self):
        """Single poll cycle: update queue, broadcast state, evaluate conditions."""
        from app.api.websocket import voice_clients, broadcast_to_dashboards
        from app.services.call_orchestrator import get_orchestrator

        # 0. Reap stuck dialing locks so a crashed call doesn't hold its slot forever.
        # Cutoff is generous (30 min) so legitimately long calls — transfers,
        # scheduling conversations — never get their lock cleared while still
        # active. Calls that exceed this should be investigated; they probably
        # represent a hung Twilio session.
        STUCK_DIAL_REAP_SECONDS = max(self.dispatch_timeout + 1800, 1800)
        try:
            cleared = await get_patient_provider().reap_stale_dialing(
                older_than_seconds=STUCK_DIAL_REAP_SECONDS
            )
            if cleared:
                logger.warning("Reaped %s stale dialing lock(s) older than %ss", cleared, STUCK_DIAL_REAP_SECONDS)
        except Exception as e:
            logger.warning("reap_stale_dialing failed: %s", e)

        # 1. Poll queue state
        queue_provider = get_queue_provider()
        queue_state = await queue_provider.poll()

        self._verbose_log(f"Queue poll: ami={queue_state.ami_connected}, outbound_ok={queue_state.outbound_allowed}, agents={queue_state.global_agents_available}")

        now = asyncio.get_event_loop().time()
        tick_decision = None

        # 2. Service per-call state: timeouts, deferred starts (voice client arrived), self-heal.
        settings_provider = get_settings_provider()
        settings = await settings_provider.get_settings()
        call_mode = settings.call_mode or "web"

        patient_provider_for_release = get_patient_provider()

        # Iterate a snapshot because we may mutate the dict.
        for patient_id, entry in list(self._active_calls.items()):
            if entry.phase == "dispatched":
                elapsed = now - entry.dispatched_at
                if elapsed > self.dispatch_timeout:
                    tick_decision = self._log_decision(
                        "dispatch_timeout",
                        f"Dispatch timed out after {self.dispatch_timeout}s for patient {patient_id}")
                    self._active_calls.pop(patient_id, None)
                    try:
                        await patient_provider_for_release.release_dialing(patient_id)
                    except Exception as e:
                        logger.warning("release_dialing failed for %s: %s", patient_id, e)
                    continue
                # Deferred web-mode start: we pre-dispatched and are waiting for a voice client.
                if call_mode == "web" and voice_clients:
                    orchestrator = get_orchestrator()
                    self._wire_session_callbacks(orchestrator)
                    self._verbose_log(f"Deferred start: voice client up, starting call for patient {patient_id}")
                    call = await orchestrator.start_call(patient_id, call_mode=call_mode)
                    if call:
                        self.notify_call_started(patient_id, call_id=call.call_id)
                        self._last_dispatch_started_at = now
                        try:
                            old_lock = entry.lock_id or ""
                            ok = await patient_provider_for_release.rekey_dialing(
                                patient_id, old_lock, call.call_id
                            )
                            if ok:
                                entry.lock_id = call.call_id
                            else:
                                logger.warning(
                                    "dialing lock re-key skipped (provisional lock missing) patient=%s",
                                    patient_id,
                                )
                        except Exception as e:
                            logger.warning("dialing lock re-key failed for %s: %s", patient_id, e)
                        await broadcast_to_dashboards({
                            "type": "call_started",
                            "call": call.to_dict(),
                        })
                        tick_decision = self._log_decision(
                            "call_starting",
                            f"Voice client connected; starting call for patient {patient_id}")
                    else:
                        self._active_calls.pop(patient_id, None)
                        try:
                            await patient_provider_for_release.release_dialing(patient_id)
                        except Exception as e:
                            logger.warning("release_dialing failed for %s: %s", patient_id, e)
                        tick_decision = self._log_decision(
                            "start_failed",
                            f"Failed to start call after voice client connected (patient {patient_id})")
            elif entry.phase == "active":
                # Self-heal: if no call is live in the log for this call_id, drop the entry.
                call_log_provider = get_call_log_provider()
                if entry.call_id and not call_log_provider.has_active_call(entry.call_id):
                    print(f"[Dispatcher] Self-heal: no active call found, dropping entry patient={patient_id}")
                    self._active_calls.pop(patient_id, None)
                    tick_decision = self._log_decision(
                        "self_healed",
                        f"Call ended (missed notification) for patient {patient_id}, returning to idle")
                    await broadcast_to_dashboards({"type": "call_ended", "call": {}})

        # 3. Only evaluate new-call gates if we're running and have a free slot.
        # The pick/reserve/start sequence runs under _pick_lock so two
        # concurrent ticks can't both pass the _occupied_slots check.
        if self._pick_lock is None:
            self._pick_lock = asyncio.Lock()
        # Hand-off variable: when the locked candidate-selection branch
        # successfully reserves a candidate, it stuffs (candidate, lock_id,
        # mode) here. After the lock releases, we run the long-tail
        # start_call() unlocked so other ticks can proceed in parallel.
        dispatch_payload = None
        if self._state != DispatcherState.RUNNING:
            pass
        elif self._occupied_slots() >= self.max_parallel_calls:
            # Tripwire: should be impossible unless a bug lets two dispatches
            # past the gate. Loud log so we notice in staging before prod.
            if self._occupied_slots() > self.max_parallel_calls:
                logger.warning(
                    "Dispatcher exceeded cap: occupied=%s cap=%s active=%s",
                    self._occupied_slots(),
                    self.max_parallel_calls,
                    list(self._active_calls.keys()),
                )
            if tick_decision is None:
                tick_decision = {
                    "decision": "at_capacity",
                    "detail": f"{self._occupied_slots()}/{self.max_parallel_calls} slots in use",
                    "state": self._state.value,
                }
        else:
          async with self._pick_lock:
            # Re-check occupancy under the lock — the previous check is at
            # tick start, but we may have yielded since. Without this, a
            # concurrent notify_call_started could push us past the cap.
            if self._occupied_slots() >= self.max_parallel_calls:
                tick_decision = {
                    "decision": "at_capacity",
                    "detail": f"{self._occupied_slots()}/{self.max_parallel_calls} slots in use (post-lock recheck)",
                    "state": self._state.value,
                }
                # Fall through to broadcast; cap reached after waiting on lock.
                await broadcast_to_dashboards({
                    "type": "queue_update",
                    "queue_state": queue_state.to_dict(),
                    "decision": tick_decision,
                    "active_calls": [
                        {
                            "patient_id": e.patient_id,
                            "patient_name": e.patient_name,
                            "phase": e.phase,
                            "call_id": e.call_id,
                        }
                        for e in self._active_calls.values()
                    ],
                    "max_parallel_calls": self.max_parallel_calls,
                })
                return

            call_log_provider = get_call_log_provider()

            self._verbose_log(
                f"Sources: queue={settings.queue_source}, patients={settings.patient_source}, "
                f"call_mode={settings.call_mode}, scenario={settings.active_scenario_id or 'none'}"
            )

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
                if queue_state.global_agents_available == 0:
                    reason = "No agents available"
                elif queue_state.global_calls_waiting > 0:
                    reason = f"{queue_state.global_calls_waiting} calls waiting, holdtime {queue_state.global_max_holdtime}s"
                elif queue_state.stable_polls_count < 3:
                    reason = f"Waiting for stable queue ({queue_state.stable_polls_count}/3 polls)"
                else:
                    reason = "Queue thresholds not met"
                tick_decision = self._log_decision("blocked", reason)

            # Redundant safety net while call_log_provider is still singleton-slotted.
            # Phase 2 removes the single-slot flag so this check goes away.
            elif call_log_provider.has_active_call() and not self._active_calls:
                tick_decision = self._log_decision("blocked", "Call already in progress (outside dispatcher)")

            # Post-start-failure backoff: don't hammer after a broken start_call.
            elif self._last_start_failure_at is not None:
                elapsed = now - self._last_start_failure_at
                remaining = self.cooldown_seconds - elapsed
                if remaining > 0:
                    tick_decision = self._log_decision(
                        "blocked", f"Backoff after failed start ({int(remaining)}s remaining)")
                else:
                    self._last_start_failure_at = None

            # Dispatch pacing — keep at least N seconds between consecutive starts
            # so bursts don't trip Twilio per-second rate limits.
            if tick_decision is None and self._last_dispatch_started_at is not None:
                elapsed = now - self._last_dispatch_started_at
                remaining = self.dispatch_pacing_seconds - elapsed
                if remaining > 0:
                    tick_decision = self._log_decision(
                        "blocked", f"Dispatch pacing ({int(remaining) + 1}s until next start)")

            if tick_decision is None:
                self._verbose_log("All gates passed — looking for candidate patient")

                # 4. Get next candidate patient
                patient_provider = get_patient_provider()

                candidate = None
                if not settings.mock_mode:
                    from app.services.transfer_service import resolve_transfer_queue_for_language, find_queue_by_name
                    queue = await patient_provider.get_outbound_queue(
                        max_attempts_ordered=self.max_attempts_ordered,
                        max_attempts_other=self.max_attempts_other,
                        min_hours_between=self.min_hours_between)
                    for prospect in queue:
                        # Skip patients we already have an in-flight call for.
                        if prospect.patient_id in self._active_calls:
                            continue
                        target_queue = resolve_transfer_queue_for_language(prospect.language)
                        queue_info = find_queue_by_name(queue_state, target_queue)
                        if queue_info and queue_info.AvailableAgents >= 1:
                            candidate = prospect
                            break
                        else:
                            self._verbose_log(
                                f"Skipping {prospect.name} — no agents in queue {target_queue} "
                                f"for language {prospect.language.value if hasattr(prospect.language, 'value') else prospect.language}"
                            )
                else:
                    candidate = await patient_provider.get_next_candidate(
                        max_attempts_ordered=self.max_attempts_ordered,
                        max_attempts_other=self.max_attempts_other,
                        min_hours_between=self.min_hours_between)
                    # Guard the mock path against re-picking an in-flight patient.
                    if candidate and candidate.patient_id in self._active_calls:
                        candidate = None

                if candidate is None:
                    self._verbose_log("No eligible candidate found")
                    tick_decision = self._log_decision("no_candidate", "No eligible patients in queue")
                else:
                    # Pre-reserve the patient so a second tick (or manual call) can't
                    # pick the same row. The lock_id is provisional until we have a
                    # real call_id; we re-key it once start_call returns.
                    import uuid as _uuid
                    provisional_lock = f"dispatch-{_uuid.uuid4().hex[:12]}"
                    reserved = await patient_provider.reserve_for_dialing(
                        candidate.patient_id, provisional_lock
                    )
                    if not reserved:
                        self._verbose_log(
                            f"Candidate {candidate.patient_id} already reserved by another claim — skipping tick"
                        )
                        tick_decision = self._log_decision(
                            "blocked",
                            f"Candidate {candidate.name} was locked by a concurrent claim")
                        await broadcast_to_dashboards({
                            "type": "queue_update",
                            "queue_state": queue_state.to_dict(),
                            "decision": tick_decision,
                            "active_calls": [
                                {
                                    "patient_id": e.patient_id,
                                    "patient_name": e.patient_name,
                                    "phase": e.phase,
                                    "call_id": e.call_id,
                                }
                                for e in self._active_calls.values()
                            ],
                            "max_parallel_calls": self.max_parallel_calls,
                        })
                        return

                    # Final cap recheck — between the post-lock recheck and now,
                    # we yielded inside reserve_for_dialing/get_outbound_queue/etc.,
                    # so notify_call_started from a manual web call may have
                    # bumped _occupied_slots. Bail if the new entry would push us
                    # past the cap.
                    if self._occupied_slots() + 1 > self.max_parallel_calls:
                        try:
                            await patient_provider.release_dialing(candidate.patient_id)
                        except Exception as e:
                            logger.warning("release_dialing failed during cap-overshoot bail for %s: %s",
                                           candidate.patient_id, e)
                        tick_decision = self._log_decision(
                            "blocked",
                            f"Cap reached after reserve ({self._occupied_slots()}/{self.max_parallel_calls}) — releasing claim")
                        await broadcast_to_dashboards({
                            "type": "queue_update",
                            "queue_state": queue_state.to_dict(),
                            "decision": tick_decision,
                            "active_calls": [
                                {
                                    "patient_id": e.patient_id,
                                    "patient_name": e.patient_name,
                                    "phase": e.phase,
                                    "call_id": e.call_id,
                                }
                                for e in self._active_calls.values()
                            ],
                            "max_parallel_calls": self.max_parallel_calls,
                        })
                        return

                    # Reserve the slot in-memory NOW (atomic from this coroutine's POV).
                    self._active_calls[candidate.patient_id] = ActiveCall(
                        patient_id=candidate.patient_id,
                        patient_name=candidate.name,
                        dispatched_at=now,
                        phase="dispatched",
                        lock_id=provisional_lock,
                    )

                    print(f"[Dispatcher] Candidate found: {candidate.name} ({candidate.phone}), mode={call_mode}")

                    if call_mode == "web" and not voice_clients:
                        # Pre-dispatch only: actual start_call happens in a future
                        # tick once the voice client connects. Nothing more to do
                        # under the lock; broadcast and exit.
                        print(f"[Dispatcher] Dispatch: pre-dispatching patient={candidate.patient_id} (waiting for voice client)")
                        tick_decision = self._log_decision(
                            "waiting_for_voice_client",
                            f"Ready to call {candidate.name}; requesting voice client to connect")
                        await broadcast_to_dashboards({
                            "type": "dispatch_call",
                            "patient_id": candidate.patient_id,
                            "patient_name": candidate.name,
                        })
                    else:
                        # Hand off to the post-lock section. start_call is the
                        # long-running step (Twilio API + media wait); running
                        # it outside the lock lets concurrent ticks dispatch
                        # other patients in parallel.
                        tick_decision = self._log_decision(
                            "starting_call",
                            f"Starting call to {candidate.name} ({candidate.phone}, mode={call_mode})")
                        dispatch_payload = (candidate, provisional_lock, call_mode)

        # --- Lock released. start_call runs unlocked so other ticks can proceed. ---
        if dispatch_payload is not None:
            candidate, provisional_lock, call_mode = dispatch_payload
            print(f"[Dispatcher] Dispatch: starting call patient={candidate.patient_id} mode={call_mode}")

            if call_mode == "twilio":
                from app.services.call_orchestrator import get_manager
                orchestrator = get_manager().create_session()
                self._wire_session_callbacks(orchestrator)
            else:
                orchestrator = get_orchestrator()
                self._wire_session_callbacks(orchestrator)

            try:
                call = await orchestrator.start_call(candidate.patient_id, call_mode=call_mode)
            except Exception as e:
                # Don't let an orchestrator exception kill the dispatcher loop.
                logger.exception("start_call raised for patient %s: %s", candidate.patient_id, e)
                call = None

            patient_provider = get_patient_provider()
            if call is None:
                # Release slot + dialing lock and arm the start-failure backoff.
                self._active_calls.pop(candidate.patient_id, None)
                try:
                    await patient_provider.release_dialing(candidate.patient_id)
                except Exception as e:
                    logger.warning("release_dialing failed for %s: %s", candidate.patient_id, e)
                self._last_start_failure_at = now
                error_reason = getattr(orchestrator, "_last_start_error", None) or "unknown reason"
                tick_decision = self._log_decision(
                    "start_failed",
                    f"Failed to start call to {candidate.name}: {error_reason} (backoff {self.cooldown_seconds}s)")
            else:
                self.notify_call_started(candidate.patient_id, call_id=call.call_id)
                self._last_dispatch_started_at = now
                try:
                    ok = await patient_provider.rekey_dialing(
                        candidate.patient_id, provisional_lock, call.call_id
                    )
                    if ok:
                        entry = self._active_calls.get(candidate.patient_id)
                        if entry is not None:
                            entry.lock_id = call.call_id
                    else:
                        logger.warning(
                            "dialing lock re-key skipped (provisional lock missing) patient=%s",
                            candidate.patient_id,
                        )
                except Exception as e:
                    logger.warning("dialing lock re-key failed for %s: %s", candidate.patient_id, e)
                await broadcast_to_dashboards({
                    "type": "call_started",
                    "call": call.to_dict(),
                })

        # 5. Broadcast queue_update + decision + parallel-call state to dashboards.
        await broadcast_to_dashboards({
            "type": "queue_update",
            "queue_state": queue_state.to_dict(),
            "decision": tick_decision,
            "active_calls": [
                {
                    "patient_id": e.patient_id,
                    "patient_name": e.patient_name,
                    "phase": e.phase,
                    "call_id": e.call_id,
                }
                for e in self._active_calls.values()
            ],
            "max_parallel_calls": self.max_parallel_calls,
        })

    def notify_call_started(self, patient_id: str, call_id: Optional[str] = None):
        """Mark a patient's call as active (from dispatch or manual WS start)."""
        entry = self._active_calls.get(patient_id)
        if entry is None:
            # Manual call started outside the dispatcher (e.g. WS /ws/voice start_call).
            # Warn if this manual call pushes us past the cap — the UI should
            # have prevented it but we want loud breadcrumbs for any backend
            # path that bypasses the gate.
            occupied_before = self._occupied_slots()
            if occupied_before + 1 > self.max_parallel_calls:
                logger.warning(
                    "Manual call_started for patient=%s pushes occupied=%s past cap=%s",
                    patient_id, occupied_before + 1, self.max_parallel_calls,
                )
            entry = ActiveCall(
                patient_id=patient_id,
                patient_name="",
                dispatched_at=asyncio.get_event_loop().time(),
                phase="active",
                call_id=call_id,
            )
            self._active_calls[patient_id] = entry
            print(f"[Dispatcher] call_started patient={patient_id} call_id={call_id} source=manual slots={self._occupied_slots()}/{self.max_parallel_calls}")
            self._log_decision("call_started", f"Manual call started for patient {patient_id} (call_id={call_id})")
            return
        entry.phase = "active"
        if call_id:
            entry.call_id = call_id
        print(f"[Dispatcher] call_started patient={patient_id} call_id={call_id} slots={self._occupied_slots()}/{self.max_parallel_calls}")
        self._log_decision("call_started", f"Call started patient={patient_id} call_id={call_id}")

    def notify_voicemail_started(self, patient_id: str):
        """Mark a call as 'leaving voicemail' so its slot is freed for the
        next dispatch while the AI finishes speaking the message.
        The underlying call stays live until end_call() fires normally."""
        entry = self._active_calls.get(patient_id)
        if entry is None:
            return
        if entry.phase == "voicemail":
            return
        entry.phase = "voicemail"
        print(f"[Dispatcher] Voicemail phase patient={patient_id} — slot released for next dispatch")
        self._log_decision(
            "voicemail_started",
            f"AMD detected voicemail for patient {patient_id}; slot released for next dispatch")

    def notify_call_ended(self, patient_id: Optional[str] = None):
        """Release a call slot. If patient_id is None, release the first active entry
        (backward compat for callers that don't track which call ended)."""
        if patient_id is None:
            if not self._active_calls:
                return
            # Drop the oldest entry — at max=1 this is unambiguous.
            patient_id = next(iter(self._active_calls))
        entry = self._active_calls.pop(patient_id, None)
        if entry is None:
            return
        print(f"[Dispatcher] call_ended patient={patient_id} call_id={entry.call_id} phase={entry.phase} slots={self._occupied_slots()}/{self.max_parallel_calls}")
        self._log_decision("call_ended", f"Call ended patient={patient_id} call_id={entry.call_id}")
        # Release the DB-level dialing lock so the next tick can re-pick this patient.
        # Only build the coroutine if we can schedule it — otherwise Python warns
        # about un-awaited coroutines in sync test paths.
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                return
        except RuntimeError:
            return
        from app.services import safe_create_task

        async def _release():
            try:
                await get_patient_provider().release_dialing(patient_id)
            except Exception as e:
                logger.warning("release_dialing failed for %s after call_ended: %s", patient_id, e)

        safe_create_task(_release(), logger, f"dispatcher_release_dialing patient={patient_id}")

    def _log_decision(self, decision: str, detail: str) -> dict:
        """Append to the circular decision buffer, persist to DB, and return the entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": decision,
            "detail": detail,
            "state": self._state.value,
        }
        self._decision_log.append(entry)
        print(f"[Dispatcher] {decision}: {detail}")

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
        active_calls = [
            {
                "patient_id": e.patient_id,
                "patient_name": e.patient_name,
                "phase": e.phase,
                "call_id": e.call_id,
                "dispatched_at": e.dispatched_at,
            }
            for e in self._active_calls.values()
        ]
        # Backward-compat: `dispatched_patient_id` used to be the single in-flight patient.
        # Return the first entry's id (or None) until callers migrate to `active_calls`.
        first_pid = next(iter(self._active_calls), None)
        return {
            "state": self._state.value,
            "dispatched_patient_id": first_pid,
            "active_calls": active_calls,
            "max_parallel_calls": self.max_parallel_calls,
            "running": self._task is not None and not self._task.done(),
            "recent_decisions": list(self._decision_log)[-5:],
            "config": {
                "poll_interval": self.poll_interval,
                "dispatch_timeout": self.dispatch_timeout,
                "max_attempts_ordered": self.max_attempts_ordered,
                "max_attempts_other": self.max_attempts_other,
                "min_hours_between": self.min_hours_between,
                "cooldown_seconds": self.cooldown_seconds,
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
