from __future__ import annotations

from dataclasses import dataclass, field

from synapse.missions.errors import NoWorkerAvailable
from synapse.missions.models import MissionTask, WorkerDescriptor
from synapse.workers.registry import WorkerRegistry


@dataclass(frozen=True)
class RejectedCandidate:
    worker_id: str
    reasons: list[str]


@dataclass(frozen=True)
class SelectionResult:
    selected_worker: str
    selected_agent: str
    reason: str
    candidates_considered: list[str]
    rejected_candidates: list[RejectedCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fallback_applied: bool = False


class WorkerScheduler:
    def __init__(self, registry: WorkerRegistry):
        self.registry = registry

    def select_worker(
        self,
        task: MissionTask,
        candidates: list[WorkerDescriptor] | None = None,
        scheduling_context: dict[str, object] | None = None,
    ) -> SelectionResult:
        candidates = candidates if candidates is not None else self.registry.list()
        rejected: list[RejectedCandidate] = []
        eligible: list[WorkerDescriptor] = []
        for worker in sorted(candidates, key=lambda item: item.worker_id):
            reasons: list[str] = []
            if worker.status not in {"idle", "sleeping"}:
                reasons.append(f"status:{worker.status}")
            if not set(task.required_capabilities) <= set(worker.capabilities):
                reasons.append("capability_mismatch")
            if not set(task.required_tools) <= set(worker.tools):
                reasons.append("tool_mismatch")
            if not set(task.required_permissions) <= set(worker.permissions):
                reasons.append("permission_mismatch")
            if reasons:
                rejected.append(RejectedCandidate(worker.worker_id, reasons))
            else:
                eligible.append(worker)
        if not eligible:
            raise NoWorkerAvailable(f"No worker available for task {task.task_id}")
        preferred_agent = str((scheduling_context or {}).get("preferred_agent_id") or "")
        selected = min(
            eligible,
            key=lambda item: (
                item.agent_id != preferred_agent,
                item.workload,
                item.failure_count,
                item.worker_id,
            ),
        )
        return SelectionResult(
            selected_worker=selected.worker_id,
            selected_agent=selected.agent_id,
            reason="lowest workload and failure count among compatible available workers",
            candidates_considered=[
                item.worker_id for item in sorted(candidates, key=lambda item: item.worker_id)
            ],
            rejected_candidates=rejected,
        )
