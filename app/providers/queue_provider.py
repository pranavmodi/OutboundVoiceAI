"""Queue providers — Base, Mock (simulation), and Live (FreePBX HTTP)."""
import asyncio
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import httpx

from app.models import QueueInfo, GlobalQueueState

logger = logging.getLogger(__name__)

FREEPBX_QUEUE_URL = os.getenv(
    "FREEPBX_QUEUE_URL", "http://10.254.99.40:2001/queuestatus.php"
)


class BaseQueueProvider(ABC):
    """Shared gating, aggregation, and snapshot persistence."""

    def __init__(self):
        self._state = GlobalQueueState()
        self._stable_polls = 0

    def get_state(self) -> GlobalQueueState:
        return self._state

    @abstractmethod
    async def poll(self) -> GlobalQueueState:
        ...

    async def _evaluate_gating(self):
        from app.providers.settings_provider import get_settings_provider

        thresholds = await get_settings_provider().get_thresholds()

        self._state.global_calls_waiting = sum(q.Calls for q in self._state.queues)
        self._state.global_max_holdtime = max(
            (q.Holdtime for q in self._state.queues), default=0
        )
        self._state.global_agents_available = sum(
            q.AvailableAgents for q in self._state.queues
        )
        self._state.last_poll_time = datetime.now()
        self._state.ami_connected = True

        conditions_met = (
            self._state.global_agents_available >= 1
            and self._state.global_calls_waiting <= thresholds.calls_waiting_threshold
            and self._state.global_max_holdtime
            <= thresholds.holdtime_threshold_seconds
        )

        if conditions_met:
            self._stable_polls += 1
        else:
            self._stable_polls = 0

        self._state.stable_polls_count = self._stable_polls
        self._state.outbound_allowed = (
            self._stable_polls >= thresholds.stable_polls_required
        )

        self._persist_snapshot_bg()

    def _persist_snapshot_bg(self):
        """Fire-and-forget persist of current state to queue_state_snapshots."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._save_snapshot())
        except RuntimeError:
            pass

    async def _save_snapshot(self):
        try:
            from app.db import AsyncSessionLocal
            from app.db.models import QueueStateSnapshotRow

            async with AsyncSessionLocal() as session:
                row = QueueStateSnapshotRow(
                    global_calls_waiting=self._state.global_calls_waiting,
                    global_max_holdtime=self._state.global_max_holdtime,
                    global_agents_available=self._state.global_agents_available,
                    outbound_allowed=self._state.outbound_allowed,
                    stable_polls_count=self._state.stable_polls_count,
                    ami_connected=self._state.ami_connected,
                    queues=[
                        {
                            "Event": q.Event,
                            "Queue": q.Queue,
                            "Max": q.Max,
                            "Strategy": q.Strategy,
                            "Calls": q.Calls,
                            "Holdtime": q.Holdtime,
                            "TalkTime": q.TalkTime,
                            "Completed": q.Completed,
                            "Abandoned": q.Abandoned,
                            "ServiceLevel": q.ServiceLevel,
                            "ServicelevelPerf": q.ServicelevelPerf,
                            "ServicelevelPerf2": q.ServicelevelPerf2,
                            "Weight": q.Weight,
                            "AvailableAgents": q.AvailableAgents,
                        }
                        for q in self._state.queues
                    ],
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist queue snapshot: %s", e)


class MockQueueProvider(BaseQueueProvider):
    """Simulates FreePBX/Asterisk queue monitoring via AMI."""

    def __init__(self):
        super().__init__()
        self._state.queues = [
            QueueInfo(Queue="9006", AvailableAgents=2),   # Scheduling English
            QueueInfo(Queue="9009", AvailableAgents=1),   # Scheduling Spanish
            QueueInfo(Queue="9012", AvailableAgents=1),   # Scheduling Mandarin
        ]
        self._ami_connected = True

    async def poll(self) -> GlobalQueueState:
        if not self._ami_connected:
            self._state.ami_connected = False
            self._state.outbound_allowed = False
            self._stable_polls = 0
            self._persist_snapshot_bg()
            return self._state

        await self._evaluate_gating()
        return self._state

    def set_queue_state(
        self,
        queue_name: str,
        Calls: Optional[int] = None,
        Holdtime: Optional[int] = None,
        AvailableAgents: Optional[int] = None,
    ):
        """Manually set queue state for testing."""
        for queue in self._state.queues:
            if queue.Queue == queue_name:
                if Calls is not None:
                    queue.Calls = Calls
                if Holdtime is not None:
                    queue.Holdtime = Holdtime
                if AvailableAgents is not None:
                    queue.AvailableAgents = AvailableAgents
                break

    def simulate_busy_queue(self):
        for queue in self._state.queues:
            queue.Calls = 5
            queue.Holdtime = 60
            queue.AvailableAgents = 0
        self._stable_polls = 0

    def simulate_quiet_queue(self):
        for queue in self._state.queues:
            queue.Calls = 0
            queue.Holdtime = 0
            queue.AvailableAgents = 2
        self._stable_polls = 3

    def simulate_ami_failure(self):
        self._ami_connected = False

    def simulate_ami_recovery(self):
        self._ami_connected = True

    def reset_with_config(self, queues_config: list[dict], ami_connected: bool):
        self._state.queues = [
            QueueInfo(
                Event=q.get("Event", "QueueParams"),
                Queue=q.get("Queue", ""),
                Max=q.get("Max", 0),
                Strategy=q.get("Strategy", "ringall"),
                Calls=q.get("Calls", 0),
                Holdtime=q.get("Holdtime", 0),
                TalkTime=q.get("TalkTime", 0),
                Completed=q.get("Completed", 0),
                Abandoned=q.get("Abandoned", 0),
                ServiceLevel=q.get("ServiceLevel", 135),
                ServicelevelPerf=q.get("ServicelevelPerf", 0.0),
                ServicelevelPerf2=q.get("ServicelevelPerf2", 0.0),
                Weight=q.get("Weight", 0),
                AvailableAgents=q.get("AvailableAgents", 0),
            )
            for q in queues_config
        ]
        self._ami_connected = ami_connected
        self._stable_polls = 0

    def add_queue(self, queue_name: str, available_agents: int = 1):
        self._state.queues.append(
            QueueInfo(Queue=queue_name, AvailableAgents=available_agents)
        )


class LiveQueueProvider(BaseQueueProvider):
    """Fetches real queue data from FreePBX queuestatus.php."""

    def __init__(self, url: str = FREEPBX_QUEUE_URL):
        super().__init__()
        self._url = url
        self._client = httpx.AsyncClient(timeout=5.0)
        # Only include these queues in gating/aggregation (empty = all).
        raw = os.getenv("MONITORED_QUEUES", "").strip()
        self._monitored: set[str] = (
            {q.strip() for q in raw.split(",") if q.strip()} if raw else set()
        )

    async def poll(self) -> GlobalQueueState:
        try:
            resp = await self._client.get(self._url)
            resp.raise_for_status()
            data = resp.json()  # {"9006": {...}, "9007": {...}}
            all_queues = [
                QueueInfo(
                    Event=v.get("Event", "QueueParams"),
                    Queue=v.get("Queue", qid),
                    Max=int(v.get("Max", 0)),
                    Strategy=v.get("Strategy", "ringall"),
                    Calls=int(v.get("Calls", 0)),
                    Holdtime=int(v.get("Holdtime", 0)),
                    TalkTime=int(v.get("TalkTime", 0)),
                    Completed=int(v.get("Completed", 0)),
                    Abandoned=int(v.get("Abandoned", 0)),
                    ServiceLevel=int(v.get("ServiceLevel", 135)),
                    ServicelevelPerf=float(v.get("ServicelevelPerf", 0.0)),
                    ServicelevelPerf2=float(v.get("ServicelevelPerf2", 0.0)),
                    Weight=int(v.get("Weight", 0)),
                    AvailableAgents=int(v.get("AvailableAgents", 0)),
                )
                for qid, v in data.items()
            ]
            # Filter to scheduling queues only so billing/records don't
            # affect gating or transfer availability.
            if self._monitored:
                self._state.queues = [
                    q for q in all_queues if q.Queue in self._monitored
                ]
            else:
                self._state.queues = all_queues
            await self._evaluate_gating()
        except Exception as e:
            logger.warning("FreePBX poll failed: %s", e)
            self._state.ami_connected = False
            self._state.outbound_allowed = False
            self._stable_polls = 0
            self._persist_snapshot_bg()
        return self._state


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------
_mock_provider: Optional[MockQueueProvider] = None
_live_provider: Optional[LiveQueueProvider] = None
_active_source: str = "simulation"


def _get_mock_provider() -> MockQueueProvider:
    global _mock_provider
    if _mock_provider is None:
        _mock_provider = MockQueueProvider()
    return _mock_provider


def _get_live_provider() -> LiveQueueProvider:
    global _live_provider
    if _live_provider is None:
        _live_provider = LiveQueueProvider()
    return _live_provider


def get_queue_provider() -> BaseQueueProvider:
    """Get the active queue provider based on queue_source setting."""
    if _active_source == "live":
        return _get_live_provider()
    return _get_mock_provider()


def get_mock_queue_provider() -> MockQueueProvider:
    """Always returns the mock provider (for simulation endpoints)."""
    return _get_mock_provider()


def set_queue_source(source: str):
    """Switch the active queue source ('simulation' or 'live')."""
    global _active_source
    if source not in ("simulation", "live"):
        raise ValueError(f"Invalid queue source: {source!r}")
    _active_source = source
    logger.info("Queue source set to: %s", source)
