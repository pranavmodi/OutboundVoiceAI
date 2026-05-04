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


DEFAULT_CALL_GREETING = (
    "Hi, this is Ashley with Precise Imaging. We received your doctor's "
    "imaging order and need to schedule your appointment. Are you available "
    "now to schedule your appointment?"
)


@dataclass
class DispatcherSettings:
    """Dispatcher configuration parameters."""
    poll_interval: int = 10
    dispatch_timeout: int = 30
    # Max combined (AI + human) attempts before a patient is moved to
    # "Couldnt Schedule".  Configurable separately for Ordered-status
    # patients vs. the remaining statuses (No Show + Needs to Reschedule).
    max_attempts_ordered: int = 4
    max_attempts_other: int = 4
    min_hours_between: int = 6
    verbose_logging: bool = False
    openai_voice: str = "alloy"
    gemini_voice: str = "Aoede"
    call_greeting: str = DEFAULT_CALL_GREETING
    # Phase 7: parallel-call cap. 1 means single-call (legacy behavior).
    # Hard ceiling enforced in the settings provider; keep low (1-10) until
    # Twilio-side concurrency limits and from-number pool are validated.
    max_parallel_calls: int = 1
    # Minimum gap (seconds) between successive call starts. Avoids tripping
    # carrier per-second rate limits when max_parallel_calls > 1.
    dispatch_pacing_seconds: int = 1

    @property
    def max_attempts(self) -> int:
        """Legacy single-value accessor — returns the larger of the two."""
        return max(self.max_attempts_ordered, self.max_attempts_other)

    def max_attempts_for_status(self, radflow_status: str | None) -> int:
        if (radflow_status or "").strip() == "Ordered":
            return self.max_attempts_ordered
        return self.max_attempts_other


@dataclass
class DailyReportConfig:
    """Daily Slack report configuration (posts yesterday's call summary)."""
    enabled: bool = False
    webhook_url: str = ""
    hour: int = 7  # 0-23 local time
    timezone: str = "America/Los_Angeles"


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
    mock_mode: bool = False
    mock_phone: str = ""  # redirect Twilio calls/SMS here when mock_mode=True
    voice_provider: str = "openai"  # "openai" or "gemini"
    daily_report: DailyReportConfig = field(default_factory=DailyReportConfig)
