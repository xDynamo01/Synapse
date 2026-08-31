from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SkillScope(StrEnum):
    SYSTEM = "system"
    USER = "user"
    WORKSPACE = "workspace"
    PROJECT = "project"
    AGENT = "agent"
    MISSION = "mission"
    TASK = "task"


SCOPE_PRECEDENCE = tuple(SkillScope)
SKILL_STATUSES = {"draft", "active", "deprecated", "disabled"}
LOAD_LEVELS = (
    "metadata_only",
    "instructions",
    "references",
    "resources",
    "scripts_metadata",
    "full_authorized",
)


@dataclass(frozen=True)
class SkillDependency:
    skill_id: str
    version_constraint: str = "*"
    optional: bool = False
    reason: str = ""


@dataclass(frozen=True)
class SkillConflict:
    skill_id: str
    version_constraint: str | None = None
    reason: str = ""
    severity: str = "critical"


@dataclass(frozen=True)
class SkillScriptDescriptor:
    script_id: str
    runtime: str
    entrypoint: str
    checksum: str
    purpose: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    permissions: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    timeout: float = 30.0
    deterministic: bool = False
    side_effects: tuple[str, ...] = ()
    sandbox_required: bool = True


@dataclass(frozen=True)
class SkillManifest:
    skill_id: str
    name: str
    version: str
    description: str
    summary: str
    authorship: tuple[str, ...]
    status: str
    scopes: tuple[SkillScope, ...]
    supported_agent_kinds: tuple[str, ...]
    activation: dict[str, Any] = field(default_factory=dict)
    requirements: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[SkillDependency, ...] = ()
    conflicts: tuple[SkillConflict, ...] = ()
    tools: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    scripts: tuple[SkillScriptDescriptor, ...] = ()
    context_policy: dict[str, Any] = field(default_factory=dict)
    permissions: tuple[str, ...] = ()
    output_contract: dict[str, Any] | None = None
    compatibility: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_project: bool = False
    requires_rfc_for_change_classes: tuple[str, ...] = ()
    allowed_rfc_statuses: tuple[str, ...] = ("approved", "implementing")
    consumes_rfc_sections: tuple[str, ...] = ()
    produces_evidence_types: tuple[str, ...] = ()
    required_quality_gates: tuple[str, ...] = ()
    allowed_classifications: tuple[str, ...] = ()
    external_processing_allowed: bool = False
    private_only: bool = False
    data_categories_consumed: tuple[str, ...] = ()
    provider_trust_requirements: tuple[str, ...] = ()
    telemetry_retention: str = "local-only"
    output_classification_rule: str = "most-restrictive-input"


@dataclass(frozen=True)
class SkillPackage:
    manifest: SkillManifest
    root: Path
    instructions_path: Path
    checksum: str
    installed: bool = False


@dataclass(frozen=True)
class SkillDescriptor:
    skill_id: str
    version: str
    name: str
    summary: str
    scopes: tuple[str, ...]
    tags: tuple[str, ...]
    supported_agent_kinds: tuple[str, ...]
    activation_hints: tuple[str, ...]
    requirements_summary: dict[str, tuple[str, ...]]
    status: str
    relevance: float = 0.0


@dataclass(frozen=True)
class SkillResolutionRequest:
    objective: str
    explicit_skill_ids: tuple[str, ...] = ()
    agent_id: str | None = None
    agent_kind: str = "persistent"
    workspace_id: str | None = None
    project_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    available_tools: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    policy_context: dict[str, Any] = field(default_factory=dict)
    context_budget: int = 8000
    correlation_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    rfc_checksum: str | None = None
    change_class: str | None = None
    required_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillResolutionResult:
    selected: tuple[SkillDescriptor, ...] = ()
    rejected: tuple[dict[str, Any], ...] = ()
    unavailable: tuple[str, ...] = ()
    conflicts: tuple[dict[str, Any], ...] = ()
    missing_dependencies: tuple[str, ...] = ()
    missing_tools: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    ordering: tuple[str, ...] = ()
    estimated_context_cost: int = 0
    warnings: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillLoadRequest:
    skill_id: str
    version: str
    level: str = "instructions"
    references: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    context_budget: int = 8000
    authorized_scripts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillLoadResult:
    skill_id: str
    version: str
    level: str
    instructions: str = ""
    references: dict[str, str] = field(default_factory=dict)
    resources: dict[str, str] = field(default_factory=dict)
    scripts: tuple[SkillScriptDescriptor, ...] = ()
    loaded: tuple[str, ...] = ()
    omissions: tuple[str, ...] = ()
    bytes_loaded: int = 0
    token_estimate: int = 0
    checksum: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillAssignment:
    agent_id: str
    skill_id: str
    version_constraint: str
    scope: SkillScope = SkillScope.AGENT
    enabled: bool = True
    auto_discovery: bool = True
    explicit_only: bool = False
    priority: int = 0
    assigned_by: str = "system"
    assignment_id: str = field(default_factory=lambda: str(uuid4()))
    assigned_at: str = field(default_factory=now_iso)
    revision: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillLease:
    ephemeral_agent_id: str
    skill_id: str
    resolved_version: str
    mission_id: str | None
    task_id: str | None
    expires_at: str
    context_budget: int
    allowed_resources: tuple[str, ...] = ()
    allowed_scripts: tuple[str, ...] = ()
    tool_scope: tuple[str, ...] = ()
    lease_id: str = field(default_factory=lambda: str(uuid4()))
    granted_at: str = field(default_factory=now_iso)
    revision: int = 1
    status: str = "granted"
    correlation_id: str | None = None
