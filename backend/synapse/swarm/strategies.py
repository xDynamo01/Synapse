from __future__ import annotations

from typing import Any, Protocol

from synapse.missions.errors import SwarmInvalidStrategy
from synapse.missions.models import ConsolidatedResult, MissionPlan, SwarmDescriptor


class SwarmStrategyRuntime(Protocol):
    def validate(self, swarm: SwarmDescriptor, plan: MissionPlan) -> None: ...
    def prepare(self, swarm: SwarmDescriptor, plan: MissionPlan) -> dict[str, Any]: ...
    def dispatch(self, swarm: SwarmDescriptor, plan: MissionPlan, missions: Any) -> Any: ...
    def collect(self, swarm: SwarmDescriptor, plan: MissionPlan) -> list[dict[str, Any]]: ...
    def evaluate(self, swarm: SwarmDescriptor, outputs: list[dict[str, Any]]) -> dict[str, Any]: ...
    def finalize(
        self, swarm: SwarmDescriptor, outputs: list[dict[str, Any]], evaluation: dict[str, Any]
    ) -> ConsolidatedResult: ...


class BaseStrategy:
    name = "base"

    def validate(self, swarm: SwarmDescriptor, plan: MissionPlan) -> None:
        if not plan.tasks:
            raise SwarmInvalidStrategy("Swarm mission plan is empty.")
        if not swarm.member_agent_ids:
            raise SwarmInvalidStrategy("Swarm requires at least one member.")

    def prepare(self, swarm: SwarmDescriptor, plan: MissionPlan) -> dict[str, Any]:
        return {
            "swarm_id": swarm.swarm_id,
            "plan_id": plan.plan_id,
            "task_ids": [task.task_id for task in plan.tasks],
        }

    def dispatch(self, swarm: SwarmDescriptor, plan: MissionPlan, missions: Any) -> Any:
        missions.dispatch_ready_tasks(
            swarm.mission_id,
            int(swarm.metadata.get("max_parallelism", 1)),
            execute=True,
        )
        return missions.refresh_progress(swarm.mission_id)

    def collect(self, swarm: SwarmDescriptor, plan: MissionPlan) -> list[dict[str, Any]]:
        return [
            {
                "task_id": task.task_id,
                "agent_id": task.assigned_agent_id,
                "result": task.result,
                "status": task.status,
            }
            for task in plan.tasks
            if task.status == "completed" and task.result is not None
        ]

    def evaluate(self, swarm: SwarmDescriptor, outputs: list[dict[str, Any]]) -> dict[str, Any]:
        return {"complete": bool(outputs), "output_count": len(outputs)}

    def finalize(
        self, swarm: SwarmDescriptor, outputs: list[dict[str, Any]], evaluation: dict[str, Any]
    ) -> ConsolidatedResult:
        return ConsolidatedResult(
            mission_id=swarm.mission_id,
            swarm_id=swarm.swarm_id,
            strategy=self.name,
            outputs=outputs,
            verification=evaluation,
            provenance=[
                {"task_id": item["task_id"], "agent_id": item["agent_id"]} for item in outputs
            ],
            final_output={
                item["task_id"]: item["result"]
                for item in sorted(outputs, key=lambda value: value["task_id"])
            },
        )


class LeaderWorkerStrategy(BaseStrategy):
    name = "leader_worker"

    def validate(self, swarm: SwarmDescriptor, plan: MissionPlan) -> None:
        super().validate(swarm, plan)
        if not swarm.leader_agent_id:
            raise SwarmInvalidStrategy("Leader-worker strategy requires a leader.")
        if swarm.leader_agent_id in swarm.member_agent_ids:
            raise SwarmInvalidStrategy("Leader must not also be a worker member.")


class ParallelStrategy(BaseStrategy):
    name = "parallel"

    def validate(self, swarm: SwarmDescriptor, plan: MissionPlan) -> None:
        super().validate(swarm, plan)
        roots = [task for task in plan.tasks if not task.dependencies]
        limit = int(swarm.metadata.get("max_parallelism", len(swarm.member_agent_ids)))
        if limit < 1:
            raise SwarmInvalidStrategy("Parallel max_parallelism must be positive.")
        if len(roots) > len(swarm.member_agent_ids) and not swarm.metadata.get(
            "allow_worker_reuse", False
        ):
            raise SwarmInvalidStrategy("Parallel strategy has more ready tasks than members.")


class PipelineStrategy(BaseStrategy):
    name = "pipeline"

    def validate(self, swarm: SwarmDescriptor, plan: MissionPlan) -> None:
        super().validate(swarm, plan)
        ordered = plan.tasks
        if len(ordered) < 2:
            raise SwarmInvalidStrategy("Pipeline requires at least two tasks.")
        for index, task in enumerate(ordered[1:], start=1):
            if ordered[index - 1].task_id not in task.dependencies:
                raise SwarmInvalidStrategy("Pipeline tasks must form an explicit dependency chain.")

    def collect(self, swarm: SwarmDescriptor, plan: MissionPlan) -> list[dict[str, Any]]:
        outputs = super().collect(swarm, plan)
        positions = {task.task_id: index for index, task in enumerate(plan.tasks)}
        return sorted(outputs, key=lambda item: positions[item["task_id"]])


class ReviewLoopStrategy(BaseStrategy):
    name = "review_loop"

    def validate(self, swarm: SwarmDescriptor, plan: MissionPlan) -> None:
        super().validate(swarm, plan)
        maximum = int(swarm.metadata.get("max_iterations", 0))
        if maximum < 1:
            raise SwarmInvalidStrategy("Review-loop requires a positive max_iterations.")
        if len(swarm.member_agent_ids) < 2:
            raise SwarmInvalidStrategy("Review-loop requires producer and reviewer members.")

    def evaluate(self, swarm: SwarmDescriptor, outputs: list[dict[str, Any]]) -> dict[str, Any]:
        reviews = [
            review
            for item in outputs
            if (review := self._review(item.get("result", {}))) is not None
        ]
        approved = any(review.get("approved") for review in reviews)
        return {
            "complete": approved,
            "approved": approved,
            "iterations": len(reviews),
            "max_iterations": int(swarm.metadata["max_iterations"]),
            "feedback": reviews,
        }

    @staticmethod
    def _review(result: dict[str, Any]) -> dict[str, Any] | None:
        for candidate in (
            result.get("review"),
            result.get("structured_output", {}).get("review"),
            result.get("output", {}).get("review")
            if isinstance(result.get("output"), dict)
            else None,
        ):
            if isinstance(candidate, dict):
                return candidate
        return None


STRATEGIES: dict[str, BaseStrategy] = {
    strategy.name: strategy
    for strategy in (
        LeaderWorkerStrategy(),
        ParallelStrategy(),
        PipelineStrategy(),
        ReviewLoopStrategy(),
    )
}
