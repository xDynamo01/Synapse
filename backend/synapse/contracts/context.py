from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractEvent, now_iso
from .memory import MemorySnapshotDTO


@dataclass(frozen=True)
class ContextRequestDTO:
    agent_id: str
    conversation_id: str | None = None
    mission_id: str | None = None
    session_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    perception: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class ContextSnapshotDTO:
    agent_id: str
    conversation_id: str | None = None
    mission_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    memory: MemorySnapshotDTO | None = None
    loaded_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class ContextProvider(Protocol):
    def build(self, request: ContextRequestDTO) -> ContextSnapshotDTO: ...

    def emit(self, event: ContractEvent) -> None: ...
