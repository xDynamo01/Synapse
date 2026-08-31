from __future__ import annotations

import os
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.serialization import load_structured_file
from synapse.observability.correlation import current_correlation
from synapse.providers.models import (
    CapabilityProvider,
    ProviderHealth,
    ProviderManifest,
)
from synapse.providers.registry import ProviderRegistry

DEFAULT_POLICY: dict[str, Any] = {
    "allow_network_providers": False,
    "allow_gpu_providers": False,
    "prefer_local_providers": True,
    "disabled_providers": [],
    "provider_priority_overrides": {},
}


class ProviderRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        self.data_dir = data_dir
        self.registry = registry
        self.event_bus = event_bus
        for manifest in self.registry.list_providers():
            self._emit("provider.registered", manifest.provider_id, asdict(manifest))

    def list_providers(self) -> list[ProviderManifest]:
        return self.registry.list_providers()

    def get_provider(self, provider_id: str) -> ProviderManifest:
        return self.registry.get_provider(provider_id)

    def provider_health(self, provider_id: str) -> ProviderHealth:
        manifest = self.get_provider(provider_id)
        policy = self.load_policy()
        status = "unconfigured"
        message = "Provider manifest is registered but no real provider is configured."
        if provider_id in set(policy.get("disabled_providers", [])):
            status = "unavailable"
            message = "Provider is disabled by provider policy."
        elif not manifest.enabled:
            status = "unavailable"
            message = "Provider manifest is disabled."
        elif manifest.requires_network and not policy.get("allow_network_providers", False):
            status = "unavailable"
            message = "Network providers are disabled by provider policy."
        elif manifest.requires_gpu and not policy.get("allow_gpu_providers", False):
            status = "unavailable"
            message = "GPU providers are disabled by provider policy."
        health = ProviderHealth(
            provider_id=provider_id,
            status=status,
            checked_at=_now(),
            message=message,
            metadata={
                "provider_type": manifest.provider_type,
                "capabilities": list(manifest.capabilities),
            },
            configured=status != "unconfigured",
            enabled=manifest.enabled
            and provider_id not in set(policy.get("disabled_providers", [])),
        )
        self._emit("provider.health_checked", provider_id, asdict(health))
        return health

    def list_provider_health(self) -> list[ProviderHealth]:
        return [self.provider_health(provider.provider_id) for provider in self.list_providers()]

    def resolve_provider_for_capability(self, capability_id: str) -> CapabilityProvider:
        candidates = self._eligible_capability_providers(capability_id)
        if not candidates:
            self._emit(
                "provider.resolution.failed",
                "providers",
                {
                    "capability_id": capability_id,
                    "reason": "no_eligible_provider",
                },
            )
            raise NotFound(f"No eligible provider for capability: {capability_id}")
        selected = candidates[0]
        self._emit(
            "provider.resolution.completed",
            selected.provider_id,
            {
                "capability_id": capability_id,
                "provider_id": selected.provider_id,
                "priority": selected.priority,
            },
        )
        return selected

    def explain_provider_resolution(self, capability_id: str) -> dict[str, Any]:
        policy = self.load_policy()
        registered = self.registry.list_capability_providers(capability_id)
        candidates: list[dict[str, Any]] = []
        for capability_provider in registered:
            provider = self.registry.get_provider(capability_provider.provider_id)
            eligible, reasons = self._eligibility(provider, capability_provider, policy)
            candidates.append(
                {
                    "capability_provider": asdict(capability_provider),
                    "provider": asdict(provider),
                    "eligible": eligible,
                    "reasons": reasons,
                }
            )
        selected = None
        try:
            selected = asdict(self.resolve_provider_for_capability(capability_id))
        except NotFound:
            selected = None
        return {
            "capability_id": capability_id,
            "selected": selected,
            "candidates": candidates,
            "policy": policy,
        }

    def load_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.data_dir.resolve("config/provider_policy.yaml"))
        policy_raw = raw.get("providers", raw)
        policy = dict(DEFAULT_POLICY)
        policy.update(policy_raw)
        return policy

    def _eligible_capability_providers(self, capability_id: str) -> list[CapabilityProvider]:
        policy = self.load_policy()
        candidates: list[CapabilityProvider] = []
        overrides = policy.get("provider_priority_overrides", {})
        for capability_provider in self.registry.list_capability_providers(capability_id):
            provider = self.registry.get_provider(capability_provider.provider_id)
            eligible, _ = self._eligibility(provider, capability_provider, policy)
            if not eligible:
                continue
            priority = int(overrides.get(provider.provider_id, capability_provider.priority))
            candidates.append(
                CapabilityProvider(
                    capability_id=capability_provider.capability_id,
                    provider_id=capability_provider.provider_id,
                    priority=priority,
                    enabled=capability_provider.enabled,
                    metadata=capability_provider.metadata,
                )
            )
        return sorted(candidates, key=lambda item: item.priority)

    def _eligibility(
        self,
        provider: ProviderManifest,
        capability_provider: CapabilityProvider,
        policy: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not capability_provider.enabled:
            reasons.append("capability_provider_disabled")
        if not provider.enabled:
            reasons.append("provider_disabled")
        if provider.provider_id in set(policy.get("disabled_providers", [])):
            reasons.append("disabled_by_policy")
        if provider.requires_network and not policy.get("allow_network_providers", False):
            reasons.append("network_not_allowed")
        if provider.requires_gpu and not policy.get("allow_gpu_providers", False):
            reasons.append("gpu_not_allowed")
        if provider.metadata.get("mock") and not self._development_mode_enabled():
            reasons.append("mock_requires_explicit_development_mode")
        return not reasons, reasons or ["eligible"]

    def _development_mode_enabled(self) -> bool:
        if os.getenv("SYNAPSE_DEV_MODE", "").lower() in {"1", "true", "yes"}:
            return True
        raw = load_structured_file(self.data_dir.resolve("config/system.yaml"))
        mode = str(raw.get("system", raw).get("mode", "")).lower()
        return mode in {"test", "development", "dev"}

    def _emit(self, event_type: str, source: str, payload: dict[str, Any]) -> None:
        correlation = current_correlation()
        if correlation:
            payload = {**payload, "correlation_id": correlation.correlation_id}
        self.event_bus.emit(event_type, source, payload)


def _now() -> str:
    return datetime.now(UTC).isoformat()
