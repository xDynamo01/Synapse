from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AgentMemoryScope(StrEnum):
    NONE = "none"
    TASK = "task"
    MISSION_SHARED = "mission_shared"


class EphemeralAgentState(StrEnum):
    PLANNED = "planned"
    PROVISIONING = "provisioning"
    READY = "ready"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


@dataclass(frozen=True)
class EphemeralAgentSpec:
    mission_id: str
    parent_agent_id: str
    role: str
    objective: str
    created_by: str
    correlation_id: str
    spec_id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str | None = None
    required_capabilities: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    preferred_model_requirements: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    context_scope: dict[str, Any] = field(default_factory=dict)
    memory_scope: AgentMemoryScope = AgentMemoryScope.TASK
    autonomy_ceiling: str = "manual"
    risk_ceiling: str = "low"
    max_context_tokens: int = 8192
    max_execution_time: int = 900
    max_retries: int = 1
    lease_duration: int = 300
    provenance: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    project_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    rfc_checksum: str | None = None
    implementation_plan_id: str | None = None
    implementation_plan_revision: int | None = None
    implementation_plan_checksum: str | None = None
    information_classification: str = "internal"
    information_categories: tuple[str, ...] = ()
    allowed_processing_boundaries: tuple[str, ...] = ()
    allowed_provider_profiles: tuple[str, ...] = ()
    external_processing_policy: str = "policy-controlled"
    training_use_policy: str = "prohibited"
    can_approve_egress: bool = False


@dataclass(frozen=True)
class EphemeralAgentInstance:
    ephemeral_agent_id: str
    spec_id: str
    mission_id: str
    task_id: str | None
    parent_agent_id: str
    state: EphemeralAgentState
    created_at: str
    expires_at: str
    correlation_id: str
    worker_id: str | None = None
    ready_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    last_heartbeat: str | None = None
    current_attempt_id: str | None = None
    model_selection: dict[str, Any] = field(default_factory=dict)
    tool_scope: list[str] = field(default_factory=list)
    context_reference: str | None = None
    scratchpad_reference: str | None = None
    result_reference: str | None = None
    failure: dict[str, Any] | None = None
    revision: int = 1
    schema_version: int = 1


@dataclass(frozen=True)
class EphemeralAgentResult:
    ephemeral_agent_id: str
    mission_id: str
    task_id: str | None
    attempt_ids: list[str]
    status: str
    output_reference: str | None
    started_at: str | None
    completed_at: str
    trace_id: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    failure: dict[str, Any] | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    revision: int = 1
    schema_version: int = 1


@dataclass(frozen=True)
class EphemeralWorkforcePlan:
    mission_id: str
    required: bool
    reason: str
    agents: list[EphemeralAgentSpec]
    max_concurrency: int
    execution_order: list[list[str]]
    strategy: str
    resource_estimate: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    approval_required: bool = False
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class EphemeralCleanupResult:
    dry_run: bool
    scanned: int
    eligible: int
    destroyed: int
    preserved: int
    agent_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
