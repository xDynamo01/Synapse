from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ProviderType = str
ProviderHealthStatus = str

PROVIDER_TYPES: set[str] = {
    "stt",
    "tts",
    "voice_analysis",
    "vision",
    "face_tracking",
    "body_tracking",
    "search",
    "vector_store",
    "model",
    "generic",
}

PROVIDER_HEALTH_STATUSES: set[str] = {
    "available",
    "unavailable",
    "degraded",
    "unconfigured",
    "configured",
    "enabled",
    "reachable",
    "authenticated",
    "misconfigured",
}


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    name: str
    description: str
    provider_type: ProviderType
    capabilities: list[str]
    version: str
    enabled: bool
    local_only: bool
    requires_network: bool
    requires_gpu: bool
    supported_platforms: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderHealth:
    provider_id: str
    status: ProviderHealthStatus
    checked_at: str
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    configured: bool = False
    enabled: bool = False
    reachable: bool | None = None
    authenticated: bool | None = None
    latency_ms: int | None = None
    model_count: int | None = None


@dataclass(frozen=True)
class CapabilityProvider:
    capability_id: str
    provider_id: str
    priority: int
    enabled: bool
    metadata: dict[str, Any] = field(default_factory=dict)
