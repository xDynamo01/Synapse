from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, runtime_from
from synapse.core.exceptions import ValidationError

router = APIRouter()


class DelegationCreatePayload(BaseModel):
    title: str
    description: str = ""
    requester_agent_id: str
    assignee_agent_id: str
    priority: str = "normal"
    conversation_id: str | None = None
    mission_id: str | None = None
    due_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DelegationTransitionPayload(BaseModel):
    reason: str | None = None
    result: str | None = None


class DelegationCompletionPayload(BaseModel):
    status: str
    summary: str
    result: str | None = None
    failure_reason: str | None = None
    needs_followup: bool = False
    followup_message: str | None = None
    created_by_agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DelegationAutonomyCheckPayload(BaseModel):
    action: str


class DelegationTimeoutScanPayload(BaseModel):
    dry_run: bool = True


class DeadLetterCreatePayload(BaseModel):
    task_id: str
    reason: str = "manual_move"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionCreatePayload(BaseModel):
    title: str
    objective: str | None = None
    description: str = ""
    status: str = "draft"
    priority: str = "normal"
    owner_agent_id: str | None = None
    created_by: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None
    rfc_id: str | None = None
    rfc_revision: int | None = None
    rfc_checksum: str | None = None
    implementation_plan_id: str | None = None
    implementation_plan_revision: int | None = None
    implementation_plan_checksum: str | None = None
    information_classification: str = "internal"
    information_categories: list[str] = Field(default_factory=list)
    allowed_processing_boundaries: list[str] = Field(default_factory=list)
    allowed_provider_profiles: list[str] = Field(default_factory=list)
    external_processing_policy: str = "policy-controlled"
    training_use_policy: str = "prohibited"


class MissionPlanPayload(BaseModel):
    objective: str | None = None
    tasks: list[dict[str, Any]]
    constraints: dict[str, Any] = Field(default_factory=dict)
    preferred_agents: list[str] = Field(default_factory=list)


class MissionUpdatePayload(BaseModel):
    expected_revision: int
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    metadata: dict[str, Any] | None = None


class WorkerRegisterPayload(BaseModel):
    worker_id: str
    agent_id: str
    status: str = "offline"
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    role: str | None = None


class SwarmCreatePayload(BaseModel):
    mission_id: str
    strategy: str
    leader_agent_id: str | None = None
    member_agent_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimeoutScanPayload(BaseModel):
    stale_after_seconds: int = 120


class WorkerWorkloadPayload(BaseModel):
    workload: float
    task_id: str | None = None
    attempt_id: str | None = None


class MissionTaskUpdatePayload(BaseModel):
    expected_revision: int
    metadata: dict[str, Any] | None = None
    dependencies: list[str] | None = None


class MissionTaskAssignPayload(BaseModel):
    worker_id: str
    expected_revision: int


class RecoveryApplyPayload(BaseModel):
    action: str
    options: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class MissionTaskLinkPayload(BaseModel):
    task_id: str


