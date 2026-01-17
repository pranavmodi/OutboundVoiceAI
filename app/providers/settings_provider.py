"""Settings provider for system configuration."""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.models import BusinessHours, QueueThresholds, SystemSettings


# Common timezones for selection
COMMON_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "Pacific/Honolulu",
    "UTC",
]


class SettingsProvider:
    """Manages system settings with in-memory storage."""

    def __init__(self):
        self._settings = SystemSettings()

    def get_settings(self) -> SystemSettings:
        """Get current system settings."""
        return self._settings

    def update_settings(self, settings: SystemSettings) -> SystemSettings:
        """Update all system settings."""
        self._settings = settings
        return self._settings

    def set_system_enabled(self, enabled: bool) -> SystemSettings:
        """Enable or disable the system."""
        self._settings.system_enabled = enabled
        return self._settings

    def update_business_hours(self, business_hours: BusinessHours) -> SystemSettings:
        """Update business hours settings."""
        self._settings.business_hours = business_hours
        return self._settings

    def update_queue_thresholds(self, thresholds: QueueThresholds) -> SystemSettings:
        """Update queue thresholds."""
        self._settings.queue_thresholds = thresholds
        return self._settings

    def is_within_business_hours(self) -> bool:
        """Check if current time is within configured business hours."""
        bh = self._settings.business_hours

        if not bh.enabled:
            return True  # If business hours not enabled, always allow

        try:
            tz = ZoneInfo(bh.timezone)
            now = datetime.now(tz)
            current_time = now.strftime("%H:%M")

            return bh.start_time <= current_time <= bh.end_time
        except Exception:
            # If timezone parsing fails, default to allowing calls
            return True

    def can_make_outbound_call(self) -> bool:
        """Check if all conditions allow making an outbound call."""
        if not self._settings.system_enabled:
            return False

        if not self.is_within_business_hours():
            return False

        return True

    def get_thresholds(self) -> QueueThresholds:
        """Get current queue thresholds."""
        return self._settings.queue_thresholds


# Global instance
_settings_provider: Optional[SettingsProvider] = None


def get_settings_provider() -> SettingsProvider:
    """Get the global settings provider instance."""
    global _settings_provider
    if _settings_provider is None:
        _settings_provider = SettingsProvider()
    return _settings_provider
