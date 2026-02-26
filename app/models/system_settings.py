"""System settings models."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class HolidayEntry:
    """Holiday calendar entry."""
    date: str  # YYYY-MM-DD
    name: str
    recurring: bool = True


@dataclass
class BusinessHours:
    """Business hours configuration."""
    start_time: str = "08:00"  # HH:MM format
    end_time: str = "17:00"    # HH:MM format
    enabled: bool = False
    timezone: str = "America/New_York"
    days_of_week: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri (0=Mon, 6=Sun)
    holidays: List[HolidayEntry] = field(default_factory=list)


@dataclass
class QueueThresholds:
    """Queue gating thresholds for outbound calls."""
    calls_waiting_threshold: int = 1
    holdtime_threshold_seconds: int = 30
    stable_polls_required: int = 3


@dataclass
class DispatcherSettings:
    """Dispatcher configuration parameters."""
    poll_interval: int = 10
    dispatch_timeout: int = 30
    max_attempts: int = 3
    min_hours_between: int = 6


@dataclass
class SystemSettings:
    """Main system settings."""
    system_enabled: bool = True
    business_hours: BusinessHours = field(default_factory=BusinessHours)
    queue_thresholds: QueueThresholds = field(default_factory=QueueThresholds)
    dispatcher_settings: DispatcherSettings = field(default_factory=DispatcherSettings)
    allow_live_calls: bool = False
    allowed_phones: List[str] = field(default_factory=list)
    queue_source: str = "simulation"
    patient_source: str = "simulation"
    active_scenario_id: Optional[str] = None
    call_mode: str = "web"  # "web" or "twilio"
