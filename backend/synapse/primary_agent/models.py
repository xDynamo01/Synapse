from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class PrimaryAgentProfile:
    agent_id: str
    workspace_id: str
    status: str
    assigned_at: str
    conversation_id: str
    interaction_mode: str = "continuous"
    proactive_mode: str = "policy_governed"
    voice_enabled: bool = False
    last_interaction_at: str | None = None
    last_active_at: str | None = None
    revision: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1


@dataclass(frozen=True)
class PrimaryAgentState:
    state: str
    profile: PrimaryAgentProfile | None
    reason: str | None = None


@dataclass(frozen=True)
class PrimaryInteractionBootstrap:
    primary_agent: dict[str, Any] | None
    conversation: dict[str, Any] | None
    agent_status: str
    interaction_status: str
    voice_status: str
    proactive_mode: str
    pending_attention_count: int
    pending_approvals_count: int
    active_missions: list[dict[str, Any]]
    unread_notifications: int
    health_summary: dict[str, Any]
    capabilities: list[str]
    resume_token: str | None
    assigned_skills: list[dict[str, Any]] = field(default_factory=list)
    available_skills: list[dict[str, Any]] = field(default_factory=list)
    project_context: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PrimaryInteractionResult:
    profile: PrimaryAgentProfile
    conversation_status: str
    changed: bool
