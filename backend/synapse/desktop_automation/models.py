from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class ApplicationInfo:
    application_id: str
    name: str
    pid: int
    executable_name: str
    state: str
    foreground: bool
    window_count: int
    provider: str


@dataclass(frozen=True)
class WindowInfo:
    window_id: str
    application_id: str
    pid: int
    title: str
    state: str
    foreground: bool
    monitor: str | None
    workspace: str | None
    bounds: Bounds | None
    provider: str


@dataclass(frozen=True)
class ElementSelector:
    automation_id: str | None = None
    role: str | None = None
    control_type: str | None = None
    name: str | None = None
    description: str | None = None
    value: str | None = None
    window_id: str | None = None
    ancestor_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UIElement:
    element_id: str
    window_id: str
    automation_id: str | None
    role: str
    control_type: str
    name: str | None
    description: str | None
    value: str | None
    enabled: bool
    focused: bool
    selected: bool | None
    expanded: bool | None
    toggled: bool | None
    range_value: float | None
    bounds: Bounds | None
    patterns: list[str]
    children: list[UIElement] = field(default_factory=list)
    provider: str = "unknown"


@dataclass(frozen=True)
class VerificationSpec:
    kind: str
    selector: ElementSelector | None = None
    expected: Any = None
    window_id: str | None = None


@dataclass(frozen=True)
class AutomationAction:
    kind: str
    selector: ElementSelector | None = None
    application: str | None = None
    window_id: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    verification: VerificationSpec | None = None
    fallback_allowed: bool = True
    max_attempts: int = 2
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class RiskAssessment:
    level: str
    reasons: list[str]
    approval_required: bool
    prohibited: bool = False


@dataclass(frozen=True)
class ActionPreview:
    action_id: str
    kind: str
    target: dict[str, Any]
    risk: RiskAssessment
    expected: dict[str, Any]
    provider_order: list[str]


@dataclass(frozen=True)
class AutomationPlan:
    actor_id: str
    objective: str
    actions: list[AutomationAction]
    status: str = "draft"
    dry_run: bool = False
    previews: list[ActionPreview] = field(default_factory=list)
    approval_id: str | None = None
    current_action: int = 0
    revision: int = 1
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    kind: str
    expected: Any
    observed: Any
    evidence: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    status: str
    provider: str | None
    attempts: int
    verification: VerificationResult
    evidence: list[dict[str, Any]] = field(default_factory=list)
    rollback: dict[str, Any] | None = None
    error_code: str | None = None
    started_at: str = field(default_factory=now_iso)
    completed_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class AutomationResult:
    plan_id: str
    status: str
    actions: list[ActionResult]
    rollback_results: list[dict[str, Any]] = field(default_factory=list)
    approval_id: str | None = None
    error_code: str | None = None
    completed_at: str = field(default_factory=now_iso)


def automation_result_from_dict(value: dict[str, Any]) -> AutomationResult:
    """Rehydrate the frozen Desktop result after crossing the tool boundary."""
    actions = []
    for raw_action in value.get("actions", []):
        raw_verification = raw_action.get("verification", {})
        verification = VerificationResult(**raw_verification)
        actions.append(ActionResult(**{**raw_action, "verification": verification}))
    return AutomationResult(**{**value, "actions": actions})


@dataclass(frozen=True)
class ClipboardSnapshot:
    content_type: str
    digest: str | None
    restorable: bool
    token: str | None = None
