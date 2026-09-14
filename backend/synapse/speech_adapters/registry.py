from __future__ import annotations

import os

from synapse.core.exceptions import NotFound, ValidationError
from synapse.speech_adapters.models import (
    SPEECH_ADAPTER_TYPES,
    SpeechAdapterCapability,
    SpeechAdapterManifest,
    SpeechAdapterType,
)


class SpeechAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SpeechAdapterManifest] = {}
        self._capabilities: dict[str, list[SpeechAdapterCapability]] = {}

    def register_adapter(self, manifest: SpeechAdapterManifest) -> SpeechAdapterManifest:
        self._validate_manifest(manifest)
        self._adapters[manifest.adapter_id] = manifest
        return manifest

    def get_adapter(self, adapter_id: str) -> SpeechAdapterManifest:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise NotFound(f"Speech adapter not found: {adapter_id}") from exc

    def list_adapters(self) -> list[SpeechAdapterManifest]:
        return sorted(self._adapters.values(), key=lambda item: item.adapter_id)

    def list_by_type(self, adapter_type: SpeechAdapterType) -> list[SpeechAdapterManifest]:
        if adapter_type not in SPEECH_ADAPTER_TYPES:
            raise ValidationError(f"Unsupported speech adapter type: {adapter_type}")
        return [adapter for adapter in self.list_adapters() if adapter.adapter_type == adapter_type]

    def register_capability(
        self,
        adapter_capability: SpeechAdapterCapability,
    ) -> SpeechAdapterCapability:
        self.get_adapter(adapter_capability.adapter_id)
        existing = [
            item
            for item in self._capabilities.get(adapter_capability.capability_id, [])
            if item.adapter_id != adapter_capability.adapter_id
        ]
        existing.append(adapter_capability)
        self._capabilities[adapter_capability.capability_id] = sorted(
            existing,
            key=lambda item: item.priority,
        )
        return adapter_capability

    def list_capabilities(self, capability_id: str) -> list[SpeechAdapterCapability]:
        return list(self._capabilities.get(capability_id, []))

    @staticmethod
    def _validate_manifest(manifest: SpeechAdapterManifest) -> None:
        if not manifest.adapter_id:
            raise ValidationError("adapter_id is required")
        if not manifest.provider_id:
            raise ValidationError("provider_id is required")
        if manifest.adapter_type not in SPEECH_ADAPTER_TYPES:
            raise ValidationError(f"Unsupported speech adapter type: {manifest.adapter_type}")
        if not manifest.version:
            raise ValidationError("adapter version is required")


