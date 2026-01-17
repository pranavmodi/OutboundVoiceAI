"""Mock queue provider simulating FreePBX/Asterisk."""
from datetime import datetime
from typing import Optional
from app.models import QueueInfo, GlobalQueueState


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

    def poll(self) -> GlobalQueueState:
        """Poll queues and update state (called every 10 seconds)."""
        # Import here to avoid circular imports
        from app.providers.settings_provider import get_settings_provider

        if not self._ami_connected:
            self._state.ami_connected = False
            self._state.outbound_allowed = False
            self._stable_polls = 0
            return self._state

        # Get dynamic thresholds from settings
        settings_provider = get_settings_provider()
        thresholds = settings_provider.get_thresholds()

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

        return self._state

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
        self.poll()

    def simulate_busy_queue(self):
        """Simulate a busy queue scenario."""
        for queue in self._state.queues:
            queue.calls_waiting = 5
            queue.oldest_wait_seconds = 60
            queue.agents_available = 0
        self._stable_polls = 0
        self.poll()

    def simulate_quiet_queue(self):
        """Simulate a quiet queue scenario (outbound allowed)."""
        # Import here to avoid circular imports
        from app.providers.settings_provider import get_settings_provider

        for queue in self._state.queues:
            queue.calls_waiting = 0
            queue.oldest_wait_seconds = 0
            queue.agents_available = 2
        # Force stable polls to allow outbound using dynamic threshold
        settings_provider = get_settings_provider()
        thresholds = settings_provider.get_thresholds()
        self._stable_polls = thresholds.stable_polls_required
        self.poll()

    def simulate_ami_failure(self):
        """Simulate AMI connection failure."""
        self._ami_connected = False
        self.poll()

    def simulate_ami_recovery(self):
        """Simulate AMI connection recovery."""
        self._ami_connected = True
        self.poll()

    def add_queue(self, queue_name: str, agents_available: int = 1, agents_logged_in: int = 1):
        """Add a new queue."""
        self._state.queues.append(
            QueueInfo(
                queue_name=queue_name,
                agents_available=agents_available,
                agents_logged_in=agents_logged_in,
            )
        )
        self.poll()


# Global instance
_queue_provider: Optional[MockQueueProvider] = None


def get_queue_provider() -> MockQueueProvider:
    """Get the global queue provider instance."""
    global _queue_provider
    if _queue_provider is None:
        _queue_provider = MockQueueProvider()
        # Initialize with a few polls to allow outbound
        for _ in range(3):
            _queue_provider.poll()
    return _queue_provider
