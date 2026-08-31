from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.missions.models import (
    MISSION_PRIORITIES,
    MISSION_STATUSES,
    Mission,
    MissionDelegationLink,
    MissionSummary,
    now_iso,
)
from synapse.project_governance.models import RFCImplementationBinding

if TYPE_CHECKING:
    from synapse.agents.registry import AgentRegistry
    from synapse.conversations.runtime import ConversationRuntime
    from synapse.dead_letter.runtime import DeadLetterRuntime
    from synapse.delegation.runtime import DelegationRuntime
    from synapse.missions.attempts import TaskAttemptRuntime
    from synapse.missions.dispatcher import MissionDispatcher
    from synapse.missions.planner import PlannerRuntime
    from synapse.missions.verification import ResultVerifier
    from synapse.project_governance.contracts import ImplementationBindingPort
    from synapse.tools.contracts import ToolExecutionPort
    from synapse.workers.registry import WorkerRegistry
    from synapse.workers.scheduler import WorkerScheduler


class MissionRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        delegation: DelegationRuntime | None = None,
        dead_letter: DeadLetterRuntime | None = None,
        conversations: ConversationRuntime | None = None,
        agents: AgentRegistry | None = None,
        planner: PlannerRuntime | None = None,
        worker_registry: WorkerRegistry | None = None,
        worker_scheduler: WorkerScheduler | None = None,
        verifier: ResultVerifier | None = None,
        attempts: TaskAttemptRuntime | None = None,
        implementation_binding: ImplementationBindingPort | None = None,
    ):
        self.data_dir = data_dir
        self.events = events
        self.delegation = delegation
        self.dead_letter = dead_letter
        self.conversations = conversations
        self.agents = agents
        self.planner = planner
        self.worker_registry = worker_registry
        self.worker_scheduler = worker_scheduler
        self.verifier = verifier
        self.attempts = attempts
        self.implementation_binding = implementation_binding
        self.dispatcher: MissionDispatcher | None = None
        self.resource_pressure: Any | None = None
        self.desktop_runtime: Any | None = None
        self.tool_runtime: ToolExecutionPort | None = None

    def execute_desktop_automation(
        self,
        mission_id: str,
        automation_plan_id: str,
        *,
        approval_id: str | None = None,
    ) -> Any:
        self.get_mission(mission_id)
        if self.tool_runtime is None:
            raise ValidationError("Desktop automation runtime is unavailable.")
        from synapse.tools.identities import DESKTOP_EXECUTE
        from synapse.tools.models import ToolExecutionRequest

        execution = self.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=DESKTOP_EXECUTE,
                arguments={
                    "plan_id": automation_plan_id,
                    **({"approval_id": approval_id} if approval_id else {}),
                },
                caller="mission",
                caller_type="system",
                mission_id=mission_id,
            )
        )
        from synapse.desktop_automation.models import automation_result_from_dict

        result = automation_result_from_dict(execution.output)
        self.events.emit(
            "mission.desktop_automation_completed",
            "mission",
            {
                "mission_id": mission_id,
                "automation_plan_id": automation_plan_id,
                "status": result.status,
            },
        )
        return result

    def dispatch_ready_tasks(
        self,
        mission_id: str,
        max_concurrency: int | None = None,
        *,
        execute: bool = True,
    ) -> Any:
        mission = self.get_mission(mission_id)
        resource_guard = bool(mission.metadata.get("resource_pressure_guard", False))
        if self.resource_pressure is not None and resource_guard:
            capacity = self.resource_pressure.assess_capacity("mission")
            if not capacity.sufficient:
                from synapse.missions.dispatcher import DispatchResult

                self.events.emit(
                    "mission.deferred_resource_pressure",
                    "system_insight",
                    {
                        "mission_id": mission_id,
                        "pressure_level": capacity.pressure_level,
                        "reason": capacity.reason,
                    },
                )
                return DispatchResult(
                    mission_id=mission_id,
                    skipped=[{"mission_id": mission_id, "reason": "resource_pressure"}],
                    warnings=[capacity.reason],
                )
        if not self.dispatcher:
            raise ValidationError("Mission dispatcher is unavailable.")
        return self.dispatcher.dispatch_ready_tasks(
            mission_id,
            max_concurrency,
            execute=execute,
        )

    def refresh_progress(self, mission_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        if not mission.plan_id:
            return mission
        planner = cast("PlannerRuntime", self.planner)
        plan = planner.get_plan(mission_id, mission.plan_id)
        total_weight = sum(max(task.weight, 0) for task in plan.tasks)
        completed_weight = sum(
            max(task.weight, 0)
            for task in plan.tasks
            if task.status == "completed"
            and task.result
            and task.result.get("verification_status", "passed") == "passed"
        )
        progress = completed_weight / total_weight * 100 if total_weight else 0.0
        failed = any(task.status in {"failed", "timed_out", "dead_lettered"} for task in plan.tasks)
        completed = bool(plan.tasks) and all(task.status == "completed" for task in plan.tasks)
        status = "completed" if completed else ("blocked" if failed else mission.status)
        if mission.progress == progress and mission.status == status:
            return mission
        return self._persist(
            replace(
                mission,
                progress=progress,
                status=status,
                completed_at=now_iso() if completed else mission.completed_at,
                revision=mission.revision + 1,
                updated_at=now_iso(),
            ),
            "mission.completed" if completed else "mission.progress",
        )

    def list_tasks(self, mission_id: str) -> list[Any]:
        mission, plan = self._mission_plan(mission_id)
        del mission
        return plan.tasks

    def get_task(self, mission_id: str, task_id: str) -> Any:
        _mission, plan = self._mission_plan(mission_id)
        task = next((item for item in plan.tasks if item.task_id == task_id), None)
        if not task:
            raise NotFound(f"Mission task not found: {mission_id}/{task_id}")
        return task

    def update_task(
        self,
        mission_id: str,
        task_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        expected_revision: int,
    ) -> Any:
        _mission, plan = self._mission_plan(mission_id)
        task = self.get_task(mission_id, task_id)
        if task.revision != expected_revision:
            raise ValidationError(
                f"Task revision conflict: expected {expected_revision}, found {task.revision}"
            )
        updated = replace(
            task,
            metadata=metadata if metadata is not None else task.metadata,
            dependencies=dependencies if dependencies is not None else task.dependencies,
            revision=task.revision + 1,
            updated_at=now_iso(),
        )
        self._save_plan_task(plan, updated)
        self.events.emit("task.updated", task.assigned_agent_id or "mission", asdict(updated))
        return updated

    def assign_task(
        self,
        mission_id: str,
        task_id: str,
        worker_id: str,
        *,
        expected_revision: int,
        reassign: bool = False,
    ) -> Any:
        _mission, plan = self._mission_plan(mission_id)
        task = self.get_task(mission_id, task_id)
        attempts = cast("TaskAttemptRuntime", self.attempts)
        worker_registry = cast("WorkerRegistry", self.worker_registry)
        if task.revision != expected_revision:
            raise ValidationError(
                f"Task revision conflict: expected {expected_revision}, found {task.revision}"
            )
        active = attempts.active_for_task(task_id)
        if active and not reassign:
            raise ValidationError("Task has an active attempt; explicit reassign is required.")
        if active:
            attempts.transition(active.attempt_id, "cancelled", error={"type": "reassigned"})
            worker_registry.set_workload(active.worker_id, 0.0, None, None)
        worker = worker_registry.get(worker_id)
        if worker.status not in {"idle", "sleeping"}:
            raise ValidationError(f"Worker is unavailable: {worker.status}")
        if not set(task.required_capabilities) <= set(worker.capabilities):
            raise ValidationError("Worker capability mismatch.")
        updated = replace(
            task,
            status="assigned",
            assigned_worker_id=worker.worker_id,
            assigned_agent_id=worker.agent_id,
            revision=task.revision + 1,
            updated_at=now_iso(),
        )
        self._save_plan_task(plan, updated)
        attempt = attempts.create(
            mission_id,
            task_id,
            worker.worker_id,
            worker.agent_id,
            correlation_id=task.correlation_id,
            input_snapshot={"objective": task.objective, "metadata": task.metadata},
            idempotency_key=f"assignment:{mission_id}:{task_id}:{updated.revision}",
        )
        self.events.emit(
            "task.reassigned" if reassign else "task.assigned",
            worker.agent_id,
            {"mission_id": mission_id, "task_id": task_id, "attempt_id": attempt.attempt_id},
        )
        return updated

    def cancel_task(self, mission_id: str, task_id: str, *, expected_revision: int) -> Any:
        _mission, plan = self._mission_plan(mission_id)
        task = self.get_task(mission_id, task_id)
        if task.revision != expected_revision:
            raise ValidationError(
                f"Task revision conflict: expected {expected_revision}, found {task.revision}"
            )
        if task.status == "cancelled":
            return task
        if task.status == "completed":
            raise ValidationError("Completed task cannot be cancelled.")
        attempts = self.attempts
        worker_registry = cast("WorkerRegistry", self.worker_registry)
        if attempts is not None:
            active = attempts.active_for_task(task_id)
            if active:
                attempts.transition(active.attempt_id, "cancelled")
                worker_registry.set_workload(active.worker_id, 0.0, None, None)
        updated = replace(
            task,
            status="cancelled",
            completed_at=now_iso(),
            revision=task.revision + 1,
            updated_at=now_iso(),
        )
        self._save_plan_task(plan, updated)
        self.events.emit("task.cancelled", task.assigned_agent_id or "mission", asdict(updated))
        return updated

    def verify_task(self, mission_id: str, task_id: str) -> Any:
        task = self.get_task(mission_id, task_id)
        verifier = cast("ResultVerifier", self.verifier)
        verification = verifier.verify(task.result, task.verification_policy)
        self.events.emit(
            "task.verified" if verification.status == "passed" else "task.verification_failed",
            task.assigned_agent_id or "mission",
            {"mission_id": mission_id, "task_id": task_id, "verification": asdict(verification)},
        )
        return verification

    def _mission_plan(self, mission_id: str) -> tuple[Mission, Any]:
        mission = self.get_mission(mission_id)
        if not mission.plan_id:
            raise ValidationError("Mission has no active plan.")
        planner = cast("PlannerRuntime", self.planner)
        return mission, planner.get_plan(mission_id, mission.plan_id)

    def _save_plan_task(self, plan: Any, updated: Any) -> None:
        tasks = list(plan.tasks)
        index = next(index for index, item in enumerate(tasks) if item.task_id == updated.task_id)
        tasks[index] = updated
        from synapse.missions.dag import TaskGraph

        TaskGraph(tasks).validate()
        planner = cast("PlannerRuntime", self.planner)
        planner.save_plan(
            replace(
                plan, tasks=tasks, dependencies={item.task_id: item.dependencies for item in tasks}
            )
        )

    def create_mission(
        self,
        title: str,
        description: str = "",
        status: str = "draft",
        priority: str = "normal",
        owner_agent_id: str | None = None,
        created_by: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        objective: str | None = None,
        requester: str | None = None,
        deadline: str | None = None,
        project_id: str | None = None,
        rfc_id: str | None = None,
        rfc_revision: int | None = None,
        rfc_checksum: str | None = None,
        implementation_plan_id: str | None = None,
        implementation_plan_revision: int | None = None,
        implementation_plan_checksum: str | None = None,
        information_classification: str = "internal",
        information_categories: tuple[str, ...] = (),
        allowed_processing_boundaries: tuple[str, ...] = (),
        allowed_provider_profiles: tuple[str, ...] = (),
        external_processing_policy: str = "policy-controlled",
        training_use_policy: str = "prohibited",
    ) -> Mission:
        if not title.strip():
            raise ValidationError("Mission title is required.")
        self._validate_status(status)
        self._validate_priority(priority)
        owner = owner_agent_id.strip().lower() if owner_agent_id else None
        if owner and self.agents:
            self.agents.get(owner)
        if conversation_id and self.conversations:
            self.conversations.get_conversation(conversation_id)
        mission = Mission(
            title=title.strip(),
            objective=(objective or description or title).strip(),
            description=description,
            status=status,
            priority=priority,
            owner_agent_id=owner,
            created_by=created_by,
            conversation_id=conversation_id,
            metadata=metadata or {},
            requester=requester or created_by,
            deadline=deadline,
            project_id=project_id,
            rfc_id=rfc_id,
            rfc_revision=rfc_revision,
            rfc_checksum=rfc_checksum,
            implementation_plan_id=implementation_plan_id,
            implementation_plan_revision=implementation_plan_revision,
            implementation_plan_checksum=implementation_plan_checksum,
            information_classification=information_classification,
            information_categories=information_categories,
            allowed_processing_boundaries=allowed_processing_boundaries,
            allowed_provider_profiles=allowed_provider_profiles,
            external_processing_policy=external_processing_policy,
            training_use_policy=training_use_policy,
        )
        self._write_mission(mission)
        self.events.emit("mission.created", created_by or "mission", asdict(mission))
        return mission

    def get_mission(self, mission_id: str) -> Mission:
        path = self._mission_path(mission_id)
        if not path.exists():
            raise NotFound(f"Mission not found: {mission_id}")
        return self._read_mission(path)

    def list_missions(self, status: str | None = None) -> list[Mission]:
        if status:
            self._validate_status(status)
        missions = [
            self._read_mission(path)
            for path in sorted(self.data_dir.resolve("missions").glob("*.yaml"))
            if not path.name.endswith(".delegations.yaml")
        ]
        if status:
            missions = [mission for mission in missions if mission.status == status]
        return sorted(missions, key=lambda mission: (mission.updated_at, mission.mission_id))

    def update_mission(
        self,
        mission_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        owner_agent_id: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> Mission:
        current = self.get_mission(mission_id)
        if expected_revision is not None and current.revision != expected_revision:
            raise ValidationError(
                f"Mission revision conflict: expected {expected_revision}, found {current.revision}"
            )
        next_status = status or current.status
        next_priority = priority or current.priority
        self._validate_status(next_status)
        self._validate_priority(next_priority)
        owner = (
            owner_agent_id.strip().lower()
            if owner_agent_id is not None and owner_agent_id
            else current.owner_agent_id
        )
        if owner and self.agents:
            self.agents.get(owner)
        next_conversation_id = (
            conversation_id if conversation_id is not None else current.conversation_id
        )
        if next_conversation_id and self.conversations:
            self.conversations.get_conversation(next_conversation_id)
        updated = Mission(
            mission_id=current.mission_id,
            title=title if title is not None else current.title,
            objective=current.objective,
            description=description if description is not None else current.description,
            status=next_status,
            priority=next_priority,
            owner_agent_id=owner,
            created_by=current.created_by,
            conversation_id=next_conversation_id,
            metadata=metadata if metadata is not None else current.metadata,
            requester=current.requester,
            plan_id=current.plan_id,
            progress=current.progress,
            started_at=current.started_at,
            completed_at=current.completed_at,
            paused_at=current.paused_at,
            cancelled_at=current.cancelled_at,
            deadline=current.deadline,
            revision=current.revision + 1,
            created_at=current.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            project_id=current.project_id,
            rfc_id=current.rfc_id,
            rfc_revision=current.rfc_revision,
            rfc_checksum=current.rfc_checksum,
            implementation_plan_id=current.implementation_plan_id,
            implementation_plan_revision=current.implementation_plan_revision,
            implementation_plan_checksum=current.implementation_plan_checksum,
        )
        self._write_mission(updated)
        self.events.emit("mission.updated", updated.created_by or "mission", asdict(updated))
        return updated

    def archive_mission(self, mission_id: str) -> Mission:
        mission = self.update_mission(mission_id, status="archived")
        self.events.emit("mission.archived", mission.created_by or "mission", asdict(mission))
        return mission

    def attach_plan(self, mission_id: str, plan_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        if not self.planner:
            raise ValidationError("Planner runtime is unavailable.")
        self.planner.get_plan(mission_id, plan_id)
        return self._persist(
            replace(
                mission,
                plan_id=plan_id,
                status="planned",
                revision=mission.revision + 1,
                updated_at=now_iso(),
            ),
            "mission.planned",
        )

    def pause(self, mission_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        if mission.status == "paused":
            return mission
        if mission.status not in {"running", "blocked", "active"}:
            raise ValidationError(f"Mission cannot be paused from {mission.status}.")
        return self._persist(
            replace(
                mission,
                status="paused",
                paused_at=now_iso(),
                revision=mission.revision + 1,
                updated_at=now_iso(),
            ),
            "mission.paused",
        )

    def resume(self, mission_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        if mission.status == "running":
            return mission
        if mission.status != "paused":
            raise ValidationError(f"Mission cannot be resumed from {mission.status}.")
        return self._persist(
            replace(
                mission,
                status="running",
                paused_at=None,
                revision=mission.revision + 1,
                updated_at=now_iso(),
            ),
            "mission.resumed",
        )

    def cancel(self, mission_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        if mission.status == "cancelled":
            return mission
        if mission.status == "completed":
            raise ValidationError("Completed mission cannot be cancelled.")
        return self._persist(
            replace(
                mission,
                status="cancelled",
                cancelled_at=now_iso(),
                revision=mission.revision + 1,
                updated_at=now_iso(),
            ),
            "mission.cancelled",
        )

    def run_mission(self, mission_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        binding_values = (
            mission.project_id,
            mission.rfc_id,
            mission.rfc_revision,
            mission.rfc_checksum,
            mission.implementation_plan_id,
            mission.implementation_plan_revision,
            mission.implementation_plan_checksum,
        )
        if any(value is not None for value in binding_values):
            if not all(value is not None for value in binding_values):
                raise ValidationError("Mission has an incomplete RFC implementation binding.")
            if not self.implementation_binding:
                raise ValidationError("RFC implementation gate is unavailable.")
            decision = self.implementation_binding.validate_binding(
                RFCImplementationBinding(
                    str(mission.project_id),
                    str(mission.rfc_id),
                    cast(int, mission.rfc_revision),
                    str(mission.rfc_checksum),
                    str(mission.implementation_plan_id),
                    cast(int, mission.implementation_plan_revision),
                    str(mission.implementation_plan_checksum),
                )
            )
            if not decision.allowed:
                raise ValidationError(f"RFC gate blocked mission: {decision.disposition}")
        if mission.status in {"completed", "cancelled", "paused"}:
            return mission
        planner = self.planner
        worker_registry = self.worker_registry
        worker_scheduler = self.worker_scheduler
        verifier = self.verifier
        if (
            planner is None
            or worker_registry is None
            or worker_scheduler is None
            or verifier is None
        ):
            raise ValidationError("Mission execution dependencies are unavailable.")
        if not mission.plan_id:
            raise ValidationError("Mission has no active plan.")
        plan = planner.get_plan(mission_id, mission.plan_id)
        from synapse.missions.dag import TaskGraph

        graph = TaskGraph(plan.tasks)
        graph.validate()
        if mission.status != "running":
            mission = self._persist(
                replace(
                    mission,
                    status="running",
                    started_at=mission.started_at or now_iso(),
                    revision=mission.revision + 1,
                    updated_at=now_iso(),
                ),
                "mission.started",
            )
        tasks = list(plan.tasks)
        ready = graph.ready_tasks()
        for task in ready:
            selection = worker_scheduler.select_worker(task)
            operational_agent_id = str(
                task.metadata.get("ephemeral_agent_id") or selection.selected_agent
            )
            index = next(i for i, item in enumerate(tasks) if item.task_id == task.task_id)
            tasks[index] = replace(
                task,
                status="assigned",
                assigned_agent_id=operational_agent_id,
                assigned_worker_id=selection.selected_worker,
                revision=task.revision + 1,
                updated_at=now_iso(),
            )
            if self.attempts:
                self.attempts.create(
                    mission_id,
                    task.task_id,
                    selection.selected_worker,
                    operational_agent_id,
                    correlation_id=task.correlation_id,
                    input_snapshot={"objective": task.objective, "metadata": task.metadata},
                    idempotency_key=f"{mission_id}:{task.task_id}:{task.revision}",
                )
            self.events.emit(
                "task.assigned",
                operational_agent_id,
                {
                    "mission_id": mission_id,
                    "task_id": task.task_id,
                    "worker_id": selection.selected_worker,
                },
            )
        completed = len([task for task in tasks if task.status == "completed"])
        progress = (completed / len(tasks) * 100) if tasks else 0.0
        updated_plan = replace(
            plan, tasks=tasks, dependencies={task.task_id: task.dependencies for task in tasks}
        )
        planner.save_plan(updated_plan)
        status = (
            "completed"
            if completed == len(tasks)
            else ("blocked" if not ready and completed < len(tasks) else "running")
        )
        completed_at = now_iso() if status == "completed" else None
        return self._persist(
            replace(
                mission,
                status=status,
                progress=progress,
                completed_at=completed_at,
                revision=mission.revision + 1,
                updated_at=now_iso(),
            ),
            f"mission.{status}",
        )

    def _persist(self, mission: Mission, event_type: str) -> Mission:
        self._write_mission(mission)
        self.events.emit(
            event_type, mission.requester or mission.created_by or "mission", asdict(mission)
        )
        return mission

    def link_task(self, mission_id: str, task_id: str) -> MissionDelegationLink:
        self.get_mission(mission_id)
        if self.delegation:
            self.delegation.get_task(task_id)
        links = self._read_links(mission_id)
        existing = next((link for link in links if link.task_id == task_id), None)
        if existing:
            return existing
        link = MissionDelegationLink(mission_id=mission_id, task_id=task_id)
        links.append(link)
        self._write_links(mission_id, links)
        self.events.emit("mission.task_linked", "mission", asdict(link))
        return link

    def unlink_task(self, mission_id: str, task_id: str) -> MissionDelegationLink:
        self.get_mission(mission_id)
        links = self._read_links(mission_id)
        removed = next((link for link in links if link.task_id == task_id), None)
        if not removed:
            raise NotFound(f"Mission task link not found: {mission_id}/{task_id}")
        self._write_links(mission_id, [link for link in links if link.task_id != task_id])
        self.events.emit("mission.task_unlinked", "mission", asdict(removed))
        return removed

    def list_mission_tasks(self, mission_id: str) -> list[MissionDelegationLink]:
        self.get_mission(mission_id)
        return self._read_links(mission_id)

    def summarize_mission(self, mission_id: str) -> MissionSummary:
        links = self.list_mission_tasks(mission_id)
        tasks = []
        if self.delegation:
            for link in links:
                try:
                    tasks.append(self.delegation.get_task(link.task_id))
                except NotFound:
                    continue
        pending = len([task for task in tasks if task.status == "pending"])
        running = len([task for task in tasks if task.status in {"accepted", "in_progress"}])
        completed = len([task for task in tasks if task.status == "completed"])
        failed = len([task for task in tasks if task.status == "failed"])
        cancelled = len([task for task in tasks if task.status == "cancelled"])
        dlq = len(
            [
                task
                for task in tasks
                if self.dead_letter and self.dead_letter.is_task_open(task.task_id)
            ]
        )
        return MissionSummary(
            mission_id=mission_id,
            total_tasks=len(links),
            pending_tasks=pending,
            running_tasks=running,
            completed_tasks=completed,
            failed_tasks=failed,
            cancelled_tasks=cancelled,
            dlq_tasks=dlq,
        )

    def active_missions_count(self) -> int:
        return len(self.list_missions(status="active"))

    def failed_missions_count(self) -> int:
        return len(self.list_missions(status="failed"))

    def _mission_path(self, mission_id: str) -> Path:
        return self.data_dir.resolve(f"missions/{mission_id}.yaml")

    def _links_path(self, mission_id: str) -> Path:
        return self.data_dir.resolve(f"missions/{mission_id}.delegations.yaml")

    def _write_mission(self, mission: Mission) -> None:
        dump_structured_file(self._mission_path(mission.mission_id), asdict(mission))

    def _write_links(self, mission_id: str, links: list[MissionDelegationLink]) -> None:
        dump_structured_file(
            self._links_path(mission_id),
            {"mission_id": mission_id, "links": [asdict(link) for link in links]},
        )

    def _read_links(self, mission_id: str) -> list[MissionDelegationLink]:
        path = self._links_path(mission_id)
        if not path.exists():
            return []
        raw = load_structured_file(path)
        links = raw.get("links", [])
        if not isinstance(links, list):
            raise ValidationError(f"Invalid mission delegation links: {mission_id}")
        return [MissionDelegationLink(**link) for link in links]

    @staticmethod
    def _read_mission(path: Path) -> Mission:
        raw = load_structured_file(path)
        raw.setdefault("description", "")
        raw.setdefault("objective", raw.get("description") or raw.get("title", ""))
        raw.setdefault("status", "draft")
        raw.setdefault("priority", "normal")
        raw.setdefault("owner_agent_id", None)
        raw.setdefault("created_by", None)
        raw.setdefault("conversation_id", None)
        raw.setdefault("metadata", {})
        raw.setdefault("requester", raw.get("created_by"))
        raw.setdefault("plan_id", None)
        raw.setdefault("progress", 0.0)
        raw.setdefault("started_at", None)
        raw.setdefault("completed_at", None)
        raw.setdefault("paused_at", None)
        raw.setdefault("cancelled_at", None)
        raw.setdefault("deadline", None)
        raw.setdefault("revision", 1)
        raw.setdefault("updated_at", raw.get("created_at", datetime.now(UTC).isoformat()))
        raw.setdefault("project_id", None)
        raw.setdefault("rfc_id", None)
        raw.setdefault("rfc_revision", None)
        raw.setdefault("rfc_checksum", None)
        raw.setdefault("implementation_plan_id", None)
        raw.setdefault("implementation_plan_revision", None)
        raw.setdefault("implementation_plan_checksum", None)
        return Mission(**raw)

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in MISSION_STATUSES:
            raise ValidationError(f"Invalid mission status: {status}")

    @staticmethod
    def _validate_priority(priority: str) -> None:
        if priority not in MISSION_PRIORITIES:
            raise ValidationError(f"Invalid mission priority: {priority}")
