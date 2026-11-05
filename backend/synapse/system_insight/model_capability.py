from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from synapse.model_hub.models import ModelCatalogEntry, ModelProviderInfo
from synapse.system_insight.models import (
    Evidence,
    HardwareSnapshot,
    ModelCapabilityReport,
    ModelRecommendation,
)

MODEL_TASKS = ("chat", "swarm", "coding", "vision", "speech", "reasoning", "embedding")

# Small offline knowledge base used when a model is not installed yet. These
# are envelopes, not claims that the model is present; the provider/runtime
# status and measured hardware decide whether each entry is usable.
MODEL_PROFILES = (
    ("Qwen3 4B Instruct Q4_K_M", "lmstudio", 5.5, 3.5, ("chat", "reasoning", "coding")),
    ("Qwen2.5-Coder 3B Q4_K_M", "ollama", 4.5, 2.5, ("chat", "coding")),
    ("Llama 3.2 3B Instruct Q4", "synapse_local", 4.0, 2.5, ("chat", "reasoning")),
    ("Phi-3.5-mini Instruct", "lmstudio", 3.5, 2.0, ("chat", "coding")),
)


class ModelCapabilityRuntime:
    def __init__(self, model_hub: Any, hardware: Any):
        self.model_hub = model_hub
        self.hardware = hardware

    def inspect(self, hardware: HardwareSnapshot | None = None) -> ModelCapabilityReport:
        hardware = hardware or self.hardware.inspect()
        models, providers, limitations = self._catalog()
        recommendations = [
            self.recommend(task, hardware, models, providers) for task in MODEL_TASKS
        ]
        return ModelCapabilityReport(
            checked_at=datetime.now(UTC).isoformat(),
            available_models=sum(
                1 for model in models if not bool(model.metadata.get("profile_only"))
            ),
            online_providers=sum(1 for provider in providers if provider.active),
            providers=[_provider_view(provider) for provider in providers],
            recommendations=recommendations,
            limitations=limitations,
        )

    def recommend(
        self,
        task: str,
        hardware: HardwareSnapshot | None = None,
        models: list[ModelCatalogEntry] | None = None,
        providers: list[ModelProviderInfo] | None = None,
        preferred_model: str | None = None,
        preferred_provider: str | None = None,
    ) -> ModelRecommendation:
        hardware = hardware or self.hardware.inspect()
        if models is None or providers is None:
            models, providers, _ = self._catalog()
        online = {provider.provider_id for provider in providers if provider.active}
        candidates = [
            entry
            for entry in models
            if entry.status != "unavailable" and _recommendable_model(entry)
        ]
        ranked = sorted(
            candidates,
            key=lambda entry: self._score(
                entry,
                task,
                hardware,
                online,
                preferred_model,
                preferred_provider,
            ),
            reverse=True,
        )
        fitting = [entry for entry in ranked if self._fits(entry, hardware, online)]
        real_candidates = [
            entry for entry in ranked if not bool(entry.metadata.get("profile_only"))
        ]
        real_fitting = [entry for entry in fitting if not bool(entry.metadata.get("profile_only"))]
        if real_fitting:
            fitting = real_fitting
        if not fitting:
            known_online = [
                entry for entry in (real_candidates or ranked) if entry.provider in online
            ]
            if known_online:
                selected = min(
                    known_online,
                    key=lambda entry: (
                        0
                        if (
                            task in _capabilities(entry)
                            or (task == "chat" and entry.chat_usable)
                        )
                        else 1,
                        entry.estimated_ram_gb or float("inf"),
                        entry.estimated_vram_gb or float("inf"),
                        entry.id,
                    ),
                )
                return ModelRecommendation(
                    task=task,
                    model_id=selected.id,
                    provider_id=selected.provider,
                    status="limited",
                    reason=(
                        "Registered model exists, but measured free resources are "
                        "currently below the recommended execution envelope."
                    ),
                    estimated_ram_gb=selected.estimated_ram_gb,
                    estimated_vram_gb=selected.estimated_vram_gb,
                    evidence=self._hardware_evidence(hardware),
                )
            if ranked:
                selected = ranked[0]
                return ModelRecommendation(
                    task=task,
                    model_id=selected.id,
                    provider_id=selected.provider,
                    status="unavailable",
                    reason=(
                        "The model fits the measured hardware envelope, but its provider "
                        "is not configured or currently available."
                    ),
                    estimated_ram_gb=selected.estimated_ram_gb,
                    estimated_vram_gb=selected.estimated_vram_gb,
                    evidence=self._hardware_evidence(hardware),
                )
            return ModelRecommendation(
                task=task,
                model_id=None,
                provider_id=None,
                status="unavailable",
                reason="No registered online model has sufficient measured capacity.",
                evidence=self._hardware_evidence(hardware),
            )
        selected = fitting[0]
        return ModelRecommendation(
            task=task,
            model_id=selected.id,
            provider_id=selected.provider,
            status="recommended",
            reason="Selected from registered model capabilities and measured free resources.",
            estimated_ram_gb=selected.estimated_ram_gb,
            estimated_vram_gb=selected.estimated_vram_gb,
            evidence=self._hardware_evidence(hardware),
        )

    def recommend_route(
        self,
        task: str,
        preferred_provider: str | None,
        preferred_model: str | None,
    ) -> ModelRecommendation:
        models = self.model_hub.registry.list_models()
        providers = self.model_hub.registry.list_providers()
        if not models:
            return ModelRecommendation(
                task=task,
                model_id=None,
                provider_id=None,
                status="unavailable",
                reason="No registered model capability snapshot is available.",
            )
        return self.recommend(
            task,
            models=models,
            providers=providers,
            preferred_provider=preferred_provider,
            preferred_model=preferred_model,
        )

    def _catalog(self) -> tuple[list[ModelCatalogEntry], list[ModelProviderInfo], list[str]]:
        limitations: list[str] = []
        try:
            # Insight is a bounded, read-only consumer of ModelHub's public registry.
            # Network and filesystem discovery remain the responsibility of ModelHub.refresh().
            models = self.model_hub.registry.list_models()
            providers = self.model_hub.registry.list_providers()
        except Exception as exc:
            models = []
            providers = []
            limitations.append(f"model_registry_unavailable:{type(exc).__name__}")
        if not models:
            limitations.append("no_registered_models")
        if not providers:
            limitations.append("no_provider_status_snapshot")
        known = {(item.provider, item.name.casefold()) for item in models}
        for name, provider, ram, vram, capabilities in MODEL_PROFILES:
            if (provider, name.casefold()) in known:
                continue
            models.append(
                ModelCatalogEntry(
                    id=f"profile:{provider}:{name.lower().replace(' ', '-')}",
                    name=name,
                    provider=provider,
                    runtime=provider,
                    origin="Synapse Insight model requirements",
                    type="chat",
                    availability_state="profile-only",
                    chat_usable=True,
                    estimated_ram_gb=ram,
                    estimated_vram_gb=vram,
                    metadata={"capabilities": list(capabilities), "profile_only": True},
                )
            )
        return models, providers, limitations

    def _fits(
        self,
        entry: ModelCatalogEntry,
        hardware: HardwareSnapshot,
        online: set[str],
    ) -> bool:
        if entry.provider not in online:
            return False
        available_ram_gb = hardware.memory.available_bytes / 1024**3
        if entry.estimated_ram_gb is not None and entry.estimated_ram_gb > available_ram_gb * 0.9:
            return False
        if entry.estimated_vram_gb and entry.estimated_vram_gb > 0:
            free_vram = (
                max(
                    (gpu.memory_free_bytes or 0 for gpu in hardware.gpus),
                    default=0,
                )
                / 1024**3
            )
            if free_vram < entry.estimated_vram_gb and not entry.cpu_compatible:
                return False
        return True

    def _score(
        self,
        entry: ModelCatalogEntry,
        task: str,
        hardware: HardwareSnapshot,
        online: set[str],
        preferred_model: str | None,
        preferred_provider: str | None,
    ) -> tuple[int, int, int, float, float]:
        capabilities = _capabilities(entry)
        task_match = int(task in capabilities or (task == "chat" and entry.chat_usable))
        preferred_tokens = {
            entry.id.casefold(),
            entry.name.casefold(),
            f"{entry.provider}/{entry.name}".casefold(),
            f"{entry.provider}:{entry.name}".casefold(),
        }
        normalized_preferred = preferred_model.casefold() if preferred_model else None
        preferred = int(
            normalized_preferred is not None
            and normalized_preferred in preferred_tokens
            and (preferred_provider is None or entry.provider == preferred_provider)
        )
        fit = int(self._fits(entry, hardware, online))
        # Prefer the most capable fitting model; pressure changes naturally move
        # selection to a smaller registered model when the larger one no longer fits.
        size = entry.estimated_ram_gb or 0.0
        installed = int(not bool(entry.metadata.get("profile_only")))
        return fit, task_match, preferred, installed, size

    @staticmethod
    def _hardware_evidence(hardware: HardwareSnapshot) -> list[Evidence]:
        evidence = [
            Evidence(
                hardware.provider,
                "memory_available_bytes",
                hardware.memory.available_bytes,
                "bytes",
                hardware.collected_at,
            )
        ]
        for index, gpu in enumerate(hardware.gpus):
            evidence.append(
                Evidence(
                    gpu.provider,
                    f"gpu_{index}_memory_free_bytes",
                    gpu.memory_free_bytes,
                    "bytes",
                    hardware.collected_at,
                )
            )
        return evidence


