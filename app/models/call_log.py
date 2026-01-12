"""Call log model."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid


class CallOutcome(str, Enum):
    IN_PROGRESS = "in_progress"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    TRANSFERRED = "transferred"
    CALLBACK_REQUESTED = "callback_requested"
    WRONG_NUMBER = "wrong_number"
    DISCONNECTED = "disconnected"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TranscriptEntry:
    """Single transcript entry."""
    speaker: str  # "ai" or "patient"
    text: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class CallLog:
    """Record of an outbound call."""
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str = ""
    patient_name: str = ""
    phone: str = ""
    order_id: Optional[str] = None
    priority_bucket: int = 0

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    duration_seconds: int = 0

    # Outcome
    outcome: CallOutcome = CallOutcome.IN_PROGRESS
    transfer_attempted: bool = False
    transfer_success: bool = False
    voicemail_left: bool = False
    sms_sent: bool = False

    # Queue state at dial time
    queue_snapshot: Optional[dict] = None

    # Transcript
    transcript: list[TranscriptEntry] = field(default_factory=list)

    # Error info
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def add_transcript(self, speaker: str, text: str):
        """Add a transcript entry."""
        self.transcript.append(TranscriptEntry(speaker=speaker, text=text))

    def end_call(self, outcome: CallOutcome):
        """Mark call as ended."""
        self.ended_at = datetime.now()
        self.outcome = outcome
        if self.started_at:
            self.duration_seconds = int((self.ended_at - self.started_at).total_seconds())

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "phone": self.phone,
            "order_id": self.order_id,
            "priority_bucket": self.priority_bucket,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome.value,
            "transfer_attempted": self.transfer_attempted,
            "transfer_success": self.transfer_success,
            "voicemail_left": self.voicemail_left,
            "sms_sent": self.sms_sent,
            "queue_snapshot": self.queue_snapshot,
            "transcript": [t.to_dict() for t in self.transcript],
            "error_code": self.error_code,
            "error_message": self.error_message,
        }
