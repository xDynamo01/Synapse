from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

ADMIN_ACTIONS = {
    "agent.activate",
    "agent.deactivate",
    "agent.archive",
    "agent.restore",
    "agent.validate",
    "agent.update",
    "agent.delete",
}


@dataclass(frozen=True)
class AdminAction:
    action: str
    agent_id: str
    actor_id: str | None = None
    actor_type: str | None = None


@dataclass(frozen=True)
class AdminPolicy:
    allow_user_admin_actions: bool = True
    require_approval_for_archive: bool = False
    require_approval_for_deactivate: bool = False
    require_approval_for_restore: bool = False
    protected_agents: list[str] = field(default_factory=list)
    blocked_admin_actions: list[str] = field(default_factory=list)
    admin_capabilities_required: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdminDecision:
    action: str
    agent_id: str
    allowed: bool
    requires_approval: bool = False
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    required_permission: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
