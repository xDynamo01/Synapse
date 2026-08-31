from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

POLICY_SCOPES = {
    "system",
    "user",
    "agent",
    "conversation",
    "mission",
    "task",
    "tool",
    "model",
    "voice",
    "perception",
}
POLICY_EFFECTS = {
    "allow",
    "deny",
    "require_approval",
    "require_confirmation",
    "constrain",
    "audit_only",
}
AUTONOMY_LEVELS = (
    "observe_only",
    "suggest",
    "act_reversible",
    "act_local",
    "act_external",
    "act_critical",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class PolicyRule:
    scope: str
    subject: str
    action: str
    resource: str
    effect: str
    source: str
    id: str = field(default_factory=lambda: str(uuid4()))
    conditions: dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    revision: int = 1


@dataclass(frozen=True)
class EffectivePolicy:
    subject: str
    action: str
    resource: str
    decision: str
    matched_rules: list[dict[str, Any]]
    winning_rule: dict[str, Any] | None
    constraints: dict[str, Any]
    approval_required: bool
    reasons: list[str]
    warnings: list[str]
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    evaluated_at: str = field(default_factory=now_iso)
