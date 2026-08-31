from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


LOOP_STATES = {
    "stopped",
    "starting",
    "idle",
    "observing",
    "evaluating",
    "deciding",
    "awaiting_approval",
    "executing",
    "verifying",
    "committing",
    "paused",
    "degraded",
    "stopping",
    "failed",
}
VALID_TRANSITIONS = {
    "stopped": {"starting"},
    "starting": {"idle", "degraded", "failed", "stopping"},
    "idle": {"observing", "paused", "stopping", "degraded", "failed"},
    "observing": {"evaluating", "idle", "degraded", "failed", "stopping"},
    "evaluating": {"deciding", "idle", "degraded", "failed", "stopping"},
    "deciding": {"awaiting_approval", "executing", "committing", "idle", "degraded", "failed"},
    "awaiting_approval": {"idle", "paused", "stopping", "failed"},
    "executing": {"verifying", "degraded", "failed"},
    "verifying": {"committing", "degraded", "failed"},
    "committing": {"idle", "degraded", "failed"},
    "paused": {"idle", "stopping"},
    "degraded": {"idle", "observing", "paused", "stopping", "failed"},
    "stopping": {"stopped", "failed"},
    "failed": {"starting", "stopping", "stopped"},
}


@dataclass(frozen=True)
class AgentLoopState:
    loop_id: str = "primary"
    state: str = "stopped"
    previous_state: str | None = None
    current_attention_id: str | None = None
    current_decision_id: str | None = None
    current_execution_ref: str | None = None
    last_cycle_at: str | None = None
    next_cycle_at: str | None = None
    error: dict[str, Any] | None = None
    revision: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionResult:
    status: str
    output_reference: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    side_effects: list[str]
    errors: list[dict[str, Any]]
    verification: dict[str, Any]
    started_at: str
    completed_at: str
    trace_id: str


@dataclass(frozen=True)
class CommitResult:
    written: bool
    memory_ids: list[str] = field(default_factory=list)
    skipped: bool = False
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "completed"
    trigger: str | None = None
    attention_item_id: str | None = None
    decision_id: str | None = None
    disposition: str | None = None
    action_result: ActionResult | None = None
    commit_result: CommitResult | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=now_iso)
    completed_at: str = field(default_factory=now_iso)
    world_state_revision: int = 0
    next_cycle_at: str | None = None
