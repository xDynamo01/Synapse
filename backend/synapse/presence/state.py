from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

PRESENCE_STATES = {
    "idle",
    "listening",
    "thinking",
    "speaking",
    "researching",
    "working",
    "waiting_approval",
    "offline",
    "error",
}


@dataclass(frozen=True)
class AgentPresence:
    agent_id: str
    state: str
    activity: str | None = None
    current_task_id: str | None = None
    current_job_id: str | None = None
    current_session_id: str | None = None
    current_approval_id: str | None = None
    emotion: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "state": self.state,
            "activity": self.activity,
            "current_task_id": self.current_task_id,
            "current_job_id": self.current_job_id,
            "current_session_id": self.current_session_id,
            "current_approval_id": self.current_approval_id,
            "emotion": self.emotion,
            "updated_at": self.updated_at,
            "correlation_id": self.correlation_id,
        }
