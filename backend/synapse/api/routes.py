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


@router.get("/events")
def list_events(request: Request, limit: int = 100) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(event) for event in runtime.events.tail(limit=limit)]


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
