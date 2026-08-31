from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractEvent, now_iso


@dataclass(frozen=True)
class VoiceSettingsDTO:
    stt_provider_id: str | None = None
    tts_provider_id: str | None = None
    voice_analysis_provider_id: str | None = None
    device_id: str | None = None
    language: str = "pt-BR"
    model: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class VoiceSTTRequestDTO:
    audio_ref: str
    language: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class VoiceSTTResultDTO:
    transcript: str
    provider_id: str | None = None
    confidence: float | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class VoiceTTSRequestDTO:
    text: str
    voice_id: str | None = None
    speed: float | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class VoiceTTSResultDTO:
    audio_ref: str
    provider_id: str | None = None
    audio_format: str | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class VoiceAnalysisRequestDTO:
    audio_ref: str
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class VoiceAnalysisResultDTO:
    summary: str
    provider_id: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class VoiceSTTProvider(Protocol):
    def transcribe(self, request: VoiceSTTRequestDTO) -> VoiceSTTResultDTO: ...

    def health(self) -> dict[str, Any]: ...

    def emit(self, event: ContractEvent) -> None: ...


@runtime_checkable
class VoiceTTSProvider(Protocol):
    def synthesize(self, request: VoiceTTSRequestDTO) -> VoiceTTSResultDTO: ...

    def health(self) -> dict[str, Any]: ...

    def emit(self, event: ContractEvent) -> None: ...


@runtime_checkable
class VoiceAnalysisProvider(Protocol):
    def analyze(self, request: VoiceAnalysisRequestDTO) -> VoiceAnalysisResultDTO: ...

    def health(self) -> dict[str, Any]: ...

    def emit(self, event: ContractEvent) -> None: ...
