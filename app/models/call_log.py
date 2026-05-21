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


class CallStatus(str, Enum):
    """High-level attempt status: did we successfully place the call?"""
    IN_PROGRESS = "in_progress"
    CALLED = "called"      # Call went out and reached the patient's phone
    FAILED = "failed"      # Call could not be placed (no carrier connection)


class CallDisposition(str, Enum):
    """Detailed disposition: what actually happened during or to the call."""
    IN_PROGRESS = "in_progress"
    TRANSFERRED = "transferred"              # Patient answered and was transferred
    VOICEMAIL_LEFT = "voicemail_left"        # Reached voicemail and left a message
    NO_ANSWER = "no_answer"                  # Rang out, no one answered
    HUNG_UP = "hung_up"                      # Patient answered then disconnected
    CALLBACK_REQUESTED = "callback_requested"  # Patient asked to be called back
    WRONG_NUMBER = "wrong_number"            # Reached wrong person / identity mismatch
    COMPLETED = "completed"                  # Call ended normally
    DISCONNECTED_NUMBER = "disconnected_number"  # Carrier: invalid/disconnected
    TECHNICAL_ERROR = "technical_error"      # Twilio/OpenAI error


def derive_status_and_disposition(
    outcome: "CallOutcome",
    error_code: Optional[str] = None,
    had_patient_speech: bool = False,
    duration_seconds: int = 0,
) -> tuple["CallStatus", "CallDisposition"]:
    """Derive CallStatus + CallDisposition from the legacy outcome + context.

    Rules (from Danny's feedback):
    - No answer is NOT a fail — it's Called + NoAnswer
    - Hang-up after answering is NOT a fail — it's Called + HungUp
    - Only real carrier/technical failures (couldn't reach the phone at all)
      should be Failed.
    """
    # Pre-connect failures
    if outcome == CallOutcome.FAILED:
        if error_code == "media_stream_timeout":
            # Twilio call was placed but the media stream never connected.
            # Typically means the call rang out without being answered.
            return CallStatus.CALLED, CallDisposition.NO_ANSWER
        if error_code in ("twilio_no-answer", "twilio_busy"):
            # Twilio reported the call rang out or was busy — the call was
            # placed successfully, the patient just didn't pick up.
            return CallStatus.CALLED, CallDisposition.NO_ANSWER
        if error_code and error_code.isdigit():
            code = int(error_code)
            if code in (32005, 32009):  # invalid/disconnected number
                return CallStatus.FAILED, CallDisposition.DISCONNECTED_NUMBER
        # Everything else (openai_connect_failed, twilio_place_failed, etc.)
        return CallStatus.FAILED, CallDisposition.TECHNICAL_ERROR

    if outcome == CallOutcome.DISCONNECTED:
        # Media stream closed mid-call.  If patient spoke or call had real
        # duration, they answered then hung up.  Otherwise treat as a bad
        # number / carrier failure.
        if had_patient_speech or duration_seconds >= 5:
            return CallStatus.CALLED, CallDisposition.HUNG_UP
        return CallStatus.FAILED, CallDisposition.DISCONNECTED_NUMBER

    if outcome == CallOutcome.TRANSFERRED:
        return CallStatus.CALLED, CallDisposition.TRANSFERRED
    if outcome == CallOutcome.VOICEMAIL:
        return CallStatus.CALLED, CallDisposition.VOICEMAIL_LEFT
    if outcome == CallOutcome.CALLBACK_REQUESTED:
        return CallStatus.CALLED, CallDisposition.CALLBACK_REQUESTED
    if outcome == CallOutcome.WRONG_NUMBER:
        return CallStatus.CALLED, CallDisposition.WRONG_NUMBER
    if outcome == CallOutcome.NO_ANSWER:
        return CallStatus.CALLED, CallDisposition.NO_ANSWER
    if outcome == CallOutcome.COMPLETED:
        return CallStatus.CALLED, CallDisposition.COMPLETED

    return CallStatus.IN_PROGRESS, CallDisposition.IN_PROGRESS


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
    call_status: CallStatus = CallStatus.IN_PROGRESS
    call_disposition: CallDisposition = CallDisposition.IN_PROGRESS
    mock_mode: bool = False  # True if the call was redirected to mock_phone instead of the patient
    voice_provider: str = "openai"  # "openai" or "gemini"
    transfer_attempted: bool = False
    transfer_success: bool = False
    voicemail_left: bool = False
    sms_sent: bool = False
    preferred_callback_time: Optional[str] = None

    # Audio recording metadata
    recording_sid: Optional[str] = None
    recording_path: Optional[str] = None
    recording_size_bytes: Optional[int] = None
    recording_duration_seconds: Optional[int] = None
    recording_format: Optional[str] = None

    # Queue state at dial time
    queue_snapshot: Optional[dict] = None

    # Transcript
    transcript: list[TranscriptEntry] = field(default_factory=list)

    # Error info
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    # Per-call latency milestones. Keys are stable snake_case identifiers
    # (e.g. "voice_connected", "first_audio_out"); values are cumulative
    # milliseconds since start_call entry. Populated by CallSession._timing
    # and written at end_call. Empty {} on legacy rows.
    timings: dict = field(default_factory=dict)

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
            "call_status": self.call_status.value,
            "call_disposition": self.call_disposition.value,
            "mock_mode": self.mock_mode,
            "voice_provider": self.voice_provider,
            "transfer_attempted": self.transfer_attempted,
            "transfer_success": self.transfer_success,
            "voicemail_left": self.voicemail_left,
            "sms_sent": self.sms_sent,
            "preferred_callback_time": self.preferred_callback_time,
            "queue_snapshot": self.queue_snapshot,
            "transcript": [t.to_dict() for t in self.transcript],
            "timings": dict(self.timings or {}),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "recording_sid": self.recording_sid,
            "recording_path": self.recording_path,
            "recording_size_bytes": self.recording_size_bytes,
            "recording_duration_seconds": self.recording_duration_seconds,
            "recording_format": self.recording_format,
            "has_recording": bool(self.recording_path),
        }
