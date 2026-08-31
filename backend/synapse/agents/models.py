from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse.core.exceptions import ValidationError
from synapse.core.serialization import load_structured_file


class AgentKind(StrEnum):
    PRIMARY = "primary"
    PERSISTENT = "persistent"
    EPHEMERAL = "ephemeral"


@dataclass(frozen=True)
class AgentConfig:
    id: str
    name: str
    role: str
    can_delegate: bool = False
    preferred_model: str | None = None
    autonomy: str = "manual"
    skills: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    kind: AgentKind = AgentKind.PERSISTENT


@dataclass(frozen=True)
class AgentMessage:
    from_agent: str
    to_agent: str
    subject: str
    body: str
    task_id: str | None = None
    status: str = "pending"
    correlation_id: str | None = None
    causation_id: str | None = None
    parent_id: str | None = None
    source: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def from_agent_id(self) -> str:
        return self.from_agent

    @property
    def to_agent_id(self) -> str:
        return self.to_agent


AGENT_MESSAGE_STATUSES = {"pending", "read", "processed", "failed"}


AgentStatus = str

VALID_AGENT_STATUSES: set[AgentStatus] = {
    "Idle",
    "Listening",
    "Thinking",
    "Researching",
    "Working",
    "Speaking",
    "Offline",
}


def normalize_agent_config(
    raw: dict[str, Any],
    expected_id: str | None = None,
    *,
    require_identity: bool = False,
) -> dict[str, Any]:
    configured_id = str(raw.get("id", "")).strip()
    agent_id = expected_id or configured_id
    if not agent_id:
        raise ValidationError("Agent config id is required.")
    if expected_id and configured_id and configured_id != expected_id:
        raise ValidationError(
            f"Agent config id mismatch: folder={expected_id}, config={configured_id}"
        )

    identity_raw = raw.get("identity", {})
    if not isinstance(identity_raw, dict):
        raise ValidationError(f"Agent config identity must be a mapping: {agent_id}")
    name = str(raw.get("name", agent_id)).strip()
    role = str(raw.get("role", identity_raw.get("role", ""))).strip()
    can_delegate = raw.get("can_delegate", identity_raw.get("can_delegate", False))
    if require_identity and not name:
        raise ValidationError(f"Agent config name is required: {agent_id}")
    if require_identity and not role:
        raise ValidationError(f"Agent config role is required: {agent_id}")
    if not isinstance(can_delegate, bool):
        raise ValidationError(f"Agent config can_delegate must be boolean: {agent_id}")
    try:
        agent_kind = AgentKind(str(raw.get("agent_kind", AgentKind.PERSISTENT.value)))
    except ValueError as exc:
        raise ValidationError(f"Agent config kind is invalid: {agent_id}") from exc
    return {
        **raw,
        "id": agent_id,
        "name": name,
        "role": role,
        "can_delegate": can_delegate,
        "agent_kind": agent_kind,
    }


def load_agent_config(
    path: Path,
    expected_id: str,
    *,
    require_identity: bool = False,
) -> dict[str, Any]:
    try:
        raw = load_structured_file(path)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ValidationError(f"Invalid agent config: {expected_id}") from exc
    return normalize_agent_config(raw, expected_id, require_identity=require_identity)


def agent_config_from_mapping(
    raw: dict[str, Any],
    expected_id: str | None = None,
) -> AgentConfig:
    normalized = normalize_agent_config(raw, expected_id)
    return AgentConfig(
        id=normalized["id"],
        name=normalized["name"],
        role=normalized["role"],
        can_delegate=normalized["can_delegate"],
        preferred_model=normalized.get("preferred_model"),
        autonomy=str(normalized.get("autonomy", "manual")),
        skills=_legacy_skill_labels(normalized.get("skills", [])),
        permissions=[str(item) for item in normalized.get("permissions", [])],
        kind=normalized["agent_kind"],
    )


def _legacy_skill_labels(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("legacy", [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
