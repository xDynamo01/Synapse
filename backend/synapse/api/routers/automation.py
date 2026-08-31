from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, runtime_from

router = APIRouter()


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    max_attempts: int = 3
    scheduled_for: str | None = None
    correlation_id: str | None = None


@router.get("/daemon/status")
def daemon_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.daemon.status())


@router.post("/daemon/run-once")
def daemon_run_once(
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.daemon.run_once(context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/daemon/runner")
def daemon_runner(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.runner_identity.load())


@router.post("/daemon/runner/heartbeat")
def daemon_runner_heartbeat(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.runner_identity.heartbeat())


@router.get("/jobs")
def list_jobs(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(job) for job in runtime.scheduler.list_jobs(status=status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).scheduler.get_job(job_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/jobs")
def enqueue_job(
    payload: JobRequest,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        job = runtime.scheduler.enqueue(
            context=context,
            job_type=payload.type,
            payload=payload.payload,
            priority=payload.priority,
            max_attempts=payload.max_attempts,
            scheduled_for=payload.scheduled_for,
            correlation_id=payload.correlation_id,
        )
        return asdict(job)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/jobs/run")
def run_jobs(
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return [asdict(job) for job in runtime.scheduler.run_all_pending(context)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.scheduler.cancel_job(context, job_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.scheduler.pause_job(runtime.context(), job_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.scheduler.resume_job(runtime.context(), job_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/scheduler/recurring")
def list_recurring_jobs(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(job) for job in runtime.scheduler.load_recurring_jobs()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/scheduler/recurring/run")
def run_recurring_jobs(
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return [asdict(job) for job in runtime.scheduler.enqueue_due_recurring_jobs(context)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/scheduler/lock")
def scheduler_lock(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.scheduler.lock_status()


@router.get("/tasks")
def list_tasks(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(task) for task in runtime.tasks.list_tasks(status=status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/scheduler/lock/recover")
def recover_scheduler_lock(request: Request) -> dict[str, Any]:
    try:
        return runtime_from(request).scheduler.recover_stale_lock()
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tasks")
def create_task(
    payload: CreateTaskRequest,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        task = runtime.tasks.create_task(
            context, payload.title, payload.description, payload.metadata
        )
        return asdict(task)
    except Exception as exc:
        raise api_error(exc) from exc
