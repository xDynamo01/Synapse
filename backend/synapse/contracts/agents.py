from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractEvent, now_iso


@dataclass(frozen=True)
class AgentIdentityDTO:
    agent_id: str
    display_name: str | None = None
    role: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class AgentConfigDTO:
    agent_id: str
    default_model: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    autonomy: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class AgentRuntimeStateDTO:
    agent_id: str
    state: str
    current_task_id: str | None = None
    current_session_id: str | None = None
    updated_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class AgentMemoryDTO:
    agent_id: str
    memory_scope: str
    entries: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class AgentToolsDTO:
    agent_id: str
    tools: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class AgentPolicyDTO:
    agent_id: str
    allowed_tools: list[str] = field(default_factory=list)
    approval_required_for: list[str] = field(default_factory=list)
    can_delegate: bool = False
    default_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class AgentWorkerStateDTO:
    agent_id: str
    mode: str
    pending_jobs: int = 0
    last_error: str | None = None
    updated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class AgentContract(Protocol):
    def describe(self, agent_id: str) -> AgentIdentityDTO: ...

    def load_config(self, agent_id: str) -> AgentConfigDTO: ...

    def get_runtime_state(self, agent_id: str) -> AgentRuntimeStateDTO: ...

    def get_policy(self, agent_id: str) -> AgentPolicyDTO: ...

    def emit(self, event: ContractEvent) -> None: ...
