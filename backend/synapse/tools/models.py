from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from synapse.resources.models import ResourceRef

ToolHandler = Callable[["ToolExecutionRequest"], dict[str, Any]]
RiskLevel = str
CallerType = str
TOOL_EXECUTION_STATUSES = {
    "pending",
    "awaiting_approval",
    "running",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    "rolled_back",
    "rollback_failed",
}


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    display_name: str
    description: str
    category: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    required_capability: str | None = None
    required_permission: str | None = None
    resource_scope_required: bool = False
    approval_required: bool = False
    risk_level: RiskLevel = "low"
    version: str = "1.0.0"
    provider_id: str = "internal"
    source: str = "builtin"
    capabilities: list[str] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    supports_preview: bool = True
    supports_dry_run: bool = True
    supports_cancel: bool = False
    supports_rollback: bool = False
    timeout_default: float = 30.0


@dataclass(frozen=True)
class ToolExecutionRequest:
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    caller: str = "system"
    caller_type: CallerType = "system"
    agent_id: str | None = None
    conversation_id: str | None = None
    mission_id: str | None = None
    resource_ref: ResourceRef | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    dry_run: bool = False
    id: str | None = None
    requester: str | None = None
    approval_id: str | None = None
    timeout_seconds: float | None = None
    retry_policy: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolExecutionResult:
    success: bool
    tool_id: str
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    status: str = "completed"
    structured_output: dict[str, Any] | None = None
    started_at: str | None = None
    completed_at: str | None = None
    side_effects: list[str] = field(default_factory=list)
    rollback_status: str | None = None
    logs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCallPreview:
    tool_id: str
    normalized_arguments: dict[str, Any]
    permissions_required: list[str]
    risk_level: str
    approval_required: bool
    side_effects: list[str]
    reversible: bool
    estimated_duration: float | None
    warnings: list[str]
    conflicts: list[str]
    target_resources: list[str]
    config_hash: str


@dataclass(frozen=True)
class ToolHealth:
    available: bool
    enabled: bool
    execution_count: int = 0
    failure_count: int = 0


@dataclass(frozen=True)
class ToolExecutionDecision:
    allowed: bool
    blocked: bool
    requires_approval: bool
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    approval_id: str | None = None
    policy_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler
