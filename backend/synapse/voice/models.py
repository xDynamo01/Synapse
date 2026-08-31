from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

VoiceSessionStatus = str
VoiceUtteranceState = str
VoiceProviderSelectionState = str

VOICE_CONFIGURATION_POLICY_VERSION = "voice-configuration-v1"
VOICE_SETTINGS_SCHEMA_VERSION = 3
VOICE_PROVIDER_SELECTION_STATES: set[str] = {
    "configured",
    "supported",
    "degraded",
    "unavailable",
}

VOICE_MODEL_PRESETS: dict[str, str] = {
    "auto": "small",
    "fast": "tiny",
    "balanced": "base",
    "quality": "medium",
    "high_quality": "large-v3",
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large-v3": "large-v3",
    "large-v3-turbo": "large-v3",
}

VOICE_SESSION_STATUSES: set[str] = {
    "idle",
    "listening",
    "recording",
    "processing",
    "thinking",
    "queued",
    "speaking",
    "paused",
    "cancelling",
    "cancelled",
    "closed",
    "error",
    "failed",
    "reconciliation_required",
}

VOICE_UTTERANCE_STATES: set[str] = {
    "pending",
    "synthesizing",
    "ready",
    "playing",
    "completed",
    "failed",
    "cancelled",
}

VOICE_RECORDING_STATUSES: set[str] = {
    "created",
    "recording",
    "completed",
    "processing",
    "recorded",
    "transcribed",
    "cancelled",
    "failed",
    "deleted",
}


@dataclass(frozen=True)
class VoiceSession:
    agent_id: str
    session_id: str = field(default_factory=lambda: str(uuid4()))
    status: VoiceSessionStatus = "idle"
    conversation_id: str | None = None
    previous_state: str | None = None
    active_recording_id: str | None = None
    active_utterance_id: str | None = None
    active_synthesis_id: str | None = None
    closed_at: str | None = None
    revision: int = 1
    settings_snapshot: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceUtterance:
    session_id: str
    text: str
    utterance_id: str = field(default_factory=lambda: str(uuid4()))
    provider_id: str | None = None
    priority: int = 100
    state: VoiceUtteranceState = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoicePlaybackState:
    session_id: str
    current_utterance: str | None = None
    speaking: bool = False
    queued_items: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceSummary:
    session: VoiceSession
    playback: VoicePlaybackState
    provider_status: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceSettings:
    schema_version: int = VOICE_SETTINGS_SCHEMA_VERSION
    provider_id: str | None = None
    stt_provider_id: str | None = None
    stt_model: str | None = "tiny"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    device_id: str | None = None
    input_device_id: str | None = None
    output_device_id: str | None = None
    language: str = "pt-BR"
    model: str | None = "base"
    tts_provider_id: str | None = "piper"
    tts_model: str | None = None
    default_tts_voice: str | None = None
    preferred_voice_gender: str | None = "female"
    tts_speed: float | None = None
    provider_configuration_references: dict[str, str] = field(default_factory=dict)
    policy_version: str = VOICE_CONFIGURATION_POLICY_VERSION
    voice_analysis_provider_id: str | None = "local_acoustic_analysis"
    vad_provider_id: str | None = None
    vad_enabled: bool = True
    silence_threshold: float = 0.001
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 500
    max_utterance_duration_ms: int = 120_000
    recording_retention: str = "metadata"
    store_raw_audio: bool = False
    delete_after_transcription: bool = True
    retention_days: int = 30
    keep_transcripts: bool = True
    keep_analysis: bool = True
    keep_synthesis_audio: bool = False
    temp_file_max_age_hours: int = 24
    failed_recording_retention_days: int = 7
    conversation_mode_defaults: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceProviderSummary:
    provider_id: str
    adapter_id: str
    adapter_type: str
    status: str
    enabled: bool
    health: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoicePackEntry:
    voice_id: str
    display_name: str
    language: str
    locale: str
    voice_profile: dict[str, Any]
    provider: str
    engine: str
    asset_reference: str
    version: str
    checksum: str
    license: str
    provenance: str
    usable: bool = False
    status: str = "missing"
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoicePackManifest:
    pack_id: str
    display_name: str
    version: str
    provider: str
    engine: str
    voices: list[VoicePackEntry] = field(default_factory=list)
    status: str = "missing"
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceProviderSelection:
    capability: str
    configured_provider_id: str | None
    state: VoiceProviderSelectionState
    adapter_id: str | None = None
    provider_id: str | None = None
    health: dict[str, Any] = field(default_factory=dict)
    policy_version: str = VOICE_CONFIGURATION_POLICY_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceRecording:
    recording_id: str
    session_id: str | None = None
    conversation_id: str | None = None
    agent_id: str | None = None
    device_id: str | None = None
    provider_id: str | None = None
    language: str = "pt-BR"
    model: str | None = None
    audio_ref: str | None = None
    audio_format: str | None = None
    duration_ms: int | None = None
    transcript: str | None = None
    status: str = "recorded"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    chunks: int = 0
    sequence: int = 0
    total_bytes: int = 0
    checksum: str | None = None
    transcript_id: str | None = None
    analysis_id: str | None = None
    error: str | None = None
    revision: int = 1
    idempotency_keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceTranscription:
    recording_id: str
    transcript: str
    provider_id: str | None = None
    language: str = "pt-BR"
    status: str = "transcribed"
    latency_ms: int | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceMessageResult:
    recording_id: str
    transcript_id: str
    text: str
    language: str | None
    segments: list[dict[str, Any]]
    confidence: float | None
    analysis: dict[str, Any]
    duration_ms: int
    warnings: list[str]
    status: str


@dataclass(frozen=True)
class VoiceSynthesis:
    synthesis_id: str
    session_id: str | None
    utterance_id: str | None
    message_id: str | None
    provider_id: str | None
    voice_id: str | None
    status: str
    text_checksum: str
    audio_reference: str | None = None
    duration_ms: int | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    cancelled_at: str | None = None
    error: str | None = None
    revision: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VoiceConversationTurnResult:
    voice_session_id: str
    recording_id: str
    transcript_id: str
    utterance_id: str
    conversation_id: str | None
    user_message_id: str | None
    assistant_message_id: str | None
    synthesis_id: str
    correlation_id: str | None
    transcript: str
    response: str
    status: str


@dataclass(frozen=True)
class VoiceCleanupReport:
    scanned: int = 0
    recordings_deleted: int = 0
    synthesis_deleted: int = 0
    temp_files_deleted: int = 0
    transcripts_retained: int = 0
    analyses_retained: int = 0
    failed: int = 0
    reclaimed_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False
