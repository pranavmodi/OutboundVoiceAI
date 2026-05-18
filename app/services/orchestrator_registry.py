"""Registry mapping live calls to their CallOrchestrator session.

Phase 2 introduces this so Twilio webhooks (AMD, status callbacks) can be
routed to the correct in-flight call instead of assuming a single global
orchestrator. At MAX_PARALLEL_CALLS == 1 the registry holds at most one
entry; it exists now so the routing infrastructure is already in place
when we lift the cap.

NOTE: today all lookups converge on the same singleton CallOrchestrator
because the class itself has not yet been split into per-call sessions
(that is the deferred Phase 2b). For now the registry simply confirms
that the incoming Twilio SID matches the orchestrator's current call.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.services.call_orchestrator import CallOrchestrator

logger = logging.getLogger(__name__)


class OrchestratorRegistry:
    """Indexes live call sessions by call_id, twilio SID, and patient_id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_call_id: dict[str, "CallOrchestrator"] = {}
        self._by_twilio_sid: dict[str, str] = {}  # sid → call_id
        self._by_patient_id: dict[str, str] = {}  # patient_id → call_id
        self._by_stream_id: dict[str, str] = {}   # twilio media stream_id → call_id

    def register(self, call_id: str, patient_id: str, session: "CallOrchestrator") -> None:
        with self._lock:
            self._by_call_id[call_id] = session
            if patient_id:
                self._by_patient_id[patient_id] = call_id
        logger.debug("Registered session call_id=%s patient_id=%s", call_id, patient_id)

    def bind_twilio_sid(self, call_id: str, twilio_sid: str) -> None:
        if not call_id or not twilio_sid:
            return
        with self._lock:
            self._by_twilio_sid[twilio_sid] = call_id
        logger.debug("Bound twilio_sid=%s to call_id=%s", twilio_sid, call_id)

    def bind_stream_id(self, call_id: str, stream_id: str) -> None:
        """Bind a Twilio media stream_id to a session so the /ws/twilio-media
        handler can route end-of-stream cleanup to the right call at max>1."""
        if not call_id or not stream_id:
            return
        with self._lock:
            self._by_stream_id[stream_id] = call_id
        logger.debug("Bound stream_id=%s to call_id=%s", stream_id, call_id)

    def unregister(self, call_id: str) -> None:
        with self._lock:
            self._by_call_id.pop(call_id, None)
            # Drop reverse indexes pointing at this call_id.
            for sid, cid in list(self._by_twilio_sid.items()):
                if cid == call_id:
                    self._by_twilio_sid.pop(sid, None)
            for pid, cid in list(self._by_patient_id.items()):
                if cid == call_id:
                    self._by_patient_id.pop(pid, None)
            for stream, cid in list(self._by_stream_id.items()):
                if cid == call_id:
                    self._by_stream_id.pop(stream, None)
        logger.debug("Unregistered call_id=%s", call_id)

    def by_call_id(self, call_id: str) -> Optional["CallOrchestrator"]:
        with self._lock:
            return self._by_call_id.get(call_id)

    def by_twilio_sid(self, twilio_sid: str) -> Optional["CallOrchestrator"]:
        with self._lock:
            call_id = self._by_twilio_sid.get(twilio_sid)
            if call_id is None:
                return None
            return self._by_call_id.get(call_id)

    def by_patient_id(self, patient_id: str) -> Optional["CallOrchestrator"]:
        with self._lock:
            call_id = self._by_patient_id.get(patient_id)
            if call_id is None:
                return None
            return self._by_call_id.get(call_id)

    def by_stream_id(self, stream_id: str) -> Optional["CallOrchestrator"]:
        with self._lock:
            call_id = self._by_stream_id.get(stream_id)
            if call_id is None:
                return None
            return self._by_call_id.get(call_id)

    def active_call_ids(self) -> list[str]:
        with self._lock:
            return list(self._by_call_id.keys())

    def active_count(self) -> int:
        with self._lock:
            return len(self._by_call_id)

    def clear(self) -> None:
        """Reset the registry (tests, dispatcher restart)."""
        with self._lock:
            self._by_call_id.clear()
            self._by_twilio_sid.clear()
            self._by_patient_id.clear()
            self._by_stream_id.clear()


_registry: Optional[OrchestratorRegistry] = None


def get_registry() -> OrchestratorRegistry:
    global _registry
    if _registry is None:
        _registry = OrchestratorRegistry()
    return _registry
