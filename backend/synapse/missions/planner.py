from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.missions.dag import TaskGraph
from synapse.missions.errors import PlanInvalid
from synapse.missions.models import MissionPlan, MissionTask, PlanValidationResult


class PlanProvider(Protocol):
    def create_mission_plan(self, objective: str, options: dict[str, Any]) -> dict[str, Any]: ...


class PlannerRuntime:
    def __init__(self, data_dir: DataDir, events: EventBus, provider: PlanProvider | None = None):
        self.data_dir = data_dir
        self.events = events
        self.provider = provider
        self.lock = RLock()

    def create_plan(
        self,
        mission_id: str,
        objective: str,
        constraints: dict[str, Any] | None = None,
        preferred_agents: list[str] | None = None,
        planning_options: dict[str, Any] | None = None,
        tasks: list[MissionTask | dict[str, Any]] | None = None,
    ) -> MissionPlan:
        options = {
            **(planning_options or {}),
            "constraints": constraints or {},
            "preferred_agents": preferred_agents or [],
        }
        generated_by = "manual"
        provider = model = None
        raw_tasks: list[MissionTask | dict[str, Any]] = tasks or []
        if tasks is None:
            if not self.provider:
                raise PlanInvalid("Manual tasks or a planning provider are required.")
            try:
                generated = self.provider.create_mission_plan(objective, options)
                raw_tasks = generated.get("tasks", [])
                provider = generated.get("provider")
                model = generated.get("model")
                generated_by = "model"
            except (TypeError, ValueError, KeyError) as exc:
                raise PlanInvalid(f"Planning provider returned malformed output: {exc}") from exc
        parsed = [
            item if isinstance(item, MissionTask) else MissionTask(mission_id=mission_id, **item)
            for item in raw_tasks
        ]
        plan = MissionPlan(
            mission_id=mission_id,
            tasks=parsed,
            dependencies={task.task_id: list(task.dependencies) for task in parsed},
            completion_criteria=options.get("completion_criteria", {"all_required_verified": True}),
            generated_by=generated_by,
            provider=provider,
            model=model,
        )
        validation = self.validate_plan(plan)
        if not validation.valid:
            raise PlanInvalid("; ".join(validation.errors))
        persisted = MissionPlan(
            **{**asdict(plan), "tasks": parsed, "validation_result": validation}
        )
        dump_structured_file(self._path(mission_id, persisted.plan_id), asdict(persisted))
        self.events.emit(
            "mission.planned", mission_id, {"mission_id": mission_id, "plan_id": persisted.plan_id}
        )
        return persisted

    def validate_plan(self, plan: MissionPlan) -> PlanValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if not plan.tasks:
            errors.append("Plan must contain at least one task.")
        if len(plan.tasks) > 64:
            errors.append("Plan exceeds the 64-task execution budget.")
        for task in plan.tasks:
            if not task.title.strip() or not task.objective.strip():
                errors.append(f"Task {task.task_id} must have a title and objective.")
            if task.timeout_seconds <= 0 or task.max_attempts < 1:
                errors.append(f"Task {task.task_id} has invalid execution limits.")
            if task.required_tools and not task.required_capabilities:
                warnings.append(
                    f"Task {task.task_id} requires tools without declaring capabilities."
                )
        try:
            TaskGraph(plan.tasks).validate()
        except PlanInvalid as exc:
            errors.append(str(exc))
        return PlanValidationResult(valid=not errors, errors=errors, warnings=sorted(warnings))

    def get_plan(self, mission_id: str, plan_id: str) -> MissionPlan:
        raw = load_structured_file(self._path(mission_id, plan_id))
        raw["tasks"] = [MissionTask(**task) for task in raw.get("tasks", [])]
        validation = raw.get("validation_result")
        raw["validation_result"] = PlanValidationResult(**validation) if validation else None
        return MissionPlan(**raw)

    def save_plan(self, plan: MissionPlan) -> MissionPlan:
        validation = self.validate_plan(plan)
        if not validation.valid:
            raise PlanInvalid("; ".join(validation.errors))
        persisted = MissionPlan(
            **{**asdict(plan), "tasks": plan.tasks, "validation_result": validation}
        )
        dump_structured_file(self._path(plan.mission_id, plan.plan_id), asdict(persisted))
        return persisted

    def list_plans(self, mission_id: str) -> list[MissionPlan]:
        paths = sorted(self.data_dir.resolve(f"missions/{mission_id}/plans").glob("*.yaml"))
        plans = [self.get_plan(mission_id, path.stem) for path in paths]
        return sorted(plans, key=lambda item: (item.version, item.created_at, item.plan_id))

    def replace_plan(
        self,
        mission_id: str,
        plan_id: str,
        expected_version: int,
        tasks: list[MissionTask | dict[str, Any]],
    ) -> MissionPlan:
        current = self.get_plan(mission_id, plan_id)
        if current.version != expected_version:
            raise PlanInvalid(
                f"Plan version conflict: expected {expected_version}, found {current.version}"
            )
        parsed = [
            item if isinstance(item, MissionTask) else MissionTask(mission_id=mission_id, **item)
            for item in tasks
        ]
        # A proposal cannot carry self-declared completion. Preserve only results
        # already validated under unchanged inputs, including transitive dependencies.
        previous = {task.task_id: task for task in current.tasks}
        fields = ("objective", "dependencies", "required_capabilities", "required_tools",
                  "required_permissions", "verification_policy", "metadata", "expected_output")
        changed = {task.task_id for task in parsed if task.task_id not in previous or any(
            getattr(task, name) != getattr(previous[task.task_id], name) for name in fields)}
        while True:
            affected = changed | {task.task_id for task in parsed if set(task.dependencies) & changed}
            if affected == changed:
                break
            changed = affected
        parsed = [previous[task.task_id] if task.task_id in previous and task.task_id not in changed
                  else replace(task, status="pending", result=None, error=None, completed_at=None,
                               assigned_agent_id=None, assigned_worker_id=None, started_at=None)
                  for task in parsed]
        replacement = MissionPlan(
            mission_id=mission_id,
            tasks=parsed,
            dependencies={task.task_id: list(task.dependencies) for task in parsed},
            completion_criteria=current.completion_criteria,
            generated_by="manual_replace",
            version=current.version + 1,
        )
        validation = self.validate_plan(replacement)
        if not validation.valid:
            raise PlanInvalid("; ".join(validation.errors))
        persisted = MissionPlan(
            **{
                **asdict(replacement),
                "tasks": parsed,
                "validation_result": validation,
            }
        )
        dump_structured_file(
            self._path(mission_id, persisted.plan_id),
            asdict(persisted),
        )
        self.events.emit(
            "mission.plan_replaced",
            mission_id,
            {
                "mission_id": mission_id,
                "previous_plan_id": plan_id,
                "plan_id": persisted.plan_id,
                "version": persisted.version,
            },
        )
        return persisted

    def _path(self, mission_id: str, plan_id: str) -> Path:
        return self.data_dir.resolve(f"missions/{mission_id}/plans/{plan_id}.yaml")
