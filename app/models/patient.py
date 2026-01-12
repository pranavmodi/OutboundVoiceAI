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

    # Priority bucket fields
    has_called_in_before: bool = False
    has_abandoned_before: bool = False
    ai_called_before: bool = False

    # Attempt tracking
    attempt_count: int = 0
    last_attempt_at: Optional[datetime] = None
    last_outcome: Optional[str] = None
    due_by: Optional[datetime] = None

    # Computed priority (1-4, lower is higher priority)
    priority_bucket: int = field(init=False)

    def __post_init__(self):
        self.priority_bucket = self._compute_priority()

    def _compute_priority(self) -> int:
        """Compute priority bucket based on call history."""
        if self.has_abandoned_before and not self.ai_called_before:
            return 1  # Abandoned + never AI-called
        elif self.has_abandoned_before and self.ai_called_before:
            return 2  # Abandoned + AI-called before
        elif not self.ai_called_before and self.has_called_in_before:
            return 3  # Never AI-called + called in before
        else:
            return 4  # Never AI-called + never called in

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
            "attempt_count": self.attempt_count,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "last_outcome": self.last_outcome,
            "due_by": self.due_by.isoformat() if self.due_by else None,
            "priority_bucket": self.priority_bucket,
        }
