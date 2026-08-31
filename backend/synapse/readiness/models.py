from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ReadinessState = str


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    state: ReadinessState
    summary: str
    health_check_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReadinessSummary:
    state: ReadinessState
    checks: list[ReadinessCheck] = field(default_factory=list)
    health_status: str = "ok"
    policy: dict[str, Any] = field(default_factory=dict)
