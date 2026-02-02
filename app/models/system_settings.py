"""System settings models."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BusinessHours:
    """Business hours configuration."""
    start_time: str = "08:00"  # HH:MM format
    end_time: str = "17:00"    # HH:MM format
    enabled: bool = False
    timezone: str = "America/New_York"


@dataclass
class QueueThresholds:
    """Queue gating thresholds for outbound calls."""
    calls_waiting_threshold: int = 1
    holdtime_threshold_seconds: int = 30
    stable_polls_required: int = 3


@dataclass
class SystemSettings:
    """Main system settings."""
    system_enabled: bool = True
    business_hours: BusinessHours = field(default_factory=BusinessHours)
    queue_thresholds: QueueThresholds = field(default_factory=QueueThresholds)
    allow_live_calls: bool = False
    allowed_phones: List[str] = field(default_factory=list)
    queue_source: str = "simulation"
    patient_source: str = "simulation"
