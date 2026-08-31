from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import load_structured_file
from synapse.delegation.models import DelegationTask

DEFAULT_DELEGATION_SCHEDULING_POLICY: dict[str, Any] = {
    "enabled": True,
    "status_order": ["in_progress", "accepted", "pending"],
    "priority_weights": {"critical": 400, "high": 300, "normal": 200, "low": 100},
    "due_at_weight": 50,
    "aging_weight": 1,
    "max_items_per_agent_cycle": 1,
    "allow_critical_first": True,
    "preserve_fifo_within_same_score": True,
}


@dataclass(frozen=True)
class DelegationSchedulingPolicy:
    enabled: bool = True
    status_order: list[str] = field(default_factory=lambda: ["in_progress", "accepted", "pending"])
    priority_weights: dict[str, int] = field(
        default_factory=lambda: {"critical": 400, "high": 300, "normal": 200, "low": 100}
    )
    due_at_weight: int = 50
    aging_weight: int = 1
    max_items_per_agent_cycle: int = 1
    allow_critical_first: bool = True
    preserve_fifo_within_same_score: bool = True


@dataclass(frozen=True)
class DelegationQueueItem:
    task_id: str
    status: str
    priority: str
    score: float
    created_at: str
    due_at: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DelegationSchedulingDecision:
    agent_id: str
    enabled: bool
    selected_task_id: str | None
    ordered_task_ids: list[str]
    queue: list[DelegationQueueItem]
    fallback_used: bool = False
    reason: str | None = None


class DelegationSchedulingPolicyRuntime:
    def __init__(self, data_dir: DataDir, events: EventBus):
        self.data_dir = data_dir
        self.events = events

    def load_policy(self) -> DelegationSchedulingPolicy:
        raw = load_structured_file(
            self.data_dir.resolve("config/delegation_scheduling_policy.yaml")
        )
        policy_raw = raw.get("delegation_scheduling", raw)
        merged = dict(DEFAULT_DELEGATION_SCHEDULING_POLICY)
        merged.update(policy_raw)
        merged["priority_weights"] = {
            **DEFAULT_DELEGATION_SCHEDULING_POLICY["priority_weights"],
            **dict(merged.get("priority_weights", {})),
        }
        return DelegationSchedulingPolicy(**merged)

    def score_task(
        self,
        task: DelegationTask,
        policy: DelegationSchedulingPolicy | None = None,
    ) -> DelegationQueueItem:
        policy = policy or self.load_policy()
        reasons: list[str] = []
        score = float(policy.priority_weights.get(task.priority, 0))
        reasons.append(f"priority:{task.priority}")

        if task.status in policy.status_order:
            status_score = (len(policy.status_order) - policy.status_order.index(task.status)) * 10
            score += status_score
            reasons.append(f"status:{task.status}")

        due_at = self._parse_datetime(task.due_at)
        now = datetime.now(UTC)
        if due_at and due_at <= now:
            score += policy.due_at_weight
            reasons.append("due_at:overdue")

        created_at = self._parse_datetime(task.created_at)
        if created_at:
            age_days = max((now - created_at).total_seconds(), 0) / 86400
            if age_days > 0:
                score += age_days * policy.aging_weight
                reasons.append("aging")

        return DelegationQueueItem(
            task_id=task.task_id,
            status=task.status,
            priority=task.priority,
            score=score,
            created_at=task.created_at,
            due_at=task.due_at,
            reasons=reasons,
        )

    def sort_tasks(self, tasks: list[DelegationTask]) -> list[DelegationTask]:
        policy = self.load_policy()
        if not policy.enabled:
            return tasks
        queue = {item.task_id: item for item in [self.score_task(task, policy) for task in tasks]}

        def sort_key(task: DelegationTask) -> tuple[int, float, str]:
            critical_rank = 0 if policy.allow_critical_first and task.priority == "critical" else 1
            created = task.created_at if policy.preserve_fifo_within_same_score else ""
            return (critical_rank, -queue[task.task_id].score, created)

        ordered = sorted(tasks, key=sort_key)
        self.events.emit(
            "delegation.scheduling.evaluated",
            "delegation_scheduling",
            {"task_ids": [task.task_id for task in ordered]},
        )
        return ordered

    def select_next_task(
        self,
        agent_id: str,
        tasks: list[DelegationTask],
    ) -> DelegationSchedulingDecision:
        policy = self.load_policy()
        if not policy.enabled:
            return DelegationSchedulingDecision(
                agent_id=agent_id,
                enabled=False,
                selected_task_id=tasks[0].task_id if tasks else None,
                ordered_task_ids=[task.task_id for task in tasks],
                queue=[],
                fallback_used=True,
                reason="policy_disabled",
            )
        ordered = self.sort_tasks(tasks)
        queue = [self.score_task(task, policy) for task in ordered]
        selected = ordered[0].task_id if ordered else None
        self.events.emit(
            "delegation.scheduling.selected",
            "delegation_scheduling",
            {"agent_id": agent_id, "task_id": selected},
        )
        return DelegationSchedulingDecision(
            agent_id=agent_id,
            enabled=True,
            selected_task_id=selected,
            ordered_task_ids=[task.task_id for task in ordered],
            queue=queue,
        )

    def explain_task_order(
        self,
        agent_id: str,
        tasks: list[DelegationTask],
    ) -> DelegationSchedulingDecision:
        return self.select_next_task(agent_id, tasks)

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
