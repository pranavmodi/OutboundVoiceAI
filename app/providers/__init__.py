"""Mock providers for external systems."""
from .queue_provider import MockQueueProvider, get_queue_provider
from .patient_provider import MockPatientProvider, get_patient_provider
from .call_log_provider import CallLogProvider, get_call_log_provider
from .settings_provider import SettingsProvider, get_settings_provider

__all__ = [
    "MockQueueProvider",
    "MockPatientProvider",
    "CallLogProvider",
    "SettingsProvider",
    "get_queue_provider",
    "get_patient_provider",
    "get_call_log_provider",
    "get_settings_provider",
]
