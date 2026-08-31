from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from synapse.core.exceptions import ValidationError

CAPABILITY_CATEGORIES = {
    "memory",
    "filesystem",
    "communication",
    "scheduling",
    "agent_coordination",
    "notification",
    "approval",
    "audio",
    "vision",
    "system",
    "research_mock",
}

CAPABILITY_RISK_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class Capability:
    capability_id: str
    name: str
    description: str
    category: str
    risk_level: str
    required_permissions: list[str] = field(default_factory=list)
    allowed_resource_types: list[str] = field(default_factory=list)
    required_approval_level: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.capability_id:
            raise ValidationError("Capability id is required.")
        if self.category not in CAPABILITY_CATEGORIES:
            raise ValidationError(f"Invalid capability category: {self.category}")
        if self.risk_level not in CAPABILITY_RISK_LEVELS:
            raise ValidationError(f"Invalid capability risk level: {self.risk_level}")


@dataclass(frozen=True)
class CapabilityDecision:
    agent_id: str
    capability_id: str
    allowed: bool
    reason: str
    resource_scope: dict[str, Any] | None = None
