from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderPluginManifest:
    plugin_id: str
    name: str
    description: str
    version: str
    plugin_type: str  # speech, vision, memory, search, model, generic
    providers: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    adapters: list[str] = field(default_factory=list)
    enabled: bool = False
    installed: bool = False
    local_only: bool = True
    requires_network: bool = False
    requires_gpu: bool = False
    supported_platforms: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    entrypoint: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderPluginHealth:
    plugin_id: str
    status: str  # available, unavailable, degraded, not_installed, disabled, incompatible
    checked_at: str
    message: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderPluginInstallState:
    plugin_id: str
    installed: bool
    enabled: bool
    version: str
    installed_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderPluginSummary:
    total_plugins: int
    installed_plugins: int
    enabled_plugins: int
    unavailable_plugins: int
    by_type: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] | None = None