def builtin_speech_adapter_registry() -> SpeechAdapterRegistry:
    registry = SpeechAdapterRegistry()
    manifests = [
        SpeechAdapterManifest(
            adapter_id="local_voice_analysis_adapter",
            provider_id="local_acoustic_analysis",
            adapter_type="voice_analysis",
            name="Local Acoustic Analysis",
            description="Objective acoustic metrics calculated from canonical PCM audio.",
            version="1.0.0",
            supported_languages=[],
            supports_streaming=False,
            supports_file_input=True,
            supports_realtime=False,
            requires_gpu=False,
            requires_network=False,
            metadata={
                "mock": False,
                "executes_real_provider": True,
                "adapter_factory": "local_voice_analysis",
            },
        ),
        SpeechAdapterManifest(
            adapter_id="mock_stt_adapter",
            provider_id="mock_stt",
            adapter_type="stt",
            name="Mock STT Adapter",
            description="Deterministic placeholder for future STT engines.",
            version="0.1.0",
            supported_languages=["en-US", "pt-BR"],
            supports_streaming=False,
            supports_file_input=False,
            supports_realtime=False,
            requires_gpu=False,
            requires_network=False,
            metadata={"mock": True, "executes_real_provider": False},
        ),
        SpeechAdapterManifest(
            adapter_id="mock_tts_adapter",
            provider_id="mock_tts",
            adapter_type="tts",
            name="Mock TTS Adapter",
            description="Deterministic placeholder for future TTS engines.",
            version="0.1.0",
            supported_languages=["en-US", "pt-BR"],
            supports_streaming=False,
            supports_file_input=False,
            supports_realtime=False,
            requires_gpu=False,
            requires_network=False,
            metadata={"mock": True, "executes_real_provider": False},
        ),
        SpeechAdapterManifest(
            adapter_id="kokoro_tts_adapter",
            provider_id="kokoro",
            adapter_type="tts",
            name="Kokoro · Dora (pt-BR)",
            description="Offline CPU speech with the original Dora voice.",
            version="1.0.0",
            supported_languages=["pt-BR"],
            supports_streaming=False,
            supports_file_input=False,
            supports_realtime=False,
            requires_gpu=False,
            requires_network=False,
            metadata={"adapter_factory": "kokoro_tts", "engine": "kokoro",
                      "execution_boundary_required": True, "executes_real_provider": False},
        ),
        SpeechAdapterManifest(
            adapter_id="piper_tts_adapter",
            provider_id="piper",
            adapter_type="tts",
            name="Piper TTS Adapter",
            description="Local text-to-speech adapter boundary for Piper-compatible synthesis.",
            version="1.0.0",
            supported_languages=["en-US", "pt-BR", "es-ES"],
            supports_streaming=False,
            supports_file_input=False,
            supports_realtime=False,
            requires_gpu=False,
            requires_network=False,
            metadata={
                "mock": False,
                "executes_real_provider": False,
                "adapter_factory": "piper_tts",
                "engine": "piper",
                "execution_boundary_required": True,
            },
        ),
        SpeechAdapterManifest(
            adapter_id="mock_voice_analysis_adapter",
            provider_id="mock_voice_analysis",
            adapter_type="voice_analysis",
            name="Mock Voice Analysis Adapter",
            description="Deterministic placeholder for future voice analysis engines.",
            version="0.1.0",
            supported_languages=["en-US", "pt-BR"],
            supports_streaming=False,
            supports_file_input=False,
            supports_realtime=False,
            requires_gpu=False,
            requires_network=False,
            metadata={"mock": True, "executes_real_provider": False},
        ),
        SpeechAdapterManifest(
            adapter_id="faster_whisper_adapter",
            provider_id="faster_whisper",
            adapter_type="stt",
            name="Faster-Whisper STT Adapter",
            description="Local STT adapter powered by Faster-Whisper.",
            version="1.0.0",
            supported_languages=["en-US", "pt-BR", "es-ES"],
            supports_streaming=False,
            supports_file_input=True,
            supports_realtime=False,
            requires_gpu=False,
            requires_network=False,
            metadata={
                "mock": False,
                "executes_real_provider": True,
                "model_root": "voice/models/faster-whisper",
            },
        ),
    ]
    if os.getenv("SYNAPSE_DEV_MODE", "").lower() not in {"1", "true", "yes"}:
        manifests = [manifest for manifest in manifests if not manifest.metadata.get("mock")]
    for manifest in manifests:
        registry.register_adapter(manifest)
    if "mock_stt_adapter" in {item.adapter_id for item in registry.list_adapters()}:
        registry.register_capability(
            SpeechAdapterCapability("mock_stt_adapter", "speech_to_text", 100, True)
        )
        registry.register_capability(
            SpeechAdapterCapability("mock_tts_adapter", "text_to_speech", 100, True)
        )
        registry.register_capability(
            SpeechAdapterCapability("mock_voice_analysis_adapter", "voice_analysis", 100, True)
        )
    registry.register_capability(
        SpeechAdapterCapability("kokoro_tts_adapter", "text_to_speech", 5, True)
    )
    registry.register_capability(
        SpeechAdapterCapability("piper_tts_adapter", "text_to_speech", 10, True)
    )
    registry.register_capability(
        SpeechAdapterCapability("local_voice_analysis_adapter", "voice_analysis", 10, True)
    )
    registry.register_capability(
        SpeechAdapterCapability("faster_whisper_adapter", "speech_to_text", 10, True)
    )
    return registry
