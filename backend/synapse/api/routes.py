from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from synapse.core.exceptions import NotFound, PermissionDenied, SynapseError, ValidationError

router = APIRouter()


class ToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessageRequest(BaseModel):
    from_agent_id: str
    subject: str = "Agent message"
    body: str
    task_id: str | None = None


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    project_id: str | None = None
    session_id: str | None = None


class JobRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    max_attempts: int = 3
    scheduled_for: str | None = None
    correlation_id: str | None = None


class DraftRequest(BaseModel):
    subject: str
    recipients: list[str]
    body: str
    provider: str = "mock"
    created_by_agent: str = "hermes"


def runtime_from(request: Request):
    return request.app.state.runtime


def context_from(runtime, actor_id: str | None, actor_type: str | None, device_id: str | None = None):
    return runtime.context(actor_id=actor_id, actor_type=actor_type or "user", device_id=device_id)


def api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionDenied):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SynapseError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=type(exc).__name__)


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    route = runtime.models.default_route()
    return {
        "status": "ok",
        "data_dir": str(runtime.data_dir.root),
        "default_model_route": asdict(route),
    }


@router.get("/agents")
def list_agents(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(agent) for agent in runtime.agents.list_agents()]


@router.get("/agents/{agent_id}/inbox")
def list_agent_inbox(
    agent_id: str,
    request: Request,
    status: str | None = None,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return [asdict(message) for message in runtime.worker.list_inbox(context, agent_id, status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/process-inbox")
def process_agent_inbox(
    agent_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return [asdict(result) for result in runtime.worker.process_inbox(context, agent_id)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/workers/status")
def worker_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.worker.status())


@router.get("/presence")
def list_presence(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(presence) for presence in runtime.presence.list_all()]


@router.get("/presence/{agent_id}")
def get_presence(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.presence.get(agent_id))


@router.get("/lifecycle")
def list_lifecycle(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(lifecycle) for lifecycle in runtime.lifecycle.list_all()]


@router.get("/lifecycle/{agent_id}")
def get_lifecycle(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.lifecycle.get(agent_id))


@router.post("/lifecycle/{agent_id}/wake")
def wake_agent(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.lifecycle.wake(agent_id, "api wake"))


@router.post("/lifecycle/{agent_id}/sleep")
def sleep_agent(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.lifecycle.sleep(agent_id))


@router.get("/communication/messages")
def list_communication_messages(request: Request, provider: str = "mock") -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [
        asdict(message)
        for message in runtime.communication_runtime.list_messages(provider=provider)
    ]


@router.get("/communication/messages/{message_id}")
def read_communication_message(
    message_id: str,
    request: Request,
    provider: str = "mock",
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.communication_runtime.read_message(message_id, provider=provider))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/communication/drafts")
def list_communication_drafts(request: Request, provider: str = "mock") -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [
        asdict(draft)
        for draft in runtime.communication_runtime.list_drafts(provider=provider)
    ]


@router.post("/communication/drafts")
def create_communication_draft(
    payload: DraftRequest,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        draft = runtime.communication_runtime.create_draft(
            subject=payload.subject,
            recipients=payload.recipients,
            body=payload.body,
            created_by_agent=payload.created_by_agent,
            provider=payload.provider,
        )
        return asdict(draft)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/communication/summary")
def communication_summary(request: Request, provider: str = "mock") -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.communication_runtime.daily_summary(provider=provider)


@router.get("/notifications")
def list_notifications(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(notification) for notification in runtime.notifications.list_notifications()]


@router.get("/notifications/unread")
def list_unread_notifications(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(notification) for notification in runtime.notifications.list_unread()]


@router.post("/notifications/cleanup")
def cleanup_notifications(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.notifications.cleanup_notifications())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/notifications/{notification_id}")
def get_notification(notification_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.notifications.get(notification_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.notifications.mark_read(notification_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/notifications/{notification_id}")
def delete_notification(notification_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        runtime.notifications.delete_notification(notification_id)
        return {"deleted": True, "id": notification_id}
    except Exception as exc:
        raise api_error(exc) from exc


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


@router.get("/events")
def list_events(request: Request, limit: int = 100) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(event) for event in runtime.events.tail(limit=limit)]


@router.get("/trace/{correlation_id}")
def trace_events(correlation_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {
        "events": [asdict(event) for event in runtime.events.trace(correlation_id)],
        "records": runtime.events.trace_records(correlation_id),
    }


@router.get("/jobs")
def list_jobs(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(job) for job in runtime.scheduler.list_jobs(status=status)]
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


@router.get("/tasks")
def list_tasks(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(task) for task in runtime.tasks.list_tasks(status=status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tools")
def list_tools(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(spec) for spec in runtime.tools.list_specs()]


@router.get("/approvals/pending")
def list_pending_approvals(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(approval) for approval in runtime.approvals.list_pending()]


@router.post("/approvals/{approval_id}/approve")
def approve_approval(
    approval_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        approval, tool_result = runtime.approval_resume.approve_and_resume(context, approval_id)
        return {"approval": asdict(approval), "tool_result": asdict(tool_result)}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/approvals/{approval_id}/reject")
def reject_approval(
    approval_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.approvals.reject(context, approval_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tools/{tool_name}")
def execute_tool(
    tool_name: str,
    payload: ToolRequest,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return runtime.tools.execute(tool_name, context, payload.arguments)
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
        task = runtime.tasks.create_task(context, payload.title, payload.description, payload.metadata)
        return asdict(task)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{to_agent_id}/messages")
def send_agent_message(
    to_agent_id: str,
    payload: AgentMessageRequest,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        message = runtime.communication.send_agent_message(
            context=context,
            from_agent_id=payload.from_agent_id,
            to_agent_id=to_agent_id,
            subject=payload.subject,
            body=payload.body,
            task_id=payload.task_id,
        )
        return asdict(message)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/chat")
def chat(
    payload: ChatRequest,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        result = runtime.chat.send_message(
            context=context,
            agent_id=payload.agent_id,
            user_message=payload.message,
            project_id=payload.project_id,
            session_id=payload.session_id,
        )
        return asdict(result)
    except Exception as exc:
        raise api_error(exc) from exc
