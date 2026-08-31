from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MissionStatus(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MissionTaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    DEAD_LETTERED = "dead_lettered"


class WorkerStatus(StrEnum):
    OFFLINE = "offline"
    IDLE = "idle"
    BUSY = "busy"
    SLEEPING = "sleeping"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class AttemptStatus(StrEnum):
    CREATED = "created"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_TOOL = "waiting_tool"
    WAITING_MODEL = "waiting_model"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    RECOVERY_PENDING = "recovery_pending"
    DEAD_LETTERED = "dead_lettered"


class SwarmStrategy(StrEnum):
    LEADER_WORKER = "leader_worker"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    REVIEW_LOOP = "review_loop"


MISSION_STATUSES = {item.value for item in MissionStatus} | {"active", "archived"}
MISSION_PRIORITIES = {"low", "normal", "high", "critical"}
TASK_STATUSES = {item.value for item in MissionTaskStatus}


@dataclass(frozen=True)
class Mission:
    title: str
    objective: str = ""
    description: str = ""
    status: str = MissionStatus.DRAFT
    priority: str = "normal"
    requester: str | None = None
    plan_id: str | None = None
    progress: float = 0.0
    owner_agent_id: str | None = None
    created_by: str | None = None
    conversation_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    paused_at: str | None = None
    cancelled_at: str | None = None
    deadline: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    mission_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
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

    @property
    def id(self) -> str:
        return self.mission_id


@dataclass(frozen=True)
class MissionTask:
    mission_id: str
    title: str
    objective: str
    status: str = MissionTaskStatus.PENDING
    priority: str = "normal"
    dependencies: list[str] = field(default_factory=list)
    assigned_agent_id: str | None = None
    assigned_worker_id: str | None = None
    required_capabilities: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    expected_output: dict[str, Any] | str | None = None
    verification_policy: dict[str, Any] = field(default_factory=lambda: {"checks": ["non_empty"]})
    attempts: int = 0
    max_attempts: int = 3
    timeout_seconds: int = 300
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    weight: float = 1.0
    started_at: str | None = None
    completed_at: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    task_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @property
    def id(self) -> str:
        return self.task_id


@dataclass(frozen=True)
class PlanValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MissionPlan:
    mission_id: str
    tasks: list[MissionTask]
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    completion_criteria: dict[str, Any] = field(default_factory=dict)
    generated_by: str = "manual"
    provider: str | None = None
    model: str | None = None
    validation_result: PlanValidationResult | None = None
    version: int = 1
    plan_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)

    @property
    def id(self) -> str:
        return self.plan_id


@dataclass(frozen=True)
class WorkerDescriptor:
    worker_id: str
    agent_id: str
    status: str = WorkerStatus.OFFLINE
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    role: str | None = None
    current_task_id: str | None = None
    current_attempt_id: str | None = None
    workload: float = 0.0
    last_heartbeat: str = field(default_factory=now_iso)
    failure_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    revision: int = 1


@dataclass(frozen=True)
class TaskAttempt:
    mission_id: str
    task_id: str
    worker_id: str
    agent_id: str
    attempt_number: int
    status: str = AttemptStatus.CREATED
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    delegation_id: str | None = None
    correlation_id: str | None = None
    completed_at: str | None = None
    timeout_at: str | None = None
    input_snapshot: dict[str, Any] = field(default_factory=dict)
    context_trace_id: str | None = None
    model_selection: dict[str, Any] = field(default_factory=dict)
    tool_call_ids: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    verification_result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    recovery_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    attempt_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @property
    def id(self) -> str:
        return self.attempt_id


@dataclass(frozen=True)
class SwarmDescriptor:
    mission_id: str
    strategy: str
    leader_agent_id: str | None
    member_agent_ids: list[str]
    status: str = "created"
    shared_context_scope: str = "mission"
    metadata: dict[str, Any] = field(default_factory=dict)
    swarm_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ConsolidatedResult:
    mission_id: str
    strategy: str
    outputs: list[dict[str, Any]]
    swarm_id: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verification: dict[str, Any] | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)
    final_output: Any = None
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class MissionDelegationLink:
    mission_id: str
    task_id: str
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class MissionSummary:
    mission_id: str
    total_tasks: int
    pending_tasks: int
    running_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    dlq_tasks: int
