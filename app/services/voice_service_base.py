"""Abstract base class for realtime voice services."""
from abc import ABC, abstractmethod
from typing import Optional, Callable, Any


class BaseVoiceService(ABC):
    """Common interface for OpenAI and Gemini realtime voice providers."""

    def __init__(self, audio_format: str = "pcm16", verbose: bool = False):
        self._audio_format = audio_format
        self._verbose = verbose

        # Callbacks — set by CallOrchestrator / TwilioMediaBridge
        self.on_transcript: Optional[Callable[[str, str], Any]] = None  # (speaker, text)
        self.on_audio: Optional[Callable[[bytes], Any]] = None  # audio data
        self.on_session_created: Optional[Callable[[str], Any]] = None
        self.on_session_ended: Optional[Callable[[], Any]] = None
        self.on_error: Optional[Callable[[str], Any]] = None
        self.on_function_call: Optional[Callable[[str, dict, str], Any]] = None  # (name, args, call_id)

    @abstractmethod
    async def connect(self, call_id: str, patient_name: str, patient_language: str = "en") -> bool:
        """Connect to the realtime API and start a session."""
        ...

    @abstractmethod
    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data (from patient) to the API."""
        ...

    @abstractmethod
    async def send_function_result(self, call_id: str, result: dict) -> None:
        """Send a function call result back to the API."""
        ...

    @abstractmethod
    async def start_conversation(self) -> None:
        """Start the conversation with an AI greeting."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the API."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to the API."""
        ...
