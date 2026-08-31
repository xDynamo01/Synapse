from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.core.permissions import PermissionContext
from synapse.missions.models import Mission, MissionTask, TaskAttempt, WorkerDescriptor


@dataclass(frozen=True)
class WorkerExecutionResult:
    output: str
    structured_output: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    tool_call_ids: list[str] = field(default_factory=list)
    model_selection: dict[str, Any] = field(default_factory=dict)
    context_trace_id: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"
    approval_ids: list[str] = field(default_factory=list)


class WorkerExecutionAdapter:
    def __init__(self, context_loader: Any, agent_runtime: Any, context_fusion: Any | None = None):
        self.context_loader = context_loader
        self.agent_runtime = agent_runtime
        self.context_fusion = context_fusion

    def execute(
        self,
        attempt: TaskAttempt,
        task: MissionTask,
        mission: Mission,
        worker: WorkerDescriptor,
        context: dict[str, Any],
    ) -> WorkerExecutionResult:
        permission_context = PermissionContext(
            actor_id=worker.agent_id, actor_type="agent", autonomy="delegated"
        )
        mission_context = context.get("mission")
        loaded = self.context_loader.load(
            permission_context,
            worker.agent_id,
            conversation_context={"mission_id": mission.mission_id, "mission": mission_context},
            delegation_context={
                "task_id": task.task_id,
                "attempt_id": attempt.attempt_id,
                "objective": task.objective,
                "expected_output": task.expected_output,
            },
        )
        run = self.agent_runtime.run(
            permission_context,
            worker.agent_id,
            loaded,
            self._instruction(mission, task),
            model_provider_override=task.metadata.get("provider"),
            model_override=task.metadata.get("model"),
        )
        tool_call_ids = [result.request.id for result in run.tool_results]
        waiting = [result for result in run.tool_results if result.status == "awaiting_approval"]
        failed = [
            result
            for result in run.tool_results
            if result.status in {"failed", "blocked", "timed_out"}
        ]
        status = (
            "waiting_approval"
            if waiting
            else ("failed" if failed and not run.response.strip() else "completed")
        )
        error = None
        if status == "failed":
            error = {
                "type": "tool_execution_failed",
                "messages": [item.error for item in failed if item.error],
            }
        return WorkerExecutionResult(
            output=run.response,
            structured_output=run.tool_calling_result,
            tool_call_ids=tool_call_ids,
            model_selection=run.model,
            context_trace_id=attempt.correlation_id,
            warnings=[item.error for item in failed if item.error],
            error=error,
            evidence=[{"kind": "tool_result", "value": asdict(item)} for item in run.tool_results],
            status=status,
            approval_ids=[item.approval_id for item in waiting if item.approval_id],
            metrics={"tool_calls": len(run.tool_results)},
        )

    @staticmethod
    def _instruction(mission: Mission, task: MissionTask) -> str:
        expected = f" Expected output: {task.expected_output}." if task.expected_output else ""
        return f"Mission objective: {mission.objective}\nTask: {task.objective}.{expected}"
