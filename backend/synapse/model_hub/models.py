from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMRecommendation:
    category: str
    model_name: str
    status: str
    reason: str
    runtime_suggested: str
    estimated_ram_gb: float | None = None
    estimated_vram_gb: float | None = None
    model_id: str | None = None
    provider: str | None = None
    source: str = "suggested"
    highlight: str | None = None


@dataclass(frozen=True)
class ModelCatalogEntry:
    id: str
    name: str
    provider: str
    runtime: str
    origin: str
    type: str
    availability_state: str = "unavailable"
    chat_usable: bool = False
    quantization: str | None = None
    size_bytes: int | None = None
    context_window: int | None = None
    estimated_ram_gb: float | None = None
    estimated_vram_gb: float | None = None
    cpu_compatible: bool = True
    gpu_compatible: bool = True
    status: str = "available"
    is_default: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelProviderInfo:
    provider_id: str
    display_name: str
    status: str
    endpoint: str | None
    active: bool
    default_model: str | None
    model_count: int
    last_refreshed_at: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelFolder:
    folder_id: str
    path: str
    enabled: bool = True
    added_at: str | None = None
    last_refreshed_at: str | None = None
    model_count: int = 0


@dataclass(frozen=True)
class ModelHubDefaults:
    default_chat_model: str | None = None
    default_provider: str | None = None
    preferred_runtime: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ModelHubRefreshResult:
    refreshed_at: str
    catalog_size: int
    provider_count: int
    folder_count: int
    errors: list[str] = field(default_factory=list)
