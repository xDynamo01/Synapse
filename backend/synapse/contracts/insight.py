from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractEvent, now_iso


@dataclass(frozen=True)
class SystemInsightDTO:
    os_name: str | None = None
    python_version: str | None = None
    cpu: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    gpu: list[dict[str, Any]] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    status: str = "unknown"
    generated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class SystemInsightProvider(Protocol):
    def inspect(self) -> SystemInsightDTO: ...

    def emit(self, event: ContractEvent) -> None: ...
