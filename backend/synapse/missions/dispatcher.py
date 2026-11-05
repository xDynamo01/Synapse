from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from threading import RLock
from typing import Any

from synapse.missions.dag import TaskGraph
from synapse.missions.errors import NoWorkerAvailable
from synapse.missions.models import MissionTask, now_iso


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
        self.admission_lock = RLock()
        self.resource_limit: Callable[[str, int], int] | None = None
        self.route_admission: Callable[[str, MissionTask, str], tuple[str, str] | None] | None = None
        self.worker_admission: Callable[[str, MissionTask, str], bool] | None = None

    def dispatch_ready_tasks(
        self, mission_id: str, max_concurrency: int | None = None, *, execute: bool = True,
    ) -> DispatchResult:
        # Admit once under the shared plan lock. Only inference runs concurrently.
        with self.admission_lock, self.planner.lock:
            result = self._admit_ready_tasks(mission_id, max_concurrency, execute=False)
        if execute and result.dispatched:
            with ThreadPoolExecutor(max_workers=len(result.dispatched)) as executor:
                futures = [executor.submit(self.execution.execute_attempt, item)
                           for item in result.dispatched]
                failures = [future.exception() for future in futures]
            self.missions.refresh_progress(mission_id)
            for failure in failures:
                if failure is not None:
                    raise failure
        return replace(result, active_attempts=[item.attempt_id
                       for item in self.attempts.list(mission_id=mission_id)
                       if self.attempts.active_for_task(item.task_id) == item])

    def _admit_ready_tasks(
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
        priorities = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        ready = sorted(graph.ready_tasks(), key=lambda task: (priorities.get(task.priority, 2), task.task_id))
        blocked = [task.task_id for task in graph.blocked_tasks()]
        active = self.attempts.list(mission_id=mission_id)
        active = [item for item in active if self.attempts.active_for_task(item.task_id) == item]
        limit = max_concurrency if max_concurrency is not None else int(mission.metadata.get("max_concurrency", 1))
        if limit < 1 or limit > 32:
            raise ValueError("Mission concurrency must be between 1 and 32.")
        if self.resource_limit is not None:
            limit = self.resource_limit(mission_id, limit)
        slots = max(0, limit - len(active))
        reserved = {item.worker_id for item in self.attempts.list()
                    if self.attempts.active_for_task(item.task_id) == item}
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
                and (not task.metadata.get("ephemeral_agent_id")
                     or worker.agent_id == task.metadata["ephemeral_agent_id"])
                and (not worker.agent_id.startswith("ephemeral:")
                     or worker.agent_id == task.metadata.get("ephemeral_agent_id"))
                and (self.worker_admission is None or self.worker_admission(
                    mission_id, task, worker.agent_id))
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
            selected_route = self.route_admission(mission_id, task, operational_agent_id) if self.route_admission else None
            assigned = replace(
                task,
                status="assigned",
                assigned_agent_id=operational_agent_id,
                assigned_worker_id=selection.selected_worker,
                revision=task.revision + 1,
                updated_at=now_iso(),
                metadata=({**task.metadata, "provider": selected_route[0], "model": selected_route[1]}
                          if selected_route else task.metadata),
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
