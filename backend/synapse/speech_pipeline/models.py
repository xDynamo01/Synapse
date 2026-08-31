from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

SpeechPipelineStatus = str

SPEECH_PIPELINE_STATUSES: set[str] = {
    "idle",
    "listening",
    "processing",
    "speaking",
    "paused",
    "closed",
    "failed",
}


@dataclass(frozen=True)
class SpeechPipelineSession:
    audio_session_id: str
    pipeline_session_id: str = field(default_factory=lambda: str(uuid4()))
    voice_session_id: str | None = None
    multimodal_session_id: str | None = None
    agent_id: str | None = None
    status: SpeechPipelineStatus = "idle"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechInputTurn:
    pipeline_session_id: str
    audio_session_id: str
    transcript: str
    turn_id: str = field(default_factory=lambda: str(uuid4()))
    confidence: float | None = None
    perception_signal_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechOutputTurn:
    pipeline_session_id: str
    voice_session_id: str
    utterance_id: str
    text: str
    turn_id: str = field(default_factory=lambda: str(uuid4()))
    output_ref: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechPipelineSummary:
    session: SpeechPipelineSession
    input_turn_count: int
    output_turn_count: int
    latest_input: SpeechInputTurn | None = None
    latest_output: SpeechOutputTurn | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
