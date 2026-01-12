"""Queue state model for FreePBX/Asterisk simulation."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class QueueInfo:
    """Individual queue information."""
    queue_name: str
    calls_waiting: int = 0
    oldest_wait_seconds: int = 0
    agents_available: int = 0
    agents_logged_in: int = 0


@dataclass
class GlobalQueueState:
    """Aggregated queue state across all queues."""
    global_calls_waiting: int = 0
    global_oldest_wait_seconds: int = 0
    global_agents_available: int = 0
    global_agents_logged_in: int = 0
    outbound_allowed: bool = False
    stable_polls_count: int = 0
    last_poll_time: Optional[datetime] = None
    ami_connected: bool = True
    queues: list[QueueInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "global_calls_waiting": self.global_calls_waiting,
            "global_oldest_wait_seconds": self.global_oldest_wait_seconds,
            "global_agents_available": self.global_agents_available,
            "global_agents_logged_in": self.global_agents_logged_in,
            "outbound_allowed": self.outbound_allowed,
            "stable_polls_count": self.stable_polls_count,
            "last_poll_time": self.last_poll_time.isoformat() if self.last_poll_time else None,
            "ami_connected": self.ami_connected,
            "queues": [
                {
                    "queue_name": q.queue_name,
                    "calls_waiting": q.calls_waiting,
                    "oldest_wait_seconds": q.oldest_wait_seconds,
                    "agents_available": q.agents_available,
                    "agents_logged_in": q.agents_logged_in,
                }
                for q in self.queues
            ],
        }
