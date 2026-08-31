from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class VoicePerceptionSignal:
    type: str
    session_id: str | None
    provenance: str
    id: str = field(default_factory=lambda: str(uuid4()))
    conversation_id: str | None = None
    utterance_id: str | None = None
    recording_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    confidence: float | None = None
    values: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)


class VoicePerceptionSink(Protocol):
    def emit(self, signal: VoicePerceptionSignal) -> None: ...


class NullVoicePerceptionSink:
    def emit(self, signal: VoicePerceptionSignal) -> None:
        return None
