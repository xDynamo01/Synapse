from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any, Callable

from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.missions.attempts import TaskAttemptRuntime
from synapse.missions.errors import VerificationFailed, WorkerAssignmentMismatch
from synapse.missions.models import MissionTask, TaskAttempt, now_iso

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
        self.route_admission: Callable[[str, MissionTask, str], tuple[str, str] | None] | None = None
        self.attempt_finished: Callable[[TaskAttempt], None] | None = None

    def resume_approved_tool(self, receipt: dict[str, Any]) -> list[str]:
        resumed: list[str] = []
        for attempt in self.attempts.list():
            if attempt.status != "waiting_approval" or receipt["request"]["id"] not in attempt.tool_call_ids:
                continue
            result = dict(attempt.result or {})
            evidence = result.get("evidence", [])
            matching = [item for item in evidence if item.get("kind") == "tool_result"
                        and item.get("value", {}).get("request", {}).get("id") == receipt["request"]["id"]
                        and item.get("value", {}).get("approval_id") == receipt.get("approval_id")]
            if len(matching) != 1:
                raise ValidationError("Approved tool receipt does not match the waiting attempt.")
            matching[0]["value"] = receipt
            self.attempts.transition(attempt.attempt_id, "running", result=result)
            pending = any(item.get("value", {}).get("status") == "awaiting_approval" for item in evidence)
            if pending:
                self.attempts.transition(attempt.attempt_id, "waiting_approval", result=result)
                continue
            self.execute_attempt(attempt.attempt_id, continuation=True)
            resumed.append(attempt.mission_id)
        return resumed

    def execute_attempt(self, attempt_id: str, *, continuation: bool = False) -> Any:
        attempt = self.attempts.get(attempt_id)
        if attempt.status == "completed":
            return attempt
        if attempt.status not in {"created", "assigned", "accepted"} and not (continuation and attempt.status == "running"):
            raise ValidationError("Attempt requires explicit recovery before execution.")
        not_before = attempt.metadata.get("not_before")
        if not_before and datetime.fromisoformat(not_before) > datetime.now(UTC):
            raise ValidationError("Retry backoff has not elapsed.")
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
        self.missions.validate_execution(mission)
        if self.route_admission is not None:
            route = self.route_admission(mission.mission_id, task, attempt.agent_id)
            if route is not None:
                task = replace(task, metadata={**task.metadata, "provider": route[0], "model": route[1]})
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
        result = None
        verification = None
        try:
            if not self.executor:
                return attempt
            context = self._context(attempt, task)
            if continuation:
                context["previous_tool_results"] = [
                    item["value"] for item in (attempt.result or {}).get("evidence", [])
                    if item.get("kind") == "tool_result"
                ]
            for verification_round in range(3):
                raw_result = self.executor(attempt, task, mission, worker, context)
                result = (
                    asdict(raw_result) if hasattr(raw_result, "__dataclass_fields__") else raw_result
                )
                if result.get("status") == "waiting_approval":
                    current_plan = self.planner.get_plan(attempt.mission_id, plan.plan_id)
                    current_task = next(item for item in current_plan.tasks if item.task_id == task.task_id)
                    self._save_task(current_plan, list(current_plan.tasks), replace(
                        current_task, status="waiting_approval", result=result,
                        revision=current_task.revision + 1, updated_at=now_iso()))
                    return self.attempts.transition(
                        attempt_id,
                        "waiting_approval",
                        result=result,
                        model_selection=result.get("model_selection", {}),
                        tool_call_ids=result.get("tool_call_ids", []),
                    )
                if result.get("status") == "failed":
                    raise RuntimeError(str(result.get("error") or "Worker execution failed."))
                self.events.emit("task.validating", attempt.agent_id,
                                 {"task_id": task.task_id, "attempt_id": attempt_id})
                verification = self.verifier.verify(result, task.verification_policy)
                if verification.status == "passed":
                    break
                receipts = [item["value"] for item in result.get("evidence", []) if item.get("kind") == "tool_result"]
                if (verification_round >= 2 or "file_operations" not in task.verification_policy.get("checks", [])
                        or not receipts or any(not receipt.get("success") for receipt in receipts)):
                    raise VerificationFailed("Task result verification failed.")
                context["previous_tool_results"] = receipts
                observed = {receipt["request"]["name"] for receipt in receipts}
                missing = [group for group in task.verification_policy.get("tool_groups", [])
                           if not observed.intersection(group)]
                context["verification_feedback"] = (
                    "The verifier rejected your premature completion. Continue this same task using tools. "
                    f"Missing required tool groups: {missing}. "
                    f"Only operations inside {task.verification_policy.get('root')} count. "
                    "Listing a directory is not reading a source file. Use read_file on the discovered source files. "
                    "Do not repeat successful writes. After a change, read the changed file to verify it."
                )
                self.events.emit("task.verification_continuation", attempt.agent_id,
                                 {"task_id": task.task_id, "attempt_id": attempt_id,
                                  "round": verification_round + 1, "errors": verification.errors})
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
                    attempt_id, "failed", error={"type": type(exc).__name__, "message": str(exc)},
                    result=result, verification_result=asdict(verification) if verification is not None else None
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
            if self.attempt_finished is not None:
                self.attempt_finished(self.attempts.get(attempt_id))

    def _context(self, attempt: Any, task: MissionTask) -> dict[str, Any]:
        handoff = {"objective": task.objective,
                   "acceptance_criteria": task.verification_policy,
                   "authorized_tools": task.required_tools,
                   "dependency_outputs": attempt.input_snapshot.get("dependency_outputs", []),
                   "failure": task.error}
        if not self.context_fusion:
            return {"mission_id": attempt.mission_id, "task_id": task.task_id, "handoff": handoff}
        built = self.context_fusion.build_mission_context(attempt.mission_id)
        return {
            "mission": asdict(built) if hasattr(built, "__dataclass_fields__") else built,
            "task_id": task.task_id,
            "handoff": handoff,
        }

    def _save_task(self, plan: Any, tasks: list[MissionTask], updated: MissionTask) -> None:
        with self.planner.lock:
            current = self.planner.get_plan(plan.mission_id, plan.plan_id)
            tasks = list(current.tasks)
            index = next(i for i, item in enumerate(tasks) if item.task_id == updated.task_id)
            if tasks[index].status == "cancelled":
                return
            tasks[index] = updated
            self.planner.save_plan(
                replace(
                    current, tasks=tasks, dependencies={item.task_id: item.dependencies for item in tasks}
                )
            )
