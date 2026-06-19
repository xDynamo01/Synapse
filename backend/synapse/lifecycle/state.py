from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

LIFECYCLE_STATES = {
    "offline",
    "booting",
    "idle",
    "waking",
    "working",
    "waiting",
    "sleeping",
    "error",
    "shutdown",
}


@dataclass(frozen=True)
class AgentLifecycle:
    agent_id: str
    state: str = "offline"
    reason: str | None = None
    last_transition_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    boot_count: int = 0
    wake_count: int = 0
    sleep_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "state": self.state,
            "reason": self.reason,
            "last_transition_at": self.last_transition_at,
            "boot_count": self.boot_count,
            "wake_count": self.wake_count,
            "sleep_count": self.sleep_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "correlation_id": self.correlation_id,
        }
