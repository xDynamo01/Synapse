from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Callable

from synapse.core.events import EventBus
from synapse.missions.attempts import TaskAttemptRuntime
from synapse.missions.errors import VerificationFailed, WorkerAssignmentMismatch
from synapse.missions.models import MissionTask, now_iso

AttemptExecutor = Callable[[Any, MissionTask, Any, Any, dict[str, Any]], Any]


class WorkerRuntime:
    def __init__(
        self,
        attempts: TaskAttemptRuntime,
        workers: Any,
        missions: Any,
        planner: Any,
        verifier: Any,
        events: EventBus,
        executor: AttemptExecutor | None = None,
        context_fusion: Any | None = None,
    ):
        self.attempts = attempts
        self.workers = workers
        self.missions = missions
        self.planner = planner
        self.verifier = verifier
        self.events = events
        self.executor = executor
        self.context_fusion = context_fusion

    def execute_attempt(self, attempt_id: str) -> Any:
        attempt = self.attempts.get(attempt_id)
        worker = self.workers.get(attempt.worker_id)
        mission = self.missions.get_mission(attempt.mission_id)
        plan = self.planner.get_plan(attempt.mission_id, mission.plan_id)
        task = next(item for item in plan.tasks if item.task_id == attempt.task_id)
        if (
            task.assigned_worker_id != worker.worker_id
            or task.assigned_agent_id != attempt.agent_id
        ):
            raise WorkerAssignmentMismatch(f"Attempt assignment does not match task {task.task_id}")
        if mission.status != "running":
            raise WorkerAssignmentMismatch(f"Mission is not executable: {mission.status}")
        if worker.status not in {"idle", "sleeping", "busy"}:
            raise WorkerAssignmentMismatch(f"Worker is unavailable: {worker.status}")
        attempt = (
            self.attempts.transition(attempt_id, "assigned")
            if attempt.status == "created"
            else attempt
        )
        attempt = (
            self.attempts.transition(attempt_id, "accepted")
            if attempt.status == "assigned"
            else attempt
        )
        attempt = (
            self.attempts.transition(attempt_id, "running")
            if attempt.status == "accepted"
            else attempt
        )
        self.workers.set_workload(worker.worker_id, 1.0, task.task_id, attempt.attempt_id)
        tasks = list(plan.tasks)
        self._save_task(
            plan,
            tasks,
            replace(
                task,
                status="running",
                started_at=task.started_at or now_iso(),
                attempts=max(task.attempts, attempt.attempt_number),
                revision=task.revision + 1,
                updated_at=now_iso(),
            ),
        )
        try:
            if not self.executor:
                return attempt
            context = self._context(attempt, task)
            raw_result = self.executor(attempt, task, mission, worker, context)
            result = (
                asdict(raw_result) if hasattr(raw_result, "__dataclass_fields__") else raw_result
            )
            if result.get("status") == "waiting_approval":
                return self.attempts.transition(
                    attempt_id,
                    "waiting_approval",
                    result=result,
                    model_selection=result.get("model_selection", {}),
                    tool_call_ids=result.get("tool_call_ids", []),
                )
            if result.get("status") == "failed":
                raise RuntimeError(str(result.get("error") or "Worker execution failed."))
            verification = self.verifier.verify(result, task.verification_policy)
            if verification.status != "passed":
                raise VerificationFailed("Task result verification failed.")
            attempt = self.attempts.transition(
                attempt_id,
                "completed",
                result=result,
                verification_result=asdict(verification),
                model_selection=result.get("model_selection", {}),
                tool_call_ids=result.get("tool_call_ids", []),
                context_trace_id=result.get("context_trace_id"),
            )
            current_plan = self.planner.get_plan(attempt.mission_id, plan.plan_id)
            current_task = next(item for item in current_plan.tasks if item.task_id == task.task_id)
            self._save_task(
                current_plan,
                list(current_plan.tasks),
                replace(
                    current_task,
                    status="completed",
                    result=result,
                    completed_at=now_iso(),
                    revision=current_task.revision + 1,
                    updated_at=now_iso(),
                ),
            )
            return attempt
        except Exception as exc:
            current = self.attempts.get(attempt_id)
            if current.status == "running":
                self.attempts.transition(
                    attempt_id, "failed", error={"type": type(exc).__name__, "message": str(exc)}
                )
            current_plan = self.planner.get_plan(attempt.mission_id, plan.plan_id)
            current_task = next(item for item in current_plan.tasks if item.task_id == task.task_id)
            self._save_task(
                current_plan,
                list(current_plan.tasks),
                replace(
                    current_task,
                    status="failed",
                    error={"type": type(exc).__name__, "message": str(exc)},
                    revision=current_task.revision + 1,
                    updated_at=now_iso(),
                ),
            )
            self.events.emit(
                "worker.failed",
                attempt.agent_id,
                {
                    "worker_id": worker.worker_id,
                    "attempt_id": attempt_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        finally:
            self.workers.set_workload(worker.worker_id, 0.0, None, None)

    def _context(self, attempt: Any, task: MissionTask) -> dict[str, Any]:
        if not self.context_fusion:
            return {"mission_id": attempt.mission_id, "task_id": task.task_id}
        built = self.context_fusion.build_mission_context(attempt.mission_id)
        return {
            "mission": asdict(built) if hasattr(built, "__dataclass_fields__") else built,
            "task_id": task.task_id,
        }

    def _save_task(self, plan: Any, tasks: list[MissionTask], updated: MissionTask) -> None:
        index = next(i for i, item in enumerate(tasks) if item.task_id == updated.task_id)
        tasks[index] = updated
        self.planner.save_plan(
            replace(
                plan, tasks=tasks, dependencies={item.task_id: item.dependencies for item in tasks}
            )
        )
