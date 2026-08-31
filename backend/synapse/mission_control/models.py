from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class MissionControlMissionCard:
    mission_id: str
    title: str
    status: str
    priority: str
    health: str
    progress_percent: float
    total_tasks: int
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    dlq_tasks: int
    attention_required: bool
    top_recommendations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MissionControlOverview:
    total_missions: int
    active_missions: int
    warning_missions: int
    critical_missions: int
    attention_required_count: int
    mission_cards: list[dict[str, Any]]
    global_attention_items: list[dict[str, Any]]
    generated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class MissionControlAttentionPanel:
    total_items: int
    critical_items: int
    warning_items: int
    items: list[dict[str, Any]]
    generated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class MissionControlWorkQueue:
    total_items: int
    items: list[dict[str, Any]]
    agent_id: str | None = None
    generated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class MissionControlAgentWorkload:
    total_agents: int
    agents: list[dict[str, Any]]
    generated_at: str = field(default_factory=now_iso)
