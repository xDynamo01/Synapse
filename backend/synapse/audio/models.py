from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

AudioSessionStatus = str
AudioDeviceType = str

AUDIO_SESSION_STATUSES: set[str] = {
    "idle",
    "listening",
    "speaking",
    "paused",
    "closed",
    "failed",
}

AUDIO_DEVICE_TYPES: set[str] = {
    "input",
    "output",
    "virtual",
}


@dataclass(frozen=True)
class AudioPayload:
    audio_bytes: bytes
    mime_type: str
    sample_rate: int
    channels: int
    encoding: str
    duration_ms: int
    checksum: str
    frame_count: int
    average_volume: float | None = None
    peak_volume: float | None = None
    silence_ratio: float | None = None
    source_mime_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    multimodal_session_id: str | None = None
    agent_id: str | None = None
    status: AudioSessionStatus = "idle"
    input_device_id: str | None = None
    output_device_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioDevice:
    device_id: str
    name: str
    device_type: AudioDeviceType
    enabled: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceDescriptor:
    id: str
    stable_id: str
    name: str
    direction: str
    backend: str
    is_default: bool
    channels: int
    default_sample_rate: float
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InputDeviceTestResult:
    device_id: str
    found: bool
    opened: bool
    frames_received: int = 0
    duration_ms: int = 0
    signal_detected: bool = False
    rms: float | None = None
    peak: float | None = None
    clipping: bool = False
    silence_ratio: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class OutputDeviceTestResult:
    device_id: str
    found: bool
    opened: bool
    playback_started: bool = False
    playback_completed: bool = False
    duration_ms: int = 0
    error: str | None = None


@dataclass(frozen=True)
class AudioInputRequest:
    session_id: str | None = None
    multimodal_session_id: str | None = None
    provider_id: str | None = None
    language: str | None = None
    model: str | None = None
    audio_base64: str | None = None
    audio_format: str | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioOutputRequest:
    session_id: str
    text: str
    agent_id: str | None = None
    provider_id: str | None = None
    voice_id: str | None = None
    language: str | None = None
    speed: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechFeatures:
    duration_ms: int | None = None
    average_volume: float | None = None
    peak_volume: float | None = None
    speech_rate: float | None = None
    pause_count: int | None = None
    pause_duration_ms: int | None = None
    silence_ratio: float | None = None
    segment_count: int | None = None
    timestamps: list[dict[str, Any]] = field(default_factory=list)
    language_confidence: float | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    # Legacy aliases retained as optional fields for callers that still read them.
    pause_ratio: float | None = None
    silence_duration: float | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceAnalysisResult:
    provider_id: str
    duration_ms: int
    average_volume: float | None = None
    peak_volume: float | None = None
    silence_ratio: float | None = None
    silence_duration_ms: int | None = None
    speech_duration_ms: int | None = None
    pause_count: int | None = None
    pause_duration_ms: int | None = None
    speech_rate: float | None = None
    pitch: float | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    status: str = "success"
    language: str | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration_ms: int | None = None
    confidence: float | None = None
    provider_id: str | None = None
    latency_ms: int | None = None
    speech_features: SpeechFeatures = field(default_factory=SpeechFeatures)
    metadata: dict[str, Any] = field(default_factory=dict)


SpeechToTextResult = TranscriptResult


@dataclass(frozen=True)
class TextToSpeechResult:
    output_ref: str
    provider_id: str | None = None
    voice_id: str | None = None
    audio_base64: str | None = None
    audio_format: str | None = None
    duration_ms: int | None = None
    latency_ms: int | None = None
    sample_rate: int | None = None
    warnings: list[str] = field(default_factory=list)
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
