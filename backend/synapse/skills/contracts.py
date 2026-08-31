from __future__ import annotations

from typing import Any, Protocol

from synapse.skills.models import (
    SkillLoadRequest,
    SkillLoadResult,
    SkillResolutionRequest,
    SkillResolutionResult,
    SkillScriptDescriptor,
)


class SkillResolutionPort(Protocol):
    def resolve(self, request: SkillResolutionRequest) -> SkillResolutionResult: ...
    def load(self, request: SkillLoadRequest) -> SkillLoadResult: ...
    def load_assigned(
        self,
        agent_id: str,
        *,
        project_id: str | None = None,
        context_budget: int = 8000,
    ) -> tuple[SkillLoadResult, ...]: ...
    def assignment_summaries(self, agent_id: str) -> tuple[dict[str, Any], ...]: ...


class SkillScriptExecutionPort(Protocol):
    def preview(
        self, descriptor: SkillScriptDescriptor, inputs: dict[str, Any], *, actor_id: str
    ) -> Any: ...
    def execute(
        self,
        descriptor: SkillScriptDescriptor,
        inputs: dict[str, Any],
        *,
        actor_id: str,
        approval_id: str | None = None,
    ) -> Any: ...


class SkillPolicyPort(Protocol):
    def authorize(self, operation: str, context: dict[str, Any]) -> bool: ...


class SkillRecordStore(Protocol):
    def put(
        self, record_id: str, payload: dict[str, Any], *, create_only: bool = False
    ) -> None: ...
    def delete(self, record_id: str) -> None: ...
    def list(self, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]: ...


class SkillLeasePort(Protocol):
    def grant_for_ephemeral(
        self,
        ephemeral_agent_id: str,
        skill_ids: tuple[str, ...],
        *,
        mission_id: str,
        task_id: str | None,
        expires_at: str,
        context_budget: int,
        allowed_tools: tuple[str, ...],
        correlation_id: str | None,
    ) -> tuple[dict[str, Any], ...]: ...
    def cleanup_leases(self, ephemeral_agent_id: str, *, audit_only: bool = False) -> int: ...
