from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

TargetType = str

TARGET_TYPES: set[str] = {"tool_runtime", "mcp", "provider", "plugin", "workflow"}


@dataclass(frozen=True)
class ExecutionTarget:
    target_type: TargetType
    target_id: str
    available: bool
    priority: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlan:
    selected_target: ExecutionTarget
    fallback_targets: list[ExecutionTarget]
    routing_reason: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class ExecutionSummary:
    available_targets: int
    registered_targets: int
    routing_table: dict[str, list[str]] = field(default_factory=dict)
