"""Execute mission-owned identities through their parent's bounded authority."""
from __future__ import annotations

from datetime import UTC, datetime

from synapse.core.exceptions import ValidationError
from synapse.ephemeral_agents.models import EphemeralAgentState
from synapse.ephemeral_agents.runtime import EphemeralAgentRuntime
from synapse.missions.models import Mission, MissionTask, TaskAttempt, WorkerDescriptor
from synapse.workers.execution_adapter import WorkerExecutionAdapter, WorkerExecutionResult


class EphemeralExecutionAdapter:
    def __init__(self, delegate: WorkerExecutionAdapter, ephemeral: EphemeralAgentRuntime):
        self.delegate = delegate
        self.ephemeral = ephemeral

    def execute(self, attempt: TaskAttempt, task: MissionTask, mission: Mission,
                worker: WorkerDescriptor, context: dict[str, object]) -> WorkerExecutionResult:
        if not attempt.agent_id.startswith("ephemeral:"):
            return self.delegate.execute(attempt, task, mission, worker, context)
        instance = self.ephemeral.get(attempt.agent_id)
        continuing = (instance.state is EphemeralAgentState.RUNNING
                      and instance.current_attempt_id == attempt.attempt_id
                      and bool(context.get("verification_feedback")))
        if (instance.mission_id != mission.mission_id or instance.task_id != task.task_id
                or instance.worker_id != worker.worker_id or worker.agent_id != attempt.agent_id
                or (instance.state not in {EphemeralAgentState.ASSIGNED, EphemeralAgentState.WAITING} and not continuing)
                or datetime.fromisoformat(instance.expires_at) <= datetime.now(UTC)):
            raise ValidationError("Temporary agent assignment or lease is invalid.")
        if continuing:
            self.ephemeral.heartbeat(instance.ephemeral_agent_id, extend_seconds=0)
        else:
            self.ephemeral.start(instance.ephemeral_agent_id, attempt.attempt_id)
        return self.delegate.execute(
            attempt, task, mission, worker, context,
            execution_agent_id=instance.parent_agent_id,
            allowed_tool_names=frozenset(instance.tool_scope),
        )

    def finished(self, attempt: TaskAttempt) -> None:
        if not attempt.agent_id.startswith("ephemeral:"):
            return
        instance = self.ephemeral.get(attempt.agent_id)
        if instance.state is not EphemeralAgentState.RUNNING:
            return
        if attempt.status == "completed":
            result = attempt.result or {}
            self.ephemeral.complete(
                instance.ephemeral_agent_id, output_reference=f"attempt:{attempt.attempt_id}",
                attempt_ids=[attempt.attempt_id], verification=attempt.verification_result,
                evidence=result.get("evidence", []), artifacts=result.get("artifacts", []),
                provenance=[{"parent_agent_id": instance.parent_agent_id,
                             "worker_id": attempt.worker_id, "model": attempt.model_selection}],
            )
        elif attempt.status in {"failed", "cancelled", "timed_out"}:
            self.ephemeral.fail(instance.ephemeral_agent_id, attempt.error or {"status": attempt.status})
        elif attempt.status == "waiting_approval":
            self.ephemeral.wait(instance.ephemeral_agent_id)