def _merge_models(*groups: list[ModelCatalogEntry]) -> list[ModelCatalogEntry]:
    merged: dict[tuple[str, str], ModelCatalogEntry] = {}
    for group in groups:
        for model in group:
            merged[(model.provider, model.id)] = model
    return list(merged.values())


def _capabilities(entry: ModelCatalogEntry) -> set[str]:
    values = entry.metadata.get("capabilities", []) if isinstance(entry.metadata, dict) else []
    capabilities = {str(value).lower() for value in values if str(value).strip()}
    if entry.chat_usable:
        capabilities.add("chat")
    if entry.type in MODEL_TASKS:
        capabilities.add(entry.type)
    return capabilities


def _recommendable_model(entry: ModelCatalogEntry) -> bool:
    path = str(entry.metadata.get("path") or "") if isinstance(entry.metadata, dict) else ""
    identity = "/".join([entry.id, entry.name, path]).replace("\\", "/").lower()
    if any(segment.startswith("mmproj") for segment in identity.split("/")):
        return False
    if entry.chat_usable:
        return True
    if entry.type in {"chat", "gguf", "ggml", "bin"}:
        return True
    return bool(_capabilities(entry))


def _provider_view(provider: ModelProviderInfo) -> dict[str, Any]:
    return {
        "provider_id": provider.provider_id,
        "status": provider.status,
        "active": provider.active,
        "model_count": provider.model_count,
        "last_refreshed_at": provider.last_refreshed_at,
    }
