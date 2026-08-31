from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from synapse.core.events import EventBus

if TYPE_CHECKING:
    from synapse.conversations.runtime import ConversationRuntime
    from synapse.dead_letter.runtime import DeadLetterRuntime
    from synapse.delegation.models import DelegationTask
    from synapse.delegation.runtime import DelegationRuntime
    from synapse.delegation.timeout_policy import DelegationTimeoutPolicyRuntime
    from synapse.delegation_execution.runtime import DelegationExecutionRuntime
    from synapse.delegation_recovery.models import RecoveryDecision
    from synapse.delegation_recovery.runtime import DelegationRecoveryRuntime
    from synapse.missions.models import Mission, MissionSummary
    from synapse.missions.runtime import MissionRuntime


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class MissionContextSummary:
    status: str
    health: str
    progress_percent: float
    key_findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MissionContext:
    mission: dict[str, Any]
    summary: MissionContextSummary
    delegation_count: int
    execution_count: int
    failed_execution_count: int
    timeout_candidates: list[dict[str, Any]]
    dlq_count: int
    recovery_candidates: list[dict[str, Any]]
    linked_conversations: list[dict[str, Any]]
    active_tasks: list[dict[str, Any]]
    completed_tasks: list[dict[str, Any]]
    failed_tasks: list[dict[str, Any]]
    pending_tasks: list[dict[str, Any]]
    generated_at: str = field(default_factory=now_iso)


