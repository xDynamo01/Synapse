from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from synapse.missions.dag import TaskGraph
from synapse.missions.errors import NoWorkerAvailable
from synapse.missions.models import now_iso


@dataclass(frozen=True)
class DispatchResult:
    mission_id: str
    dispatched: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    rejected_workers: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    active_attempts: list[str] = field(default_factory=list)


class MissionDispatcher:
    def __init__(
        self,
        missions: Any,
        planner: Any,
        attempts: Any,
        workers: Any,
        scheduler: Any,
        execution: Any,
        events: Any,
    ):
        self.missions = missions
        self.planner = planner
        self.attempts = attempts
        self.workers = workers
        self.scheduler = scheduler
        self.execution = execution
        self.events = events

    def dispatch_ready_tasks(
        self,
        mission_id: str,
        max_concurrency: int | None = None,
        *,
        execute: bool = True,
    ) -> DispatchResult:
        mission = self.missions.get_mission(mission_id)
        if mission.status in {"paused", "cancelled", "completed", "failed"}:
            return DispatchResult(
                mission_id,
                skipped=[{"mission_id": mission_id, "reason": f"mission_{mission.status}"}],
            )
        if not mission.plan_id:
            raise ValueError("Mission has no active plan.")
        if mission.status != "running":
            mission = self.missions._persist(
                replace(
                    mission,
                    status="running",
                    started_at=mission.started_at or now_iso(),
                    revision=mission.revision + 1,
                    updated_at=now_iso(),
                ),
                "mission.started",
            )
        plan = self.planner.get_plan(mission_id, mission.plan_id)
        graph = TaskGraph(plan.tasks)
        ready = graph.ready_tasks()
        blocked = [task.task_id for task in graph.blocked_tasks()]
        active = self.attempts.list(mission_id=mission_id)
        active = [item for item in active if self.attempts.active_for_task(item.task_id) == item]
        limit = max_concurrency or int(mission.metadata.get("max_concurrency", 1))
        slots = max(0, limit - len(active))
        reserved = {item.worker_id for item in active}
        dispatched: list[str] = []
        skipped: list[dict[str, str]] = []
        rejected: list[dict[str, Any]] = []
        tasks = list(plan.tasks)
        for task in ready:
            if len(dispatched) >= slots:
                skipped.append({"task_id": task.task_id, "reason": "concurrency_limit"})
                continue
            if self.attempts.active_for_task(task.task_id):
                skipped.append({"task_id": task.task_id, "reason": "active_attempt"})
                continue
            candidates = [
                worker for worker in self.workers.list() if worker.worker_id not in reserved
            ]
            try:
                selection = self.scheduler.select_worker(task, candidates=candidates)
            except NoWorkerAvailable as exc:
                skipped.append({"task_id": task.task_id, "reason": "no_worker_available"})
                rejected.append({"task_id": task.task_id, "error": str(exc)})
                continue
            index = next(i for i, item in enumerate(tasks) if item.task_id == task.task_id)
            operational_agent_id = str(
                task.metadata.get("ephemeral_agent_id") or selection.selected_agent
            )
            assigned = replace(
                task,
                status="assigned",
                assigned_agent_id=operational_agent_id,
                assigned_worker_id=selection.selected_worker,
                revision=task.revision + 1,
                updated_at=now_iso(),
            )
            tasks[index] = assigned
            attempt = self.attempts.create(
                mission_id,
                task.task_id,
                selection.selected_worker,
                operational_agent_id,
                correlation_id=task.correlation_id,
                input_snapshot={
                    "objective": task.objective,
                    "metadata": task.metadata,
                    "dependency_outputs": [
                        {
                            "task_id": dependency_id,
                            "result": next(
                                item for item in tasks if item.task_id == dependency_id
                            ).result,
                            "provenance": f"mission:{mission_id}:task:{dependency_id}",
                        }
                        for dependency_id in task.dependencies
                    ],
                },
                idempotency_key=f"dispatch:{mission_id}:{task.task_id}:{task.revision}",
            )
            dispatched.append(attempt.attempt_id)
            reserved.add(selection.selected_worker)
            rejected.extend(asdict(item) for item in selection.rejected_candidates)
            self.events.emit(
                "task.assigned",
                operational_agent_id,
                {
                    "mission_id": mission_id,
                    "task_id": task.task_id,
                    "attempt_id": attempt.attempt_id,
                    "worker_id": selection.selected_worker,
                },
            )
        self.planner.save_plan(
            replace(
                plan, tasks=tasks, dependencies={item.task_id: item.dependencies for item in tasks}
            )
        )
        if execute:
            for attempt_id in dispatched:
                self.execution.execute_attempt(attempt_id)
            self.missions.refresh_progress(mission_id)
        current_active = [
            item.attempt_id
            for item in self.attempts.list(mission_id=mission_id)
            if self.attempts.active_for_task(item.task_id) == item
        ]
        return DispatchResult(
            mission_id, dispatched, skipped, blocked, rejected, active_attempts=current_active
        )
