from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from synapse.audio.models import (
    AudioInputRequest,
    AudioOutputRequest,
    SpeechToTextResult,
    TextToSpeechResult,
)
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.serialization import load_structured_file
from synapse.providers.runtime import ProviderRuntime
from synapse.speech_adapters.execution import SpeechExecutionPort
from synapse.speech_adapters.faster_whisper import FasterWhisperSpeechToTextAdapter
from synapse.speech_adapters.kokoro_tts import KokoroTextToSpeechAdapter
from synapse.speech_adapters.local_analysis import LocalVoiceAnalysisAdapter
from synapse.speech_adapters.models import (
    SpeechAdapterCapability,
    SpeechAdapterHealth,
    SpeechAdapterManifest,
    SpeechAdapterResolution,
)
from synapse.speech_adapters.piper_tts import PiperTextToSpeechAdapter
from synapse.speech_adapters.registry import SpeechAdapterRegistry

DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "prefer_local_adapters": True,
    "allow_network_adapters": False,
    "allow_gpu_adapters": False,
    "disabled_adapters": [],
    "adapter_priority_overrides": {},
}


class MockSpeechToTextAdapter:
    def __init__(self, manifest: SpeechAdapterManifest) -> None:
        self._manifest = manifest

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def health(self) -> SpeechAdapterHealth:
        return _health(self._manifest)

    def transcribe(self, request: AudioInputRequest) -> SpeechToTextResult:
        return SpeechToTextResult(
            text=str(request.metadata.get("text", "mock transcript")),
            language=request.language,
            confidence=1.0,
            provider_id=self._manifest.provider_id,
            latency_ms=0,
            metadata={"mock": True, "adapter_id": self._manifest.adapter_id},
        )


class MockTextToSpeechAdapter:
    def __init__(self, manifest: SpeechAdapterManifest) -> None:
        self._manifest = manifest

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def health(self) -> SpeechAdapterHealth:
        return _health(self._manifest)

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        return TextToSpeechResult(
            output_ref=f"mock://speech-adapter/{request.session_id}",
            provider_id=self._manifest.provider_id,
            voice_id=request.voice_id,
            latency_ms=0,
            metadata={
                "mock": True,
                "adapter_id": self._manifest.adapter_id,
                "text": request.text,
            },
        )


class MockVoiceAnalysisAdapter:
    def __init__(self, manifest: SpeechAdapterManifest) -> None:
        self._manifest = manifest

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def health(self) -> SpeechAdapterHealth:
        return _health(self._manifest)

    def analyze(self, request: AudioInputRequest) -> dict[str, Any]:
        return {
            "provider_id": self._manifest.provider_id,
            "adapter_id": self._manifest.adapter_id,
            "session_id": request.session_id,
            "mock": True,
            "features": {},
        }


class SpeechAdapterRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        registry: SpeechAdapterRegistry,
        providers: ProviderRuntime,
        events: EventBus,
        execution: SpeechExecutionPort | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.registry = registry
        self.providers = providers
        self.events = events
        self.execution = execution
        self._runtime_adapters: dict[str, object] = {}
        for manifest in self.registry.list_adapters():
            self._runtime_adapters[manifest.adapter_id] = self._build_adapter(manifest)
            self.events.emit("speech_adapter.registered", "speech_adapter", asdict(manifest))

    def list_adapters(self) -> list[SpeechAdapterManifest]:
        return self.registry.list_adapters()

    def get_adapter(self, adapter_id: str) -> SpeechAdapterManifest:
        return self.registry.get_adapter(adapter_id)

    def list_by_type(self, adapter_type: str) -> list[SpeechAdapterManifest]:
        return self.registry.list_by_type(adapter_type)

    def register_adapter(self, manifest: SpeechAdapterManifest) -> SpeechAdapterManifest:
        registered = self.registry.register_adapter(manifest)
        self._runtime_adapters[registered.adapter_id] = self._build_adapter(registered)
        self.events.emit("speech_adapter.registered", "speech_adapter", asdict(registered))
        return registered

    def register_capability(
        self,
        adapter_capability: SpeechAdapterCapability,
    ) -> SpeechAdapterCapability:
        return self.registry.register_capability(adapter_capability)

    def adapter_health(self, adapter_id: str) -> SpeechAdapterHealth:
        manifest = self.get_adapter(adapter_id)
        policy = self.load_policy()
        status = "unconfigured"
        message = "Speech adapter is registered but no real provider is configured."
        if adapter_id in set(policy.get("disabled_adapters", [])):
            status = "unavailable"
            message = "Speech adapter is disabled by speech adapter policy."
        elif manifest.requires_network and not policy.get("allow_network_adapters", False):
            status = "unavailable"
            message = "Network speech adapters are disabled by policy."
        elif manifest.requires_gpu and not policy.get("allow_gpu_adapters", False):
            status = "unavailable"
            message = "GPU speech adapters are disabled by policy."
        if status != "unavailable":
            adapter = self._runtime_adapters.get(adapter_id)
            if adapter is not None and hasattr(adapter, "health"):
                try:
                    adapter_health = adapter.health()
                    status = adapter_health.status
                    message = adapter_health.message
                except Exception as exc:
                    status = "unavailable"
                    message = str(exc)
            else:
                try:
                    self.providers.get_provider(manifest.provider_id)
                except Exception as exc:
                    status = "unavailable"
                    message = str(exc)
        health = SpeechAdapterHealth(
            adapter_id=adapter_id,
            provider_id=manifest.provider_id,
            status=status,
            checked_at=_now(),
            message=message,
            metadata={"adapter_type": manifest.adapter_type},
        )
        self.events.emit("speech_adapter.health_checked", "speech_adapter", asdict(health))
        return health

    def list_adapter_health(self) -> list[SpeechAdapterHealth]:
        return [self.adapter_health(adapter.adapter_id) for adapter in self.list_adapters()]

    def resolve_adapter_for_capability(self, capability_id: str) -> SpeechAdapterResolution:
        explanation = self.explain_adapter_resolution(capability_id)
        if not explanation.selected_adapter_id:
            self.events.emit(
                "speech_adapter.resolution.failed",
                "speech_adapter",
                asdict(explanation),
            )
            raise NotFound(f"No eligible speech adapter for capability: {capability_id}")
        self.events.emit(
            "speech_adapter.resolution.completed",
            "speech_adapter",
            asdict(explanation),
        )
        return explanation

    def explain_adapter_resolution(self, capability_id: str) -> SpeechAdapterResolution:
        policy = self.load_policy()
        candidates: list[dict[str, Any]] = []
        eligible_capabilities: list[SpeechAdapterCapability] = []
        overrides = policy.get("adapter_priority_overrides", {})
        for capability in self.registry.list_capabilities(capability_id):
            manifest = self.registry.get_adapter(capability.adapter_id)
            health = self.adapter_health(manifest.adapter_id)
            eligible, reasons = self._eligibility(manifest, capability, health, policy)
            priority = int(overrides.get(manifest.adapter_id, capability.priority))
            candidate = {
                "adapter": asdict(manifest),
                "capability": asdict(capability),
                "health": asdict(health),
                "eligible": eligible,
                "priority": priority,
                "reasons": reasons,
            }
            candidates.append(candidate)
            if eligible:
                eligible_capabilities.append(
                    SpeechAdapterCapability(
                        adapter_id=capability.adapter_id,
                        capability_id=capability.capability_id,
                        priority=priority,
                        enabled=capability.enabled,
                        metadata=capability.metadata,
                    )
                )
        selected = sorted(eligible_capabilities, key=lambda item: item.priority)
        if not selected:
            return SpeechAdapterResolution(
                capability_id=capability_id,
                candidates=candidates,
                reasons=["no_eligible_adapter"],
                metadata={"policy": policy},
            )
        selected_capability = selected[0]
        selected_manifest = self.registry.get_adapter(selected_capability.adapter_id)
        return SpeechAdapterResolution(
            capability_id=capability_id,
            selected_adapter_id=selected_manifest.adapter_id,
            selected_provider_id=selected_manifest.provider_id,
            candidates=candidates,
            reasons=["eligible_adapter_selected"],
            metadata={"policy": policy},
        )

    def resolve_stt_adapter(self) -> SpeechAdapterResolution:
        return self.resolve_adapter_for_capability("speech_to_text")

    def resolve_tts_adapter(self) -> SpeechAdapterResolution:
        return self.resolve_adapter_for_capability("text_to_speech")

    def transcribe(self, request: AudioInputRequest) -> SpeechToTextResult:
        resolution = self._resolve_stt_resolution(request.provider_id)
        adapter = self._runtime_adapters.get(resolution.selected_adapter_id or "")
        if adapter is None or not hasattr(adapter, "transcribe"):
            raise NotFound("Selected STT adapter is not available in this runtime.")
        return adapter.transcribe(request)

    def mock_transcribe(self, request: AudioInputRequest) -> SpeechToTextResult:
        return self.transcribe(request)

    def mock_synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        resolution = self._resolve_tts_resolution(request.provider_id or "mock_tts")
        adapter = self._runtime_adapters[resolution.selected_adapter_id or ""]
        if not isinstance(adapter, MockTextToSpeechAdapter):
            raise NotFound("Selected TTS adapter is not available in this runtime.")
        return adapter.synthesize(request)

    def analyze(self, request: AudioInputRequest):
        resolution = self.resolve_adapter_for_capability("voice_analysis")
        adapter = self._runtime_adapters.get(resolution.selected_adapter_id or "")
        if adapter is None or not hasattr(adapter, "analyze"):
            raise NotFound("Selected voice-analysis adapter is unavailable.")
        return adapter.analyze(request)

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        resolution = self._resolve_tts_resolution(request.provider_id)
        adapter = self._runtime_adapters.get(resolution.selected_adapter_id or "")
        if adapter is None or not hasattr(adapter, "synthesize"):
            raise NotFound("Selected TTS adapter is not available in this runtime.")
        return adapter.synthesize(request)

    def unavailable_count(self) -> int:
        return len(
            [health for health in self.list_adapter_health() if health.status == "unavailable"]
        )

    def load_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.data_dir.resolve("config/speech_adapter_policy.yaml"))
        policy_raw = raw.get("speech_adapters", raw)
        policy = dict(DEFAULT_POLICY)
        policy.update(policy_raw)
        return policy

    def _build_adapter(self, manifest: SpeechAdapterManifest) -> object:
        factory_name = self._adapter_factory_name(manifest)
        if factory_name == "kokoro_tts":
            return KokoroTextToSpeechAdapter(manifest, self.data_dir, self.execution)
        if factory_name == "faster_whisper":
            return FasterWhisperSpeechToTextAdapter(manifest, self.data_dir)
        if factory_name == "piper_tts":
            return PiperTextToSpeechAdapter(manifest, self.data_dir, self.execution)
        if factory_name == "local_voice_analysis":
            return LocalVoiceAnalysisAdapter(manifest)
        if manifest.adapter_type == "stt":
            return MockSpeechToTextAdapter(manifest)
        if manifest.adapter_type == "tts":
            return MockTextToSpeechAdapter(manifest)
        return MockVoiceAnalysisAdapter(manifest)

    def _adapter_factory_name(self, manifest: SpeechAdapterManifest) -> str | None:
        provider_factory = None
        try:
            provider = self.providers.get_provider(manifest.provider_id)
            provider_factory = (
                provider.metadata.get("adapter_factory") if provider.metadata else None
            )
        except Exception:
            provider_factory = None
        manifest_factory = None
        if manifest.metadata:
            manifest_factory = manifest.metadata.get("adapter_factory")
        if isinstance(provider_factory, str) and provider_factory.strip():
            return provider_factory.strip()
        if isinstance(manifest_factory, str) and manifest_factory.strip():
            return manifest_factory.strip()
        return None

    def _resolve_stt_resolution(self, provider_id: str | None = None) -> SpeechAdapterResolution:
        if provider_id == "piper":
            provider_id = "faster_whisper"
        if not provider_id:
            return self.resolve_stt_adapter()
        for capability in self.registry.list_capabilities("speech_to_text"):
            manifest = self.registry.get_adapter(capability.adapter_id)
            if provider_id not in {manifest.provider_id, manifest.adapter_id}:
                continue
            health = self.adapter_health(manifest.adapter_id)
            eligible, reasons = self._eligibility(manifest, capability, health, self.load_policy())
            if not eligible:
                raise NotFound(
                    f"Selected STT adapter is unavailable: {provider_id} ({', '.join(reasons)})"
                )
            return SpeechAdapterResolution(
                capability_id="speech_to_text",
                selected_adapter_id=manifest.adapter_id,
                selected_provider_id=manifest.provider_id,
                candidates=[
                    {
                        "adapter": asdict(manifest),
                        "capability": asdict(capability),
                        "health": asdict(health),
                        "eligible": eligible,
                        "priority": capability.priority,
                        "reasons": reasons,
                    }
                ],
                reasons=["eligible_adapter_selected"],
                metadata={"policy": self.load_policy()},
            )
        raise NotFound(f"Speech adapter not found: {provider_id}")

    def _resolve_tts_resolution(self, provider_id: str | None = None) -> SpeechAdapterResolution:
        if not provider_id:
            return self.resolve_tts_adapter()
        for capability in self.registry.list_capabilities("text_to_speech"):
            manifest = self.registry.get_adapter(capability.adapter_id)
            if provider_id not in {manifest.provider_id, manifest.adapter_id}:
                continue
            health = self.adapter_health(manifest.adapter_id)
            eligible, reasons = self._eligibility(manifest, capability, health, self.load_policy())
            if not eligible:
                raise NotFound(
                    f"Selected TTS adapter is unavailable: {provider_id} ({', '.join(reasons)})"
                )
            return SpeechAdapterResolution(
                capability_id="text_to_speech",
                selected_adapter_id=manifest.adapter_id,
                selected_provider_id=manifest.provider_id,
                candidates=[
                    {
                        "adapter": asdict(manifest),
                        "capability": asdict(capability),
                        "health": asdict(health),
                        "eligible": eligible,
                        "priority": capability.priority,
                        "reasons": reasons,
                    }
                ],
                reasons=["eligible_adapter_selected"],
                metadata={"policy": self.load_policy()},
            )
        raise NotFound(f"Speech adapter not found: {provider_id}")

    @staticmethod
    def _eligibility(
        manifest: SpeechAdapterManifest,
        capability: SpeechAdapterCapability,
        health: SpeechAdapterHealth,
        policy: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not policy.get("enabled", True):
            reasons.append("speech_adapters_disabled")
        if not capability.enabled:
            reasons.append("capability_disabled")
        if manifest.adapter_id in set(policy.get("disabled_adapters", [])):
            reasons.append("disabled_by_policy")
        if manifest.requires_network and not policy.get("allow_network_adapters", False):
            reasons.append("network_not_allowed")
        if manifest.requires_gpu and not policy.get("allow_gpu_adapters", False):
            reasons.append("gpu_not_allowed")
        if health.status == "unavailable":
            reasons.append("adapter_unavailable")
        return not reasons, reasons or ["eligible"]


def _health(manifest: SpeechAdapterManifest) -> SpeechAdapterHealth:
    return SpeechAdapterHealth(
        adapter_id=manifest.adapter_id,
        provider_id=manifest.provider_id,
        status="unconfigured",
        checked_at=_now(),
        message="Mock speech adapter is deterministic and does not execute a real provider.",
        metadata={"adapter_type": manifest.adapter_type},
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
