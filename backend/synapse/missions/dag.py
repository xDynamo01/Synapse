from __future__ import annotations

from collections import deque

from synapse.missions.errors import DependencyCycle, DependencyMissing, PlanInvalid
from synapse.missions.models import MissionTask


class TaskGraph:
    def __init__(self, tasks: list[MissionTask]):
        self.tasks = {task.task_id: task for task in tasks}
        if len(self.tasks) != len(tasks):
            raise PlanInvalid("Task IDs must be unique.")
        self.dependencies = {task.task_id: set(task.dependencies) for task in tasks}

    def add_task(self, task: MissionTask) -> None:
        if task.task_id in self.tasks:
            raise PlanInvalid(f"Duplicate task ID: {task.task_id}")
        self.tasks[task.task_id] = task
        self.dependencies[task.task_id] = set(task.dependencies)
        self.validate()

    def add_dependency(self, task_id: str, dependency_id: str) -> None:
        self._require(task_id)
        self._require(dependency_id)
        if task_id == dependency_id:
            raise DependencyCycle(f"Task cannot depend on itself: {task_id}")
        self.dependencies[task_id].add(dependency_id)
        try:
            self.validate()
        except PlanInvalid:
            self.dependencies[task_id].remove(dependency_id)
            raise

    def remove_dependency(self, task_id: str, dependency_id: str) -> None:
        self._require(task_id)
        self.dependencies[task_id].discard(dependency_id)

    def validate(self) -> None:
        for task_id, dependencies in self.dependencies.items():
            missing = sorted(dependencies - self.tasks.keys())
            if missing:
                raise DependencyMissing(
                    f"Task {task_id} has missing dependencies: {', '.join(missing)}"
                )
            if task_id in dependencies:
                raise DependencyCycle(f"Task cannot depend on itself: {task_id}")
        self.topological_order()

    def topological_order(self) -> list[str]:
        indegree = {task_id: len(deps) for task_id, deps in self.dependencies.items()}
        downstream: dict[str, set[str]] = {task_id: set() for task_id in self.tasks}
        for task_id, dependencies in self.dependencies.items():
            for dependency in dependencies:
                downstream.setdefault(dependency, set()).add(task_id)
        ready = deque(sorted(task_id for task_id, degree in indegree.items() if degree == 0))
        result: list[str] = []
        while ready:
            task_id = ready.popleft()
            result.append(task_id)
            for child in sorted(downstream[task_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(result) != len(self.tasks):
            raise DependencyCycle("Task dependency graph contains a cycle.")
        return result

    def ready_tasks(self) -> list[MissionTask]:
        completed = {task_id for task_id, task in self.tasks.items() if task.status == "completed"}
        runnable = {"pending", "ready"}
        return [
            self.tasks[task_id]
            for task_id in self.topological_order()
            if self.tasks[task_id].status in runnable and self.dependencies[task_id] <= completed
        ]

    def blocked_tasks(self) -> list[MissionTask]:
        terminal_failure = {"failed", "timed_out", "cancelled", "dead_lettered"}
        return [
            self.tasks[task_id]
            for task_id in sorted(self.tasks)
            if any(self.tasks[dep].status in terminal_failure for dep in self.dependencies[task_id])
        ]

    def downstream_tasks(self, task_id: str) -> list[str]:
        self._require(task_id)
        return sorted(item for item, deps in self.dependencies.items() if task_id in deps)

    def upstream_tasks(self, task_id: str) -> list[str]:
        self._require(task_id)
        return sorted(self.dependencies[task_id])

    def unlock_after_completion(self, task_id: str) -> list[MissionTask]:
        self._require(task_id)
        return [
            task for task in self.ready_tasks() if task.task_id in self.downstream_tasks(task_id)
        ]

    def _require(self, task_id: str) -> None:
        if task_id not in self.tasks:
            raise DependencyMissing(f"Task not found in graph: {task_id}")