class MissionContextRuntime:
    def __init__(
        self,
        events: EventBus,
        missions: MissionRuntime,
        delegation: DelegationRuntime,
        executions: DelegationExecutionRuntime,
        dead_letter: DeadLetterRuntime,
        recovery: DelegationRecoveryRuntime,
        conversations: ConversationRuntime | None = None,
        timeout_policy: DelegationTimeoutPolicyRuntime | None = None,
    ):
        self.events = events
        self.missions = missions
        self.delegation = delegation
        self.executions = executions
        self.dead_letter = dead_letter
        self.recovery = recovery
        self.conversations = conversations
        self.timeout_policy = timeout_policy

    def build_context(self, mission_id: str, emit_event: bool = True) -> MissionContext:
        try:
            mission = self.missions.get_mission(mission_id)
            mission_summary = self.missions.summarize_mission(mission_id)
            tasks = self._mission_tasks(mission_id)
            executions = [
                execution
                for task in tasks
                for execution in self.executions.list_task_executions(task.task_id)
            ]
            failed_executions = [
                execution for execution in executions if execution.status == "failed"
            ]
            timeout_candidates = self._timeout_candidates(tasks)
            recovery_candidates = self.list_mission_recovery_candidates(
                mission_id, emit_event=False
            )
            linked_conversations = self.list_mission_conversations(mission_id)
            active_tasks = [task for task in tasks if task.status in {"accepted", "in_progress"}]
            completed_tasks = [task for task in tasks if task.status == "completed"]
            failed_tasks = [task for task in tasks if task.status == "failed"]
            pending_tasks = [task for task in tasks if task.status == "pending"]
            summary = self._context_summary(
                mission,
                mission_summary,
                timeout_candidates,
                recovery_candidates,
            )
            context = MissionContext(
                mission=asdict(mission),
                summary=summary,
                delegation_count=len(tasks),
                execution_count=len(executions),
                failed_execution_count=len(failed_executions),
                timeout_candidates=[asdict(candidate) for candidate in timeout_candidates],
                dlq_count=mission_summary.dlq_tasks,
                recovery_candidates=[asdict(decision) for decision in recovery_candidates],
                linked_conversations=linked_conversations,
                active_tasks=[asdict(task) for task in active_tasks],
                completed_tasks=[asdict(task) for task in completed_tasks],
                failed_tasks=[asdict(task) for task in failed_tasks],
                pending_tasks=[asdict(task) for task in pending_tasks],
            )
            if emit_event:
                self.events.emit(
                    "mission.context.generated",
                    mission.owner_agent_id or "mission",
                    asdict(context),
                )
            return context
        except Exception as exc:
            self.events.emit(
                "mission.context.failed",
                "mission",
                {"mission_id": mission_id, "error": str(exc) or type(exc).__name__},
            )
            raise

    def summarize_context(self, mission_id: str) -> MissionContextSummary:
        return self.build_context(mission_id).summary

    def list_mission_conversations(self, mission_id: str) -> list[dict[str, Any]]:
        mission = self.missions.get_mission(mission_id)
        conversation_ids = set()
        if mission.conversation_id:
            conversation_ids.add(mission.conversation_id)
        for task in self._mission_tasks(mission_id):
            if task.conversation_id:
                conversation_ids.add(task.conversation_id)
        conversations: list[dict[str, Any]] = []
        if not self.conversations:
            return conversations
        for conversation_id in sorted(conversation_ids):
            conversation = self.conversations.get_conversation(conversation_id)
            summary = self.conversations.get_conversation_summary(conversation_id)
            conversations.append(
                {
                    "conversation": asdict(conversation),
                    "summary": asdict(summary),
                }
            )
        return conversations

    def list_mission_recovery_candidates(
        self,
        mission_id: str,
        emit_event: bool = True,
    ) -> list[RecoveryDecision]:
        candidates = []
        for task in self._mission_tasks(mission_id):
            decision = self.recovery.evaluate_task(task.task_id, emit_event=emit_event)
            if decision.recommendation != "continue_processing":
                candidates.append(decision)
        return candidates

    def mission_health(self, mission_id: str) -> str:
        return self.build_context(mission_id, emit_event=False).summary.health

    def critical_missions_count(self) -> int:
        count = 0
        for mission in self.missions.list_missions():
            if mission.status == "archived":
                continue
            if self.mission_health(mission.mission_id) == "critical":
                count += 1
        return count

    def _mission_tasks(self, mission_id: str) -> list[DelegationTask]:
        tasks = []
        for link in self.missions.list_mission_tasks(mission_id):
            tasks.append(self.delegation.get_task(link.task_id))
        return tasks

    def _timeout_candidates(self, tasks: list[DelegationTask]) -> list[Any]:
        if not self.timeout_policy:
            return []
        candidates = []
        for task in tasks:
            candidate = self.timeout_policy.evaluate_timeout(
                task,
                self.executions.latest_execution(task.task_id),
            )
            if candidate:
                candidates.append(candidate)
        return candidates

    def _context_summary(
        self,
        mission: Mission,
        mission_summary: MissionSummary,
        timeout_candidates: list[Any],
        recovery_candidates: list[RecoveryDecision],
    ) -> MissionContextSummary:
        progress = 0.0
        if mission_summary.total_tasks:
            progress = round(
                (mission_summary.completed_tasks / mission_summary.total_tasks) * 100, 2
            )
        warnings: list[str] = []
        recommendations: list[str] = []
        key_findings = [
            f"{mission_summary.total_tasks} linked delegation(s)",
            f"{mission_summary.completed_tasks} completed delegation(s)",
        ]
        health = "healthy"
        if mission_summary.failed_tasks or timeout_candidates or recovery_candidates:
            health = "warning"
            if mission_summary.failed_tasks:
                warnings.append(f"{mission_summary.failed_tasks} failed delegation(s)")
            if timeout_candidates:
                warnings.append(f"{len(timeout_candidates)} timeout candidate(s)")
            if recovery_candidates:
                warnings.append(f"{len(recovery_candidates)} recovery candidate(s)")
                recommendations.append("Review mission recovery candidates.")
        if mission_summary.dlq_tasks and recovery_candidates:
            health = "critical"
            warnings.append(f"{mission_summary.dlq_tasks} delegation(s) in DLQ")
            recommendations.append("Review DLQ entries before continuing mission work.")
        if not mission_summary.total_tasks:
            recommendations.append("Link delegations to make the mission operationally useful.")
        return MissionContextSummary(
            status=mission.status,
            health=health,
            progress_percent=progress,
            key_findings=key_findings,
            warnings=warnings,
            recommendations=recommendations,
        )
