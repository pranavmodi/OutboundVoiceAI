"""Status and channel constants — aligned with cancellation-backfill-spec.md."""
from enum import Enum


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    CANCELED = "canceled"
    COMPLETED = "completed"
    CLOSED = "closed"


class CampaignStatus(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    FILLED = "Filled"
    CLOSED_NO_CANDIDATES = "ClosedNoCandidates"
    CLOSED_EXHAUSTED = "ClosedExhausted"
    CLOSED_MAX_WAVES_REACHED = "ClosedMaxWavesReached"
    CLOSED_SLOT_NO_LONGER_AVAILABLE = "ClosedSlotNoLongerAvailable"
    CLOSED_MANUALLY = "ClosedManually"
    CLOSED_SYSTEM_ERROR = "ClosedSystemError"


class CandidateEligibilityStatus(str, Enum):
    ELIGIBLE = "Eligible"
    EXCLUDED_NO_SHOW = "ExcludedNoShow"
    EXCLUDED_INVALID_CONTACT = "ExcludedInvalidContact"
    EXCLUDED_ALREADY_CONTACTED = "ExcludedAlreadyContacted"
    EXCLUDED_NOT_AFTER_OPEN_SLOT = "ExcludedNotAfterOpenSlot"
    QUEUED = "Queued"
    TEXT_SENT = "TextSent"
    CALL_PLACED = "CallPlaced"
    VOICEMAIL_LEFT = "VoicemailLeft"
    NO_RESPONSE = "NoResponse"
    INTERESTED = "Interested"
    DECLINED = "Declined"
    SELECTED_WINNER = "SelectedWinner"
    LOST_SLOT = "LostSlot"
    ERROR = "Error"


class ActionChannel(str, Enum):
    SMS = "SMS"
    VOICE = "Voice"
    SYSTEM = "System"
