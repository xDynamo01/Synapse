from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SpeechAdapterType = str
SpeechAdapterHealthStatus = str

SPEECH_ADAPTER_TYPES: set[str] = {"stt", "tts", "voice_analysis"}
SPEECH_ADAPTER_HEALTH_STATUSES: set[str] = {
    "available",
    "unavailable",
    "degraded",
    "unconfigured",
}


@dataclass(frozen=True)
class SpeechAdapterManifest:
    adapter_id: str
    provider_id: str
    adapter_type: SpeechAdapterType
    name: str
    description: str
    version: str
    supported_languages: list[str]
    supports_streaming: bool
    supports_file_input: bool
    supports_realtime: bool
    requires_gpu: bool
    requires_network: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechAdapterHealth:
    adapter_id: str
    provider_id: str
    status: SpeechAdapterHealthStatus
    checked_at: str
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechAdapterCapability:
    adapter_id: str
    capability_id: str
    priority: int
    enabled: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechAdapterResolution:
    capability_id: str
    selected_adapter_id: str | None = None
    selected_provider_id: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
