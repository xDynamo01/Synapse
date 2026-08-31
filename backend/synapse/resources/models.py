from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from synapse.core.exceptions import ValidationError

RESOURCE_TYPES = {
    "file",
    "memory",
    "project",
    "job",
    "approval",
    "notification",
    "agent_message",
    "chat_session",
}

RESOURCE_ACTIONS = {
    "read",
    "list",
    "create",
    "update",
    "delete",
    "execute",
    "approve",
    "reject",
}


@dataclass(frozen=True)
class ResourceRef:
    resource_type: str
    resource_id: str | None = None
    path: str | None = None
    owner_agent_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.resource_type not in RESOURCE_TYPES:
            raise ValidationError(f"Invalid resource type: {self.resource_type}")
        if not self.resource_id and not self.path:
            raise ValidationError("ResourceRef requires resource_id or path")


@dataclass(frozen=True)
class ResourceAction:
    name: str

    def __post_init__(self) -> None:
        if self.name not in RESOURCE_ACTIONS:
            raise ValidationError(f"Invalid resource action: {self.name}")

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class ResourceScope:
    agent_id: str
    action: str
    resource_ref: ResourceRef
    correlation_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        ResourceAction(self.action)
