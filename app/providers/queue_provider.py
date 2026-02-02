"""Mock queue provider simulating FreePBX/Asterisk — with DB snapshot persistence."""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from app.models import QueueInfo, GlobalQueueState

logger = logging.getLogger(__name__)


class MockQueueProvider:
    """Simulates FreePBX/Asterisk queue monitoring via AMI."""

    def __init__(self):
        self._state = GlobalQueueState(
            queues=[
                QueueInfo(queue_name="scheduling_en", agents_available=2, agents_logged_in=3),
                QueueInfo(queue_name="scheduling_es", agents_available=1, agents_logged_in=1),
                QueueInfo(queue_name="intake", agents_available=1, agents_logged_in=2),
            ]
        )
        self._ami_connected = True
        self._stable_polls = 0

    def get_state(self) -> GlobalQueueState:
        """Get current queue state."""
        return self._state

    async def poll(self) -> GlobalQueueState:
        """Poll queues and update state (called every 10 seconds)."""
        from app.providers.settings_provider import get_settings_provider

        if not self._ami_connected:
            self._state.ami_connected = False
            self._state.outbound_allowed = False
            self._stable_polls = 0
            self._persist_snapshot_bg()
            return self._state

        # Get dynamic thresholds from settings
        settings_provider = get_settings_provider()
        thresholds = await settings_provider.get_thresholds()

        # Aggregate metrics
        self._state.global_calls_waiting = sum(q.calls_waiting for q in self._state.queues)
        self._state.global_oldest_wait_seconds = max(
            (q.oldest_wait_seconds for q in self._state.queues), default=0
        )
        self._state.global_agents_available = sum(q.agents_available for q in self._state.queues)
        self._state.global_agents_logged_in = sum(q.agents_logged_in for q in self._state.queues)
        self._state.last_poll_time = datetime.now()
        self._state.ami_connected = True

        # Check gating conditions using dynamic thresholds
        conditions_met = (
            self._state.global_agents_available >= 1
            and self._state.global_calls_waiting <= thresholds.calls_waiting_threshold
            and self._state.global_oldest_wait_seconds <= thresholds.oldest_wait_threshold_seconds
        )

        if conditions_met:
            self._stable_polls += 1
        else:
            self._stable_polls = 0

        self._state.stable_polls_count = self._stable_polls
        self._state.outbound_allowed = self._stable_polls >= thresholds.stable_polls_required

        self._persist_snapshot_bg()
        return self._state

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
                    global_oldest_wait_seconds=self._state.global_oldest_wait_seconds,
                    global_agents_available=self._state.global_agents_available,
                    global_agents_logged_in=self._state.global_agents_logged_in,
                    outbound_allowed=self._state.outbound_allowed,
                    stable_polls_count=self._state.stable_polls_count,
                    ami_connected=self._state.ami_connected,
                    queues=[
                        {
                            "queue_name": q.queue_name,
                            "calls_waiting": q.calls_waiting,
                            "oldest_wait_seconds": q.oldest_wait_seconds,
                            "agents_available": q.agents_available,
                            "agents_logged_in": q.agents_logged_in,
                        }
                        for q in self._state.queues
                    ],
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist queue snapshot: %s", e)

    def set_queue_state(
        self,
        queue_name: str,
        calls_waiting: Optional[int] = None,
        oldest_wait_seconds: Optional[int] = None,
        agents_available: Optional[int] = None,
        agents_logged_in: Optional[int] = None,
    ):
        """Manually set queue state for testing."""
        for queue in self._state.queues:
            if queue.queue_name == queue_name:
                if calls_waiting is not None:
                    queue.calls_waiting = calls_waiting
                if oldest_wait_seconds is not None:
                    queue.oldest_wait_seconds = oldest_wait_seconds
                if agents_available is not None:
                    queue.agents_available = agents_available
                if agents_logged_in is not None:
                    queue.agents_logged_in = agents_logged_in
                break

    def simulate_busy_queue(self):
        """Simulate a busy queue scenario."""
        for queue in self._state.queues:
            queue.calls_waiting = 5
            queue.oldest_wait_seconds = 60
            queue.agents_available = 0
        self._stable_polls = 0

    def simulate_quiet_queue(self):
        """Simulate a quiet queue scenario (outbound allowed)."""
        for queue in self._state.queues:
            queue.calls_waiting = 0
            queue.oldest_wait_seconds = 0
            queue.agents_available = 2
        # Force stable polls — use default threshold
        self._stable_polls = 3

    def simulate_ami_failure(self):
        """Simulate AMI connection failure."""
        self._ami_connected = False

    def simulate_ami_recovery(self):
        """Simulate AMI connection recovery."""
        self._ami_connected = True

    def reset_with_config(self, queues_config: list[dict], ami_connected: bool):
        """Reset queue state from simulation config."""
        self._state.queues = [
            QueueInfo(
                queue_name=q["queue_name"],
                calls_waiting=q.get("calls_waiting", 0),
                oldest_wait_seconds=q.get("oldest_wait_seconds", 0),
                agents_available=q.get("agents_available", 1),
                agents_logged_in=q.get("agents_logged_in", 1),
            )
            for q in queues_config
        ]
        self._ami_connected = ami_connected
        self._stable_polls = 0

    def add_queue(self, queue_name: str, agents_available: int = 1, agents_logged_in: int = 1):
        """Add a new queue."""
        self._state.queues.append(
            QueueInfo(
                queue_name=queue_name,
                agents_available=agents_available,
                agents_logged_in=agents_logged_in,
            )
        )


# Global instance
_queue_provider: Optional[MockQueueProvider] = None


def get_queue_provider() -> MockQueueProvider:
    """Get the global queue provider instance."""
    global _queue_provider
    if _queue_provider is None:
        _queue_provider = MockQueueProvider()
    return _queue_provider