@router.get("/recovery/summary")
def recovery_summary(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.delegation_recovery.summarize_recovery_state()
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/recovery/open")
def recovery_open(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [
            asdict(decision) for decision in runtime.delegation_recovery.evaluate_all_open_tasks()
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/recovery/{task_id}")
def recovery_decision(task_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_recovery.explain_decision(task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-supervision")
def mission_supervision(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_supervision.build_summary())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-attention")
def mission_attention(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.mission_supervision.list_attention_items()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions")
def list_missions(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(mission) for mission in runtime.missions.list_missions(status=status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions")
def create_mission(payload: MissionCreatePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.missions.create_mission(
                title=payload.title,
                objective=payload.objective,
                description=payload.description,
                status=payload.status,
                priority=payload.priority,
                owner_agent_id=payload.owner_agent_id,
                created_by=payload.created_by,
                conversation_id=payload.conversation_id,
                metadata=payload.metadata,
                project_id=payload.project_id,
                rfc_id=payload.rfc_id,
                rfc_revision=payload.rfc_revision,
                rfc_checksum=payload.rfc_checksum,
                implementation_plan_id=payload.implementation_plan_id,
                implementation_plan_revision=payload.implementation_plan_revision,
                implementation_plan_checksum=payload.implementation_plan_checksum,
                information_classification=payload.information_classification,
                information_categories=tuple(payload.information_categories),
                allowed_processing_boundaries=tuple(payload.allowed_processing_boundaries),
                allowed_provider_profiles=tuple(payload.allowed_provider_profiles),
                external_processing_policy=payload.external_processing_policy,
                training_use_policy=payload.training_use_policy,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}")
def get_mission(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.missions.get_mission(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/missions/{mission_id}")
def update_mission_record(
    mission_id: str,
    payload: MissionUpdatePayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.missions.update_mission(
                mission_id,
                title=payload.title,
                description=payload.description,
                status=payload.status,
                priority=payload.priority,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/plan")
def plan_mission(mission_id: str, payload: MissionPlanPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        mission = runtime.missions.get_mission(mission_id)
        plan = runtime.planner.create_plan(
            mission_id,
            payload.objective or mission.objective,
            constraints=payload.constraints,
            preferred_agents=payload.preferred_agents,
            tasks=payload.tasks,
        )
        runtime.missions.attach_plan(mission_id, plan.plan_id)
        return asdict(plan)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/validate-plan")
def validate_mission_plan(
    mission_id: str,
    payload: MissionPlanPayload,
    request: Request,
) -> dict[str, Any]:
    from synapse.missions.models import MissionPlan, MissionTask

    runtime = runtime_from(request)
    try:
        runtime.missions.get_mission(mission_id)
        tasks = [MissionTask(mission_id=mission_id, **item) for item in payload.tasks]
        return asdict(runtime.planner.validate_plan(MissionPlan(mission_id, tasks)))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/start")
def start_mission(mission_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).missions.run_mission(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/dispatch")
def dispatch_mission(
    mission_id: str,
    request: Request,
    max_concurrency: int | None = None,
    execute: bool = True,
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).missions.dispatch_ready_tasks(
                mission_id,
                max_concurrency,
                execute=execute,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/pause")
def pause_mission(mission_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).missions.pause(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/resume")
def resume_mission(mission_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).missions.resume(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/cancel")
def cancel_mission(mission_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).missions.cancel(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/workers")
def list_workers(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    return [asdict(worker) for worker in runtime_from(request).worker_registry.list(status)]


@router.post("/workers")
def register_worker(payload: WorkerRegisterPayload, request: Request) -> dict[str, Any]:
    from synapse.missions.models import WorkerDescriptor

    try:
        return asdict(
            runtime_from(request).worker_registry.register(WorkerDescriptor(**payload.model_dump()))
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/workers/{worker_id}/heartbeat")
def heartbeat_worker(worker_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).worker_registry.heartbeat(worker_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/workers/{worker_id}")
def get_worker(worker_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).worker_registry.get(worker_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/workers/{worker_id}/disable")
def disable_worker(worker_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).worker_registry.disable(worker_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/workers/{worker_id}/workload")
def update_worker_workload(
    worker_id: str,
    payload: WorkerWorkloadPayload,
    request: Request,
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).worker_registry.set_workload(
                worker_id,
                payload.workload,
                payload.task_id,
                payload.attempt_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/workers/stale-scan")
def stale_worker_scan(request: Request, stale_after_seconds: int = 120) -> list[dict[str, Any]]:
    try:
        return [
            asdict(item)
            for item in runtime_from(request).worker_registry.expire_stale(stale_after_seconds)
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/workers/{worker_id}/attempts")
def worker_attempts(worker_id: str, request: Request) -> list[dict[str, Any]]:
    return [
        asdict(item)
        for item in runtime_from(request).attempts.list()
        if item.worker_id == worker_id
    ]


@router.post("/swarms")
def create_swarm(payload: SwarmCreatePayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).swarm.create(**payload.model_dump()))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/swarms")
def list_swarms(request: Request, mission_id: str | None = None) -> list[dict[str, Any]]:
    return [asdict(swarm) for swarm in runtime_from(request).swarm.list(mission_id)]


@router.get("/swarms/{swarm_id}")
def get_swarm(swarm_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).swarm.get(swarm_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/swarms/{swarm_id}/start")
def start_swarm(swarm_id: str, request: Request) -> dict[str, Any]:
    try:
        return runtime_from(request).swarm.run(swarm_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/swarms/{swarm_id}/pause")
def pause_swarm(swarm_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).swarm.pause(swarm_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/swarms/{swarm_id}/resume")
def resume_swarm(swarm_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).swarm.resume(swarm_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/swarms/{swarm_id}/cancel")
def cancel_swarm(swarm_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).swarm.cancel(swarm_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/swarms/{swarm_id}/members")
def swarm_members(swarm_id: str, request: Request) -> dict[str, Any]:
    swarm = runtime_from(request).swarm.get(swarm_id)
    return {"leader_agent_id": swarm.leader_agent_id, "member_agent_ids": swarm.member_agent_ids}


@router.get("/swarms/{swarm_id}/result")
def swarm_result(swarm_id: str, request: Request) -> dict[str, Any]:
    try:
        return runtime_from(request).swarm.get_result(swarm_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/swarms/{swarm_id}/trace")
def swarm_trace(swarm_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    swarm = runtime.swarm.get(swarm_id)
    return {
        "swarm_id": swarm_id,
        "events": [
            asdict(item)
            for item in runtime.mission_trace.list(swarm.mission_id, limit=500)
            if item.swarm_id in {None, swarm_id}
        ],
    }


@router.get("/missions/{mission_id}/attempts")
def list_mission_attempts(mission_id: str, request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).attempts.list(mission_id=mission_id)]


@router.get("/missions/{mission_id}/progress")
def mission_progress(mission_id: str, request: Request) -> dict[str, Any]:
    mission = runtime_from(request).missions.refresh_progress(mission_id)
    return {"mission_id": mission_id, "progress": mission.progress, "status": mission.status}


@router.get("/missions/{mission_id}/result")
def mission_result(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    mission = runtime.missions.get_mission(mission_id)
    tasks = runtime.missions.list_tasks(mission_id) if mission.plan_id else []
    return {
        "mission_id": mission_id,
        "status": mission.status,
        "progress": mission.progress,
        "results": [
            {"task_id": task.task_id, "result": task.result}
            for task in tasks
            if task.result is not None
        ],
    }


@router.get("/missions/{mission_id}/recovery-history")
def mission_recovery_history(mission_id: str, request: Request) -> list[dict[str, Any]]:
    return [
        asdict(item)
        for item in runtime_from(request).attempts.list(mission_id=mission_id)
        if item.recovery_action or item.status in {"recovery_pending", "dead_lettered"}
    ]


@router.get("/missions/{mission_id}/trace")
def mission_trace(
    mission_id: str,
    request: Request,
    event_type: str | None = None,
    task_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {
        "summary": runtime.mission_trace.summarize(mission_id),
        "events": [
            asdict(item)
            for item in runtime.mission_trace.list(
                mission_id, event_type=event_type, task_id=task_id, offset=offset, limit=limit
            )
        ],
    }


@router.get("/attempts/{attempt_id}")
def get_attempt(attempt_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).attempts.get(attempt_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/attempts/{attempt_id}/execute")
def execute_attempt(attempt_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).worker_execution.execute_attempt(attempt_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/attempts/{attempt_id}/recovery")
def evaluate_attempt_recovery(attempt_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).mission_recovery.evaluate(attempt_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/attempts/{attempt_id}/retry")
def retry_attempt(attempt_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).mission_recovery.schedule_retry(attempt_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/timeout-scan")
def scan_mission_timeouts(payload: TimeoutScanPayload, request: Request) -> dict[str, Any]:
    try:
        return runtime_from(request).mission_recovery.scan_timeouts(
            stale_after_seconds=payload.stale_after_seconds
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/tasks")
def link_mission_task(
    mission_id: str,
    payload: MissionTaskLinkPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.missions.link_task(mission_id, payload.task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/tasks")
def list_mission_tasks(mission_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        mission = runtime.missions.get_mission(mission_id)
        if mission.plan_id:
            return [asdict(task) for task in runtime.missions.list_tasks(mission_id)]
        return [asdict(link) for link in runtime.missions.list_mission_tasks(mission_id)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/tasks/{task_id}")
def get_plan_task(mission_id: str, task_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).missions.get_task(mission_id, task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/missions/{mission_id}/tasks/{task_id}")
def update_plan_task(
    mission_id: str,
    task_id: str,
    payload: MissionTaskUpdatePayload,
    request: Request,
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).missions.update_task(
                mission_id,
                task_id,
                metadata=payload.metadata,
                dependencies=payload.dependencies,
                expected_revision=payload.expected_revision,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/tasks/{task_id}/assign")
def assign_plan_task(
    mission_id: str,
    task_id: str,
    payload: MissionTaskAssignPayload,
    request: Request,
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).missions.assign_task(
                mission_id,
                task_id,
                payload.worker_id,
                expected_revision=payload.expected_revision,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/tasks/{task_id}/reassign")
def reassign_plan_task(
    mission_id: str,
    task_id: str,
    payload: MissionTaskAssignPayload,
    request: Request,
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).missions.assign_task(
                mission_id,
                task_id,
                payload.worker_id,
                expected_revision=payload.expected_revision,
                reassign=True,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/tasks/{task_id}/cancel")
def cancel_plan_task(
    mission_id: str,
    task_id: str,
    payload: MissionTaskUpdatePayload,
    request: Request,
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).missions.cancel_task(
                mission_id,
                task_id,
                expected_revision=payload.expected_revision,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/missions/{mission_id}/tasks/{task_id}/verify")
def verify_plan_task(mission_id: str, task_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).missions.verify_task(mission_id, task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/tasks/{task_id}/attempts")
def plan_task_attempts(mission_id: str, task_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    runtime.missions.get_task(mission_id, task_id)
    return [asdict(item) for item in runtime.attempts.list(mission_id=mission_id, task_id=task_id)]


@router.get("/missions/{mission_id}/tasks/{task_id}/result")
def plan_task_result(mission_id: str, task_id: str, request: Request) -> dict[str, Any]:
    task = runtime_from(request).missions.get_task(mission_id, task_id)
    return {"task_id": task_id, "result": task.result, "error": task.error}


@router.post("/attempts/{attempt_id}/recovery/apply")
def apply_attempt_recovery(
    attempt_id: str,
    payload: RecoveryApplyPayload,
    request: Request,
) -> dict[str, Any]:
    try:
        result = runtime_from(request).mission_recovery.apply(
            attempt_id,
            payload.action,
            options=payload.options,
            idempotency_key=payload.idempotency_key,
        )
        return asdict(result) if hasattr(result, "__dataclass_fields__") else result
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/summary")
def mission_summary(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.missions.summarize_mission(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/context")
def mission_context(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_context.build_context(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/health")
def mission_health(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return {"health": runtime.mission_context.mission_health(mission_id)}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/recovery")
def mission_recovery(mission_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [
            asdict(decision)
            for decision in runtime.mission_context.list_mission_recovery_candidates(mission_id)
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/status")
def mission_status(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_supervision.mission_status(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-control/overview")
def mission_control_overview(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_control.get_overview())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-control/operations")
def mission_control_operations(request: Request) -> dict[str, Any]:
    try:
        return runtime_from(request).mission_control.operational_snapshot()
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-control/missions/{mission_id}")
def mission_control_card(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_control.get_mission_card(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-control/attention")
def mission_control_attention(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_control.get_attention_panel())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-control/work-queue")
def mission_control_work_queue(request: Request, agent_id: str | None = None) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_control.get_work_queue(agent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mission-control/agents/workload")
def mission_control_agent_workload(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mission_control.get_agent_workload())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegations")
def list_delegations(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(task) for task in runtime.delegation.list_tasks(status=status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegations/{task_id}")
def get_delegation(task_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation.get_task(task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegations/{task_id}/executions")
def list_delegation_executions(task_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [
            asdict(execution)
            for execution in runtime.delegation_execution.list_task_executions(task_id)
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-executions/{execution_id}")
def get_delegation_execution(execution_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_execution.get_execution(execution_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-inbox/{agent_id}")
def get_delegation_inbox(agent_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(entry) for entry in runtime.delegation_inbox.get_agent_inbox(agent_id)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-inbox/{agent_id}/summary")
def get_delegation_inbox_summary(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_inbox.get_inbox_summary(agent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-scheduling-policy")
def get_delegation_scheduling_policy(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_scheduling.load_policy())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-autonomy-policy")
def get_delegation_autonomy_policy(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_autonomy.load_policy())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-retry-policy")
def get_delegation_retry_policy(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_retry.load_policy())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-timeout-policy")
def get_delegation_timeout_policy(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_timeout.load_policy())
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/timeout-scan")
def scan_delegation_timeouts(
    payload: DelegationTimeoutScanPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_timeout.run_timeout_scan(dry_run=payload.dry_run))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/timeout-check")
def check_delegation_timeout(task_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        task = runtime.delegation.get_task(task_id)
        latest = runtime.delegation_execution.latest_execution(task_id)
        candidate = runtime.delegation_timeout.evaluate_timeout(task, latest)
        return {"candidate": asdict(candidate) if candidate else None}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/timeout-apply")
def apply_delegation_timeout(task_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.delegation_timeout.apply_timeout(task_id, dry_run=False))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/dead-letter")
def list_dead_letter_entries(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(entry) for entry in runtime.dead_letter.list_entries(status=status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/dead-letter/{dlq_id}")
def get_dead_letter_entry(dlq_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.dead_letter.get_entry(dlq_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/dead-letter")
def create_dead_letter_entry(
    payload: DeadLetterCreatePayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.dead_letter.move_to_dead_letter(
                payload.task_id,
                reason=payload.reason,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/dead-letter/{dlq_id}/review")
def review_dead_letter_entry(dlq_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.dead_letter.review_entry(dlq_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/dead-letter/{dlq_id}/restore")
def restore_dead_letter_entry(dlq_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        entry = runtime.dead_letter.get_entry(dlq_id)
        if entry.attempt_id:
            return asdict(runtime.mission_recovery.restore_dead_letter(dlq_id))
        return asdict(runtime.dead_letter.restore_entry(dlq_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/dead-letter/{dlq_id}/retry")
def retry_dead_letter_entry(dlq_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).mission_recovery.restore_dead_letter(dlq_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/dead-letter/{dlq_id}/close")
def close_dead_letter_entry(dlq_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.dead_letter.close_entry(dlq_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/dead-letter/{dlq_id}/archive")
def archive_dead_letter(dlq_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).dead_letter.archive_entry(dlq_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/retry-check")
def check_delegation_retry(task_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        task = runtime.delegation.get_task(task_id)
        executions = runtime.delegation_execution.list_task_executions(task_id)
        return runtime.delegation_retry.evaluate_retry(task, executions).to_dict()
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/retry")
def retry_delegation(
    task_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return runtime.delegation.request_retry(task_id, context=context)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/autonomy-check")
def check_delegation_autonomy(
    task_id: str,
    payload: DelegationAutonomyCheckPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        if payload.action not in {"accept", "start", "reject"}:
            raise ValidationError("action must be one of: accept, start, reject")
        task = runtime.delegation.get_task(task_id)
        identity = runtime.identities.load_identity(task.assignee_agent_id)
        effective_policy = runtime.policies.resolve(context, task.assignee_agent_id)
        return runtime.delegation_autonomy.explain_decision(
            task_id,
            payload.action,
            task,
            identity,
            effective_policy,
        ).to_dict()
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-inbox/{agent_id}/next")
def get_next_delegation(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        tasks = [
            runtime.delegation.get_task(entry.task_id)
            for entry in runtime.delegation_inbox.get_active_tasks(agent_id)
        ]
        return asdict(runtime.delegation_scheduling.select_next_task(agent_id, tasks))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegation-inbox/{agent_id}/order")
def get_delegation_order(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        tasks = [
            runtime.delegation.get_task(entry.task_id)
            for entry in runtime.delegation_inbox.get_active_tasks(agent_id)
        ]
        return asdict(runtime.delegation_scheduling.explain_task_order(agent_id, tasks))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegation-inbox/{agent_id}/rebuild")
def rebuild_delegation_inbox(agent_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(entry) for entry in runtime.delegation_inbox.rebuild_agent_inbox(agent_id)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegation-inbox/rebuild-all")
def rebuild_all_delegation_inboxes(request: Request) -> dict[str, list[dict[str, Any]]]:
    runtime = runtime_from(request)
    try:
        rebuilt = runtime.delegation_inbox.rebuild_all_inboxes()
        return {
            agent_id: [asdict(entry) for entry in entries] for agent_id, entries in rebuilt.items()
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations")
def create_delegation(
    payload: DelegationCreatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.delegation.create_task(
                context=context,
                title=payload.title,
                description=payload.description,
                requester_agent_id=payload.requester_agent_id,
                assignee_agent_id=payload.assignee_agent_id,
                priority=payload.priority,
                conversation_id=payload.conversation_id,
                mission_id=payload.mission_id,
                due_at=payload.due_at,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/accept")
def accept_delegation(
    task_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.delegation.accept_task(context, task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/reject")
def reject_delegation(
    task_id: str,
    payload: DelegationTransitionPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.delegation.reject_task(context, task_id, reason=payload.reason))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/start")
def start_delegation(
    task_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.delegation.start_task(context, task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/complete")
def complete_delegation(
    task_id: str,
    payload: DelegationTransitionPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.delegation.complete_task(context, task_id, result=payload.result))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/delegations/{task_id}/completion")
def get_delegation_completion(task_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        signal = runtime.delegation.get_completion_signal(task_id)
        return {"completion": asdict(signal) if signal else None}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/completion")
def submit_delegation_completion(
    task_id: str,
    payload: DelegationCompletionPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.delegation.submit_completion_signal(
                context=context,
                task_id=task_id,
                status=payload.status,
                summary=payload.summary,
                result=payload.result,
                failure_reason=payload.failure_reason,
                needs_followup=payload.needs_followup,
                followup_message=payload.followup_message,
                created_by_agent_id=payload.created_by_agent_id,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/delegations/{task_id}/completion/apply")
def apply_delegation_completion(
    task_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.delegation.apply_completion_signal(context, task_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/workers/status")
def worker_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.worker.status())
