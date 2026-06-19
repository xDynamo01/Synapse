from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AgentConfig:
    id: str
    name: str
    role: str
    preferred_model: str | None = None
    autonomy: str = "manual"
    skills: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


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


def agent_config_from_mapping(raw: dict[str, Any]) -> AgentConfig:
    return AgentConfig(
        id=str(raw["id"]),
        name=str(raw.get("name", raw["id"])),
        role=str(raw.get("role", "")),
        preferred_model=raw.get("preferred_model"),
        autonomy=str(raw.get("autonomy", "manual")),
        skills=[str(item) for item in raw.get("skills", [])],
        permissions=[str(item) for item in raw.get("permissions", [])],
    )
