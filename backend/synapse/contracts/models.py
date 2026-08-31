from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractEvent, now_iso


@dataclass(frozen=True)
class ModelProviderDTO:
    provider_id: str
    adapter_id: str | None = None
    provider_type: str | None = None
    enabled: bool = True
    status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class ModelRequestDTO:
    model_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class ModelResponseDTO:
    model_id: str
    content: str
    finish_reason: str | None = None
    latency_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class ModelProvider(Protocol):
    def list_models(self) -> list[ModelProviderDTO]: ...

    def health(self) -> ModelProviderDTO: ...

    def generate(self, request: ModelRequestDTO) -> ModelResponseDTO: ...

    def emit(self, event: ContractEvent) -> None: ...


@runtime_checkable
class ModelRuntime(Protocol):
    def resolve_provider(self, model_id: str) -> ModelProviderDTO: ...

    def generate(self, request: ModelRequestDTO) -> ModelResponseDTO: ...

    def list_providers(self) -> list[ModelProviderDTO]: ...
