from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DECISION_CATEGORIES = {
    "capability",
    "tool_execution",
    "agent_provisioning",
    "admin_action",
    "delegation_autonomy",
}


@dataclass(frozen=True)
class DecisionRequest:
    actor_type: str
    action: str
    actor_id: str | None = None
    category: str | None = None
    capability_id: str | None = None
    resource_scope: Any | None = None
    target_agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


@dataclass(frozen=True)
class DecisionResult:
    allowed: bool
    blocked: bool
    requires_approval: bool
    risk_level: str
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    source_policies: list[str] = field(default_factory=list)
    evaluated_components: list[str] = field(default_factory=list)
    approval_required_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
