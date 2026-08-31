from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractEvent, now_iso


@dataclass(frozen=True)
class MissionTaskDTO:
    task_id: str
    title: str
    status: str
    depends_on: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class MissionDTO:
    mission_id: str
    title: str
    status: str
    priority: str | None = None
    progress_percent: float = 0.0
    tasks: list[MissionTaskDTO] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class MissionRuntimeStateDTO:
    mission_id: str
    state: str
    queue_depth: int = 0
    last_error: str | None = None
    updated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class MissionRuntime(Protocol):
    def create(self, mission: MissionDTO) -> MissionDTO: ...

    def get(self, mission_id: str) -> MissionDTO: ...

    def list_tasks(self, mission_id: str) -> list[MissionTaskDTO]: ...

    def state(self, mission_id: str) -> MissionRuntimeStateDTO: ...

    def emit(self, event: ContractEvent) -> None: ...
