from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import load_structured_file
from synapse.delegation.models import DelegationTask
from synapse.delegation_execution.models import DelegationExecution

DEFAULT_DELEGATION_RETRY_POLICY: dict[str, Any] = {
    "enabled": True,
    "max_attempts_default": 3,
    "max_attempts_by_priority": {"critical": 2, "high": 3, "normal": 3, "low": 2},
    "allow_retry_failed_tasks": True,
    "allow_retry_completed_tasks": False,
    "require_approval_for_critical_retry": True,
    "require_approval_after_attempts": 2,
    "reset_task_status_on_retry": True,
    "default_retry_status": "accepted",
}


@dataclass(frozen=True)
class DelegationRetryPolicy:
    enabled: bool = True
    max_attempts_default: int = 3
    max_attempts_by_priority: dict[str, int] = field(default_factory=dict)
    allow_retry_failed_tasks: bool = True
    allow_retry_completed_tasks: bool = False
    require_approval_for_critical_retry: bool = True
    require_approval_after_attempts: int | None = 2
    reset_task_status_on_retry: bool = True
    default_retry_status: str = "accepted"


@dataclass(frozen=True)
class DelegationRetryDecision:
    allowed: bool
    blocked: bool
    requires_approval: bool
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    attempt_count: int = 0
    max_attempts: int = 0
    risk_level: str = "low"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DelegationRetryPolicyRuntime:
    def __init__(self, data_dir: DataDir, events: EventBus):
        self.data_dir = data_dir
        self.events = events

    def load_policy(self) -> DelegationRetryPolicy:
        raw = load_structured_file(self.data_dir.resolve("config/delegation_retry_policy.yaml"))
        policy_raw = raw.get("delegation_retry", raw)
        merged = dict(DEFAULT_DELEGATION_RETRY_POLICY)
        merged.update(policy_raw)
        merged["max_attempts_by_priority"] = {
            **DEFAULT_DELEGATION_RETRY_POLICY["max_attempts_by_priority"],
            **dict(merged.get("max_attempts_by_priority", {})),
        }
        return DelegationRetryPolicy(**merged)

    def evaluate_retry(
        self,
        task: DelegationTask,
        executions: list[DelegationExecution],
    ) -> DelegationRetryDecision:
        policy = self.load_policy()
        attempt_count = len(executions)
        max_attempts = int(
            policy.max_attempts_by_priority.get(task.priority, policy.max_attempts_default)
        )
        reasons: list[str] = []
        blocked_reasons: list[str] = []
        requires_approval = False
        risk_level = "medium" if task.priority in {"high", "critical"} else "low"

        if not policy.enabled:
            blocked_reasons.append("delegation retry policy is disabled")
        if task.status == "failed" and not policy.allow_retry_failed_tasks:
            blocked_reasons.append("retry for failed tasks is disabled")
        if task.status == "completed" and not policy.allow_retry_completed_tasks:
            blocked_reasons.append("retry for completed tasks is disabled")
        if task.status not in {"failed", "completed"}:
            blocked_reasons.append(f"retry requires failed or completed task, got {task.status}")
        if attempt_count >= max_attempts:
            blocked_reasons.append(
                f"attempt count {attempt_count} reached max attempts {max_attempts}"
            )

        if not blocked_reasons:
            if task.priority == "critical" and policy.require_approval_for_critical_retry:
                requires_approval = True
                risk_level = "critical"
                reasons.append("critical retry requires approval")
            elif (
                policy.require_approval_after_attempts is not None
                and attempt_count >= policy.require_approval_after_attempts
            ):
                requires_approval = True
                reasons.append("retry requires approval after configured attempt threshold")
            else:
                reasons.append("retry allowed by policy")

        decision = DelegationRetryDecision(
            allowed=not blocked_reasons and not requires_approval,
            blocked=bool(blocked_reasons),
            requires_approval=requires_approval,
            reasons=reasons,
            blocked_reasons=blocked_reasons,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            risk_level=risk_level,
            metadata={
                "task_id": task.task_id,
                "priority": task.priority,
                "status": task.status,
                "default_retry_status": policy.default_retry_status,
                "reset_task_status_on_retry": policy.reset_task_status_on_retry,
            },
        )
        self._emit(task, decision)
        return decision

    def explain_retry(
        self,
        task_id: str,
        task: DelegationTask | None = None,
        executions: list[DelegationExecution] | None = None,
    ) -> DelegationRetryDecision:
        if task is None or executions is None:
            raise ValidationError("explain_retry requires task and executions in this stage")
        if task.task_id != task_id:
            raise ValidationError("task_id does not match task")
        return self.evaluate_retry(task, executions)

    def _emit(self, task: DelegationTask, decision: DelegationRetryDecision) -> None:
        payload = {"task_id": task.task_id, "decision": decision.to_dict()}
        self.events.emit("delegation.retry.evaluated", task.assignee_agent_id, payload)
        if decision.allowed:
            self.events.emit("delegation.retry.allowed", task.assignee_agent_id, payload)
        elif decision.requires_approval:
            self.events.emit("delegation.retry.requires_approval", task.assignee_agent_id, payload)
        elif decision.blocked:
            self.events.emit("delegation.retry.blocked", task.assignee_agent_id, payload)
