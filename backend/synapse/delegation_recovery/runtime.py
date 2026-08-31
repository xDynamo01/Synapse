from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from synapse.core.events import EventBus
from synapse.delegation_recovery.models import RecoveryDecision

if TYPE_CHECKING:
    from synapse.dead_letter.models import DeadLetterEntry
    from synapse.dead_letter.runtime import DeadLetterRuntime
    from synapse.delegation.models import DelegationTask
    from synapse.delegation.retry_policy import (
        DelegationRetryDecision,
        DelegationRetryPolicyRuntime,
    )
    from synapse.delegation.runtime import DelegationRuntime
    from synapse.delegation.timeout_policy import (
        DelegationTimeoutCandidate,
        DelegationTimeoutPolicyRuntime,
    )
    from synapse.delegation_execution.models import DelegationExecution
    from synapse.delegation_execution.runtime import DelegationExecutionRuntime


class DelegationRecoveryRuntime:
    def __init__(
        self,
        events: EventBus,
        delegation: DelegationRuntime,
        executions: DelegationExecutionRuntime,
        retry_policy: DelegationRetryPolicyRuntime,
        timeout_policy: DelegationTimeoutPolicyRuntime,
        dead_letter: DeadLetterRuntime,
    ):
        self.events = events
        self.delegation = delegation
        self.executions = executions
        self.retry_policy = retry_policy
        self.timeout_policy = timeout_policy
        self.dead_letter = dead_letter

    def evaluate_task(self, task_id: str, emit_event: bool = True) -> RecoveryDecision:
        try:
            task = self.delegation.get_task(task_id)
            executions = self.executions.list_task_executions(task_id)
            latest_execution = executions[-1] if executions else None
            timeout = self.timeout_policy.evaluate_timeout(task, latest_execution)
            dlq = self._latest_dead_letter(task_id)
            retry = self._retry_decision(task, executions)
            decision = self._decision(task, executions, retry, timeout, dlq)
            if emit_event:
                self.events.emit(
                    "recovery.decision.generated",
                    task.assignee_agent_id,
                    asdict(decision),
                )
            return decision
        except Exception as exc:
            self.events.emit(
                "recovery.decision.failed",
                "delegation_recovery",
                {"task_id": task_id, "error": str(exc) or type(exc).__name__},
            )
            raise

    def evaluate_all_open_tasks(self, emit_event: bool = True) -> list[RecoveryDecision]:
        decisions: list[RecoveryDecision] = []
        for task in self.delegation.list_tasks():
            if task.status in {
                "completed",
                "rejected",
                "cancelled",
            } and not self.dead_letter.is_task_open(task.task_id):
                continue
            decisions.append(self.evaluate_task(task.task_id, emit_event=emit_event))
        return decisions

    def explain_decision(self, task_id: str) -> RecoveryDecision:
        return self.evaluate_task(task_id)

    def summarize_recovery_state(self, emit_event: bool = True) -> dict[str, Any]:
        decisions = self.evaluate_all_open_tasks(emit_event=emit_event)
        by_recommendation: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        for decision in decisions:
            by_recommendation[decision.recommendation] = (
                by_recommendation.get(decision.recommendation, 0) + 1
            )
            by_risk[decision.risk_level] = by_risk.get(decision.risk_level, 0) + 1
        candidates = [
            decision for decision in decisions if decision.recommendation != "continue_processing"
        ]
        return {
            "total_open_tasks": len(decisions),
            "recovery_candidates_count": len(candidates),
            "manual_review_count": by_recommendation.get("manual_review", 0),
            "by_recommendation": by_recommendation,
            "by_risk": by_risk,
            "decisions": [asdict(decision) for decision in decisions],
        }

    def recovery_candidates_count(self) -> int:
        return int(self.summarize_recovery_state(emit_event=False)["recovery_candidates_count"])

    def manual_review_count(self) -> int:
        return int(self.summarize_recovery_state(emit_event=False)["manual_review_count"])

    def _decision(
        self,
        task: DelegationTask,
        executions: list[DelegationExecution],
        retry: DelegationRetryDecision | None,
        timeout: DelegationTimeoutCandidate | None,
        dlq: DeadLetterEntry | None,
    ) -> RecoveryDecision:
        failed_execution_count = len(
            [execution for execution in executions if execution.status == "failed"]
        )
        reasons: list[str] = []
        actions: list[str] = []
        recommendation = "continue_processing"
        risk_level = "low"
        retry_allowed = bool(retry and retry.allowed)

        if dlq and dlq.status == "reviewed":
            recommendation = "restore_from_dead_letter"
            risk_level = "medium"
            reasons.append("delegation has a reviewed dead letter entry")
            actions.append(f"restore dead letter entry {dlq.dlq_id} when appropriate")
        elif dlq and dlq.status != "restored":
            recommendation = "manual_review"
            risk_level = "high" if task.priority in {"high", "critical"} else "medium"
            reasons.append(f"delegation is in dead letter status {dlq.status}")
            actions.append(f"review dead letter entry {dlq.dlq_id}")
        elif timeout and timeout.requires_human_review:
            recommendation = "manual_review"
            risk_level = "critical"
            reasons.append("critical timeout requires human review")
            actions.append("review timeout candidate before applying any recovery")
        elif timeout:
            recommendation = "manual_review"
            risk_level = "high" if task.priority in {"high", "critical"} else "medium"
            reasons.append(f"timeout detected: {timeout.reason}")
            actions.append(
                "review timeout candidate and decide whether to fail, retry, or move to DLQ"
            )
        elif task.status == "failed" and retry and retry.allowed:
            recommendation = "retry_task"
            risk_level = retry.risk_level
            reasons.extend(retry.reasons or ["retry allowed by policy"])
            actions.append("request explicit delegation retry")
        elif task.status == "failed" and retry and retry.requires_approval:
            recommendation = "manual_review"
            risk_level = retry.risk_level
            reasons.extend(retry.reasons or ["retry requires approval"])
            actions.append("review retry decision before reopening task")
        elif task.status == "failed":
            recommendation = "move_to_dead_letter"
            risk_level = "high" if task.priority in {"high", "critical"} else "medium"
            if retry and retry.blocked_reasons:
                reasons.extend(retry.blocked_reasons)
            else:
                reasons.append("failed task cannot continue without intervention")
            actions.append("move delegation to dead letter queue for manual review")
        else:
            reasons.append(f"task status {task.status} can continue normal processing")
            actions.append("continue normal delegation processing")

        return RecoveryDecision(
            task_id=task.task_id,
            recommendation=recommendation,
            risk_level=risk_level,
            reasons=reasons,
            recommended_actions=actions,
            execution_count=len(executions),
            failed_execution_count=failed_execution_count,
            timeout_detected=timeout is not None,
            dlq_present=bool(dlq and dlq.status != "restored"),
            retry_allowed=retry_allowed,
            metadata={
                "task_status": task.status,
                "priority": task.priority,
                "assignee_agent_id": task.assignee_agent_id,
                "requester_agent_id": task.requester_agent_id,
                "latest_execution_id": executions[-1].execution_id if executions else None,
                "timeout": asdict(timeout) if timeout else None,
                "dead_letter": asdict(dlq) if dlq else None,
                "retry": retry.to_dict() if retry else None,
            },
        )

    def _latest_dead_letter(self, task_id: str) -> DeadLetterEntry | None:
        entries = [
            entry
            for entry in self.dead_letter.list_entries()
            if entry.task_id == task_id and entry.status != "restored"
        ]
        return entries[-1] if entries else None

    def _retry_decision(
        self,
        task: DelegationTask,
        executions: list[DelegationExecution],
    ) -> DelegationRetryDecision | None:
        if task.status not in {"failed", "completed"}:
            return None
        return self.retry_policy.evaluate_retry(task, executions)
