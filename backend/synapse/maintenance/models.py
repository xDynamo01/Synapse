from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MaintenanceCapability(StrEnum):
    INSPECT = "inspect"
    VALIDATE = "validate"
    CLEANUP = "cleanup"
    RECOVERY = "recovery"
    BACKUP = "backup"
    RESTORE = "restore"
    MIGRATION = "migration"


class MaintenanceScopeKind(StrEnum):
    ALL = "all"
    CONTRIBUTOR = "contributor"
    CAPABILITY = "capability"
    DOMAIN = "domain"
    CATEGORY = "category"


@dataclass(frozen=True)
class MaintenanceScope:
    kind: MaintenanceScopeKind = MaintenanceScopeKind.ALL
    value: str | None = None


@dataclass(frozen=True)
class MaintenanceInspectionRequest:
    scope: MaintenanceScope = field(default_factory=MaintenanceScope)
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class MaintenancePlanRequest:
    scope: MaintenanceScope = field(default_factory=MaintenanceScope)
    older_than_hours: int = 24
    expires_in_seconds: int = 1800
    dry_run: bool = True
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class MaintenanceExecutionRequest:
    plan_id: str
    checksum: str
    expected_revision: int
    confirmed: bool
    approval_id: str | None = None
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class MaintenanceFinding:
    contributor_id: str
    category: str
    severity: str
    status: str
    summary: str
    reference: str
    recommended_action: str
    safe_to_automate: bool
    approval_required: bool
    correlation_id: str
    finding_id: str = field(default_factory=lambda: str(uuid4()))
    estimated_bytes: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaintenanceInspectionResult:
    contributor_id: str
    status: str
    findings: list[MaintenanceFinding]
    capabilities: list[str]
    inspected_at: str = field(default_factory=now_iso)
    warnings: list[str] = field(default_factory=list)
    error_code: str | None = None


@dataclass(frozen=True)
class MaintenanceInspectionReport:
    status: str
    results: list[MaintenanceInspectionResult]
    findings: list[MaintenanceFinding]
    correlation_id: str
    started_at: str
    completed_at: str
    duration_ms: float


@dataclass(frozen=True)
class MaintenanceAction:
    contributor_id: str
    category: str
    reference: str
    risk: str
    approval_required: bool
    estimated_bytes: int = 0
    parameters: dict[str, Any] = field(default_factory=dict)
    action_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class MaintenancePlan:
    plan_id: str
    created_at: str
    expires_at: str
    scope: MaintenanceScope
    findings: list[MaintenanceFinding]
    actions: list[MaintenanceAction]
    estimated_reclaimed_bytes: int
    risks: list[str]
    approval_required: bool
    checksum: str
    revision: int
    dry_run: bool
    correlation_id: str
    status: str = "planned"
    approval_id: str | None = None


@dataclass(frozen=True)
class MaintenanceActionResult:
    action_id: str
    contributor_id: str
    status: str
    reclaimed_bytes: int = 0
    warning: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class MaintenanceExecutionResult:
    plan_id: str
    status: str
    attempted: int
    completed: int
    skipped: int
    failed: int
    reclaimed_bytes: int
    warnings: list[str]
    errors: list[dict[str, str]]
    started_at: str
    completed_at: str
    trace_id: str
    action_results: list[MaintenanceActionResult] = field(default_factory=list)
    revision: int = 1


@dataclass(frozen=True)
class MaintenanceContributorInfo:
    contributor_id: str
    capabilities: list[str]
    categories: list[str]
    required: bool
    domain: str


@dataclass(frozen=True)
class MaintenanceStatus:
    state: str
    contributor_count: int
    required_contributors: int
    optional_contributors: int
    active_operation: bool
    stale_lock: bool
    last_inspection_at: str | None
    last_execution_at: str | None
    pending_cleanup_count: int
    degraded_contributors: list[str]
