"""Patient data model."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class Language(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"
    CHINESE = "zh"


class IntakeStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class RadflowStatus(str, Enum):
    """Patient lifecycle status sourced from RadFlow."""
    ORDERED = "Ordered"
    NO_SHOW = "No Show"
    NEEDS_RESCHEDULE = "Needs to Reschedule"
    COULDNT_SCHEDULE = "Couldnt Schedule"


# Priority rank used for queue ordering. Lower = higher priority.
# Any status not in this map is excluded from the outbound queue.
STATUS_RANK: dict[str, int] = {
    RadflowStatus.ORDERED.value: 1,
    RadflowStatus.NO_SHOW.value: 2,
    RadflowStatus.NEEDS_RESCHEDULE.value: 3,
}


def normalize_radflow_status(raw: Optional[str]) -> Optional[str]:
    """Map a raw RadFlow status string to our canonical RadflowStatus value.

    RadFlow sends these in inconsistent casing (e.g. 'NO SHOW', 'Ordered').
    Returns None if the status is unrecognized, so callers can decide
    whether to default or skip the patient.
    """
    if not raw:
        return None
    key = raw.strip().upper()
    mapping = {
        "ORDERED": RadflowStatus.ORDERED.value,
        "NO SHOW": RadflowStatus.NO_SHOW.value,
        "NEEDS TO RESCHEDULE": RadflowStatus.NEEDS_RESCHEDULE.value,
        "COULDNT SCHEDULE": RadflowStatus.COULDNT_SCHEDULE.value,
        "COULD NOT SCHEDULE": RadflowStatus.COULDNT_SCHEDULE.value,
        "COULDNOT SCHEDULED": RadflowStatus.COULDNT_SCHEDULE.value,
    }
    return mapping.get(key)


@dataclass
class Patient:
    """Patient record for outbound calling."""
    patient_id: str
    name: str
    phone: str
    language: Language = Language.ENGLISH
    order_id: Optional[str] = None
    order_created: Optional[datetime] = None
    intake_status: IntakeStatus = IntakeStatus.COMPLETE

    # Legacy intent flags — retained for due_by calc and historical display
    # only. Not used in priority sorting anymore.
    has_called_in_before: bool = False
    has_abandoned_before: bool = False
    ai_called_before: bool = False

    # Split attempt tracking (priority uses total = ai + human)
    ai_attempt_count: int = 0
    human_attempt_count: int = 0
    last_attempt_at: Optional[datetime] = None
    last_outcome: Optional[str] = None
    due_by: Optional[datetime] = None

    # RadFlow lifecycle status (None = unknown/simulation-only)
    radflow_status: Optional[str] = None
    hl7_sent_at: Optional[datetime] = None

    # Legacy combined counter — kept so older consumers don't break while
    # the UI transitions to showing ai/human separately.
    attempt_count: int = 0

    # Legacy priority bucket, computed from the new fields for display
    # compatibility. Queue ordering no longer consults it.
    priority_bucket: int = field(init=False, default=0)

    def __post_init__(self):
        # Keep combined count in sync if caller only set the legacy field.
        if self.ai_attempt_count == 0 and self.human_attempt_count == 0 and self.attempt_count:
            self.ai_attempt_count = self.attempt_count
        self.attempt_count = self.total_attempts
        self.priority_bucket = STATUS_RANK.get(self.radflow_status or "", 99)

    @property
    def total_attempts(self) -> int:
        return self.ai_attempt_count + self.human_attempt_count

    def to_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "name": self.name,
            "phone": self.phone,
            "language": self.language.value,
            "order_id": self.order_id,
            "order_created": self.order_created.isoformat() if self.order_created else None,
            "intake_status": self.intake_status.value,
            "has_called_in_before": self.has_called_in_before,
            "has_abandoned_before": self.has_abandoned_before,
            "ai_called_before": self.ai_called_before,
            "ai_attempt_count": self.ai_attempt_count,
            "human_attempt_count": self.human_attempt_count,
            "total_attempts": self.total_attempts,
            "attempt_count": self.total_attempts,  # legacy alias
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "last_outcome": self.last_outcome,
            "due_by": self.due_by.isoformat() if self.due_by else None,
            "radflow_status": self.radflow_status,
            "hl7_sent_at": self.hl7_sent_at.isoformat() if self.hl7_sent_at else None,
            "priority_bucket": self.priority_bucket,
        }
