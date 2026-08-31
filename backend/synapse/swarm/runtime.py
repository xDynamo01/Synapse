from __future__ import annotations

import builtins
from dataclasses import asdict, replace
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.missions.errors import SwarmInvalidStrategy, SwarmNotFound
from synapse.missions.models import SwarmDescriptor, SwarmStrategy, now_iso
from synapse.swarm.strategies import STRATEGIES


class SwarmRuntime:
    STRATEGIES = {item.value for item in SwarmStrategy}

    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        missions: Any,
        workers: Any,
        ephemeral_agents: Any | None = None,
        workforce_planner: Any | None = None,
    ):
        self.data_dir = data_dir
        self.events = events
        self.missions = missions
        self.workers = workers
        self.ephemeral_agents = ephemeral_agents
        self.workforce_planner = workforce_planner

    def create(
        self,
        mission_id: str,
        strategy: str,
        leader_agent_id: str | None,
        member_agent_ids: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> SwarmDescriptor:
        self.missions.get_mission(mission_id)
        if strategy not in self.STRATEGIES:
            raise SwarmInvalidStrategy(f"Unsupported swarm strategy: {strategy}")
        swarm = SwarmDescriptor(
            mission_id,
            strategy,
            leader_agent_id,
            sorted(set(member_agent_ids)),
            metadata=metadata or {},
        )
        self._write(swarm)
        self.events.emit("swarm.created", leader_agent_id or "swarm", asdict(swarm))
        return swarm

    def get(self, swarm_id: str) -> SwarmDescriptor:
        path = self.data_dir.resolve(f"swarms/{swarm_id}.yaml")
        if not path.exists():
            raise SwarmNotFound(f"Swarm not found: {swarm_id}")
        return SwarmDescriptor(**load_structured_file(path))

    def list(self, mission_id: str | None = None) -> list[SwarmDescriptor]:
        items = [
            SwarmDescriptor(**load_structured_file(path))
            for path in self.data_dir.resolve("swarms").glob("*.yaml")
        ]
        return sorted(
            (item for item in items if mission_id is None or item.mission_id == mission_id),
            key=lambda item: item.swarm_id,
        )

    def get_result(self, swarm_id: str) -> dict[str, Any]:
        self.get(swarm_id)
        path = self.data_dir.resolve(f"swarms/{swarm_id}.result.yaml")
        if not path.exists():
            raise SwarmNotFound(f"Swarm result not found: {swarm_id}")
        return load_structured_file(path)

    def get_workforce_plan(self, swarm_id: str) -> Any:
        swarm = self.get(swarm_id)
        if not self.workforce_planner:
            raise SwarmInvalidStrategy("Dynamic workforce planning is unavailable.")
        mission = self.missions.get_mission(swarm.mission_id)
        if not mission.plan_id:
            raise SwarmInvalidStrategy("Swarm mission requires an active plan.")
        plan = self.missions.planner.get_plan(swarm.mission_id, mission.plan_id)
        parent = swarm.leader_agent_id or mission.owner_agent_id
        if not parent:
            raise SwarmInvalidStrategy("Dynamic workforce requires a persistent parent agent.")
        return self.workforce_planner.plan(
            mission, plan, parent_agent_id=parent, strategy=swarm.strategy
        )

    def provision_workforce(self, swarm_id: str) -> builtins.list[Any]:
        workforce = self.get_workforce_plan(swarm_id)
        if workforce.approval_required:
            raise SwarmInvalidStrategy("Dynamic workforce requires approval before provisioning.")
        if not workforce.required:
            return []
        if self.ephemeral_agents is None:
            raise SwarmInvalidStrategy("Ephemeral agent runtime is unavailable.")
        ephemeral_agents = self.ephemeral_agents
        instances = [
            ephemeral_agents.create_instance(spec, authority="swarm")
            for spec in workforce.agents
        ]
        available = [
            worker
            for worker in self.workers.list()
            if worker.status in {"idle", "online"} and worker.workload == 0
        ]
        for instance, worker in zip(instances, available, strict=False):
            ephemeral_agents.assign_worker(instance.ephemeral_agent_id, worker.worker_id)
        swarm = self.get(swarm_id)
        self._write(
            replace(
                swarm,
                member_agent_ids=sorted(
                    {*swarm.member_agent_ids, *(item.ephemeral_agent_id for item in instances)}
                ),
                metadata={
                    **swarm.metadata,
                    "ephemeral_workforce": [item.ephemeral_agent_id for item in instances],
                },
            )
        )
        mission = self.missions.get_mission(swarm.mission_id)
        if mission.plan_id:
            mission_plan = self.missions.planner.get_plan(swarm.mission_id, mission.plan_id)
            by_task = {item.task_id: item.ephemeral_agent_id for item in instances}
            tasks = [
                replace(
                    task,
                    metadata={**task.metadata, "ephemeral_agent_id": by_task[task.task_id]},
                )
                if task.task_id in by_task
                else task
                for task in mission_plan.tasks
            ]
            self.missions.planner.save_plan(
                replace(
                    mission_plan,
                    tasks=tasks,
                    dependencies={task.task_id: task.dependencies for task in tasks},
                )
            )
        return [ephemeral_agents.get(item.ephemeral_agent_id) for item in instances]

    def start(self, swarm_id: str) -> SwarmDescriptor:
        swarm = self._transition(swarm_id, "running")
        self.events.emit("swarm.started", swarm.leader_agent_id or "swarm", asdict(swarm))
        return swarm

    def pause(self, swarm_id: str) -> SwarmDescriptor:
        return self._transition(swarm_id, "paused")

    def resume(self, swarm_id: str) -> SwarmDescriptor:
        return self._transition(swarm_id, "running")

    def cancel(self, swarm_id: str) -> SwarmDescriptor:
        swarm = self._transition(swarm_id, "cancelled")
        self.events.emit("swarm.cancelled", swarm.leader_agent_id or "swarm", asdict(swarm))
        return swarm

    def run(self, swarm_id: str) -> dict[str, Any]:
        swarm = self.start(swarm_id)
        mission_record = self.missions.get_mission(swarm.mission_id)
        if not mission_record.plan_id:
            raise SwarmInvalidStrategy("Swarm mission requires an active plan.")
        plan = self.missions.planner.get_plan(swarm.mission_id, mission_record.plan_id)
        strategy = STRATEGIES[swarm.strategy]
        strategy.validate(swarm, plan)
        prepared = strategy.prepare(swarm, plan)
        self.events.emit("swarm.prepared", swarm.leader_agent_id or "swarm", prepared)
        mission = strategy.dispatch(swarm, plan, self.missions)
        current_plan = self.missions.planner.get_plan(swarm.mission_id, mission_record.plan_id)
        outputs = strategy.collect(swarm, current_plan)
        evaluation = strategy.evaluate(swarm, outputs)
        consolidated = strategy.finalize(swarm, outputs, evaluation)
        dump_structured_file(
            self.data_dir.resolve(f"swarms/{swarm_id}.result.yaml"), asdict(consolidated)
        )
        status = "completed" if mission.status == "completed" else mission.status
        if (
            swarm.strategy == SwarmStrategy.REVIEW_LOOP
            and mission.status == "completed"
            and evaluation.get("feedback")
            and not evaluation.get("approved")
        ):
            status = self._continue_review_loop(swarm, mission_record, current_plan, evaluation)
        self._transition(swarm_id, status)
        self.events.emit(
            f"swarm.{status}",
            swarm.leader_agent_id or "swarm",
            {"swarm_id": swarm_id, "mission_id": swarm.mission_id},
        )
        return {
            "swarm_id": swarm_id,
            "mission_id": swarm.mission_id,
            "status": status,
            "strategy": swarm.strategy,
            "result": asdict(consolidated),
        }

    def _continue_review_loop(
        self, swarm: SwarmDescriptor, mission: Any, plan: Any, evaluation: dict[str, Any]
    ) -> str:
        iteration = int(swarm.metadata.get("current_iteration", 1))
        maximum = int(swarm.metadata["max_iterations"])
        history = [
            *swarm.metadata.get("review_history", []),
            {"iteration": iteration, "feedback": evaluation.get("feedback", [])},
        ]
        if iteration >= maximum:
            self.missions._persist(
                replace(
                    mission,
                    status="failed",
                    completed_at=now_iso(),
                    revision=mission.revision + 1,
                    updated_at=now_iso(),
                ),
                "mission.failed",
            )
            self._write(replace(swarm, metadata={**swarm.metadata, "review_history": history}))
            return "failed"
        producer = next(
            (task for task in plan.tasks if task.metadata.get("producer")), plan.tasks[0]
        )
        reviewer = next(
            (task for task in plan.tasks if task.metadata.get("reviewer")), plan.tasks[-1]
        )
        tasks = list(plan.tasks)
        producer_index = next(
            index for index, task in enumerate(tasks) if task.task_id == producer.task_id
        )
        reviewer_index = next(
            index for index, task in enumerate(tasks) if task.task_id == reviewer.task_id
        )
        tasks[producer_index] = replace(
            producer,
            status="pending",
            result=None,
            assigned_agent_id=None,
            assigned_worker_id=None,
            metadata={
                **producer.metadata,
                "review_feedback": evaluation.get("feedback", []),
                "previous_revision": producer.revision,
            },
            revision=producer.revision + 1,
            updated_at=now_iso(),
        )
        tasks[reviewer_index] = replace(
            reviewer,
            status="pending",
            result=None,
            assigned_agent_id=None,
            assigned_worker_id=None,
            revision=reviewer.revision + 1,
            updated_at=now_iso(),
        )
        self.missions.planner.save_plan(
            replace(
                plan, tasks=tasks, dependencies={task.task_id: task.dependencies for task in tasks}
            )
        )
        current_mission = self.missions.get_mission(mission.mission_id)
        self.missions._persist(
            replace(
                current_mission,
                status="running",
                progress=0.0,
                completed_at=None,
                revision=current_mission.revision + 1,
                updated_at=now_iso(),
            ),
            "mission.progress",
        )
        self._write(
            replace(
                swarm,
                status="running",
                metadata={
                    **swarm.metadata,
                    "current_iteration": iteration + 1,
                    "review_history": history,
                },
            )
        )
        return "running"

    def _transition(self, swarm_id: str, status: str) -> SwarmDescriptor:
        current = self.get(swarm_id)
        if current.status == status:
            return current
        updated = replace(current, status=status)
        self._write(updated)
        return updated

    def _write(self, swarm: SwarmDescriptor) -> None:
        dump_structured_file(self.data_dir.resolve(f"swarms/{swarm.swarm_id}.yaml"), asdict(swarm))
