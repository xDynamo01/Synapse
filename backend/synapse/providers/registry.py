from __future__ import annotations

from synapse.core.exceptions import NotFound, ValidationError
from synapse.providers.models import (
    PROVIDER_TYPES,
    CapabilityProvider,
    ProviderManifest,
    ProviderType,
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderManifest] = {}
        self._capability_providers: dict[str, list[CapabilityProvider]] = {}

    def register_provider(self, manifest: ProviderManifest) -> ProviderManifest:
        self._validate_manifest(manifest)
        self._providers[manifest.provider_id] = manifest
        priority = 100
        try:
            priority = (
                int(manifest.metadata.get("capability_priority", 100)) if manifest.metadata else 100
            )
        except Exception:
            priority = 100
        for capability_id in manifest.capabilities:
            existing = [
                item
                for item in self._capability_providers.get(capability_id, [])
                if item.provider_id != manifest.provider_id
            ]
            existing.append(
                CapabilityProvider(
                    capability_id=capability_id,
                    provider_id=manifest.provider_id,
                    priority=priority,
                    enabled=manifest.enabled,
                    metadata={"source": "manifest"},
                )
            )
            self._capability_providers[capability_id] = sorted(
                existing,
                key=lambda item: item.priority,
            )
        return manifest

    def get_provider(self, provider_id: str) -> ProviderManifest:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise NotFound(f"Provider not found: {provider_id}") from exc

    def list_providers(self) -> list[ProviderManifest]:
        return sorted(self._providers.values(), key=lambda item: item.provider_id)

    def list_by_type(self, provider_type: ProviderType) -> list[ProviderManifest]:
        return [
            provider
            for provider in self.list_providers()
            if provider.provider_type == provider_type
        ]

    def register_capability_provider(
        self,
        capability_provider: CapabilityProvider,
    ) -> CapabilityProvider:
        self.get_provider(capability_provider.provider_id)
        existing = [
            item
            for item in self._capability_providers.get(capability_provider.capability_id, [])
            if item.provider_id != capability_provider.provider_id
        ]
        existing.append(capability_provider)
        self._capability_providers[capability_provider.capability_id] = sorted(
            existing,
            key=lambda item: item.priority,
        )
        return capability_provider

    def list_capability_providers(self, capability_id: str) -> list[CapabilityProvider]:
        return list(self._capability_providers.get(capability_id, []))

    def _validate_manifest(self, manifest: ProviderManifest) -> None:
        if not manifest.provider_id:
            raise ValidationError("provider_id is required")
        if manifest.provider_type not in PROVIDER_TYPES:
            raise ValidationError(f"Unsupported provider_type: {manifest.provider_type}")
        if not manifest.version:
            raise ValidationError("provider version is required")


def builtin_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for manifest in _mock_provider_manifests():
        registry.register_provider(manifest)
    return registry


def _mock_provider_manifests() -> list[ProviderManifest]:
    return [
        ProviderManifest(
            provider_id="mock_stt",
            name="Mock STT Provider",
            description="Unconfigured placeholder for future speech-to-text providers.",
            provider_type="stt",
            capabilities=["voice.stt", "speech_to_text"],
            version="0.1.0",
            enabled=True,
            local_only=True,
            requires_network=False,
            requires_gpu=False,
            supported_platforms=["windows", "linux", "darwin"],
            metadata={"mock": True, "executes_real_provider": False},
        ),
        ProviderManifest(
            provider_id="mock_tts",
            name="Mock TTS Provider",
            description="Unconfigured placeholder for future text-to-speech providers.",
            provider_type="tts",
            capabilities=["voice.tts", "text_to_speech"],
            version="0.1.0",
            enabled=True,
            local_only=True,
            requires_network=False,
            requires_gpu=False,
            supported_platforms=["windows", "linux", "darwin"],
            metadata={"mock": True, "executes_real_provider": False},
        ),
        ProviderManifest(
            provider_id="piper",
            name="Piper TTS Provider",
            description="Local text-to-speech provider boundary for Windows Alpha.",
            provider_type="tts",
            capabilities=["voice.tts", "text_to_speech"],
            version="1.0.0",
            enabled=True,
            local_only=True,
            requires_network=False,
            requires_gpu=False,
            supported_platforms=["windows", "linux", "darwin"],
            metadata={
                "executes_real_provider": False,
                "adapter_factory": "piper_tts",
                "engine": "piper",
                "execution_boundary_required": True,
                "voice_preset": "default",
                "capability_priority": 10,
            },
        ),
        ProviderManifest(
            provider_id="mock_voice_analysis",
            name="Mock Voice Analysis Provider",
            description="Unconfigured placeholder for future voice analysis providers.",
            provider_type="voice_analysis",
            capabilities=["voice_analysis"],
            version="0.1.0",
            enabled=True,
            local_only=True,
            requires_network=False,
            requires_gpu=False,
            supported_platforms=["windows", "linux", "darwin"],
            metadata={"mock": True, "executes_real_provider": False},
        ),
        ProviderManifest(
            provider_id="faster_whisper",
            name="Faster-Whisper STT Provider",
            description="Local speech-to-text provider powered by Faster-Whisper.",
            provider_type="stt",
            capabilities=["voice.stt", "speech_to_text"],
            version="1.0.0",
            enabled=True,
            local_only=True,
            requires_network=False,
            requires_gpu=False,
            supported_platforms=["windows", "linux", "darwin"],
            metadata={
                "executes_real_provider": True,
                "model_root": "voice/models/faster-whisper",
                "download_strategy": "local-cache",
                "adapter_factory": "faster_whisper",
            },
        ),
        ProviderManifest(
            provider_id="lmstudio_local",
            name="LM Studio Local Provider",
            description="Optional local OpenAI-compatible chat completions through LM Studio.",
            provider_type="model",
            capabilities=["local_llm", "chat_completion"],
            version="1.0.0",
            enabled=True,
            local_only=True,
            requires_network=False,
            requires_gpu=False,
            supported_platforms=["windows", "linux", "darwin"],
            metadata={
                "base_url_default": "http://127.0.0.1:1234/v1",
                "external_process_required": True,
            },
        ),
    ]
