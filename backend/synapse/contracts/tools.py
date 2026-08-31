from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractError, ContractEvent, now_iso


@dataclass(frozen=True)
class ToolSpecDTO:
    tool_id: str
    name: str
    description: str
    permission: str | None = None
    risk: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class ToolExecutionRequestDTO:
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    caller_id: str | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class ToolExecutionResultDTO:
    tool_id: str
    ok: bool
    output: Any | None = None
    error: ContractError | None = None
    executed_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class ToolProvider(Protocol):
    def list_tools(self) -> list[ToolSpecDTO]: ...

    def describe(self, tool_id: str) -> ToolSpecDTO: ...

    def execute(self, request: ToolExecutionRequestDTO) -> ToolExecutionResultDTO: ...

    def emit(self, event: ContractEvent) -> None: ...
