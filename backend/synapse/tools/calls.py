from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ToolCallRequest:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class ToolCallResult:
    request: ToolCallRequest
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class ToolCallPlan:
    calls: list[ToolCallRequest] = field(default_factory=list)

