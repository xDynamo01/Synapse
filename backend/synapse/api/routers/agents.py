from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.agents.provisioning import AgentCreateRequest, AgentUpdateRequest
from synapse.api.common import api_error, context_from, runtime_from
from synapse.api.routers.conversations import LocalChatRequest

router = APIRouter()


class AgentToolCallPayload(BaseModel):
    text: str
    conversation_id: str | None = None
    mission_id: str | None = None


class AgentMessageRequest(BaseModel):
    from_agent_id: str
    subject: str = "Agent message"
    body: str
    task_id: str | None = None


class DelegationProcessPayload(BaseModel):
    limit: int = 1


class AgentCreatePayload(BaseModel):
    agent_id: str
    display_name: str
    role: str
    description: str = ""
    focus_areas: list[str] = Field(default_factory=list)
    communication_style: str = "concise"
    autonomy_level: str = "manual"
    default_model: str | None = None
    default_provider: str | None = None
    system_prompt: str | None = None
    soul_content: str | None = None
    skills_content: str | None = None
    capabilities_allow: list[str] = Field(default_factory=list)
    capabilities_deny: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    operational_rules: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    initial_memory: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    overwrite: bool = False
    can_delegate: bool = False
    dry_run: bool = False
    agent_kind: str = "persistent"


class AgentUpdatePayload(BaseModel):
    display_name: str | None = None
    role: str | None = None
    description: str | None = None
    focus_areas: list[str] | None = None
    communication_style: str | None = None
    autonomy_level: str | None = None
    default_model: str | None = None
    default_provider: str | None = None
    system_prompt: str | None = None
    soul_content: str | None = None
    skills_content: str | None = None
    capabilities_allow: list[str] | None = None
    capabilities_deny: list[str] | None = None
    preferred_tools: list[str] | None = None
    forbidden_tools: list[str] | None = None
    permissions: list[str] | None = None
    operational_rules: list[str] | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class AgentDeletePayload(BaseModel):
    confirmation: str
    force: bool = False


class AdminActionRequestPayload(BaseModel):
    action: str
    agent_id: str
    actor_agent_id: str | None = None
    reason: str | None = None
    correlation_id: str | None = None


class AdminRequestCleanupPayload(BaseModel):
    dry_run: bool = True


@router.get("/agents/{agent_id}/context-preview/{conversation_id}")
def agent_context_preview(
    agent_id: str,
    conversation_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return runtime.worker.preview_context(context, agent_id, conversation_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/process-delegations")
def process_agent_delegations(
    agent_id: str,
    payload: DelegationProcessPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return [
            asdict(result)
            for result in runtime.worker.process_delegations(context, agent_id, limit=payload.limit)
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/enqueue-delegations")
def enqueue_agent_delegations(
    agent_id: str,
    payload: DelegationProcessPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.scheduler.enqueue(
                context,
                "process_agent_delegations",
                {"agent_id": agent_id, "limit": payload.limit},
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agents")
def list_agents(
    request: Request,
    include_archived: bool = True,
    include_seed: bool = False,
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    entries = runtime.admin.list_agents(include_archived=include_archived)
    if not include_seed:
        entries = [entry for entry in entries if not entry.is_seed_agent]
    return [_agent_profile(runtime, entry.agent_id) for entry in entries]


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return _agent_profile(runtime, agent_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agent-directory")
def agent_directory(request: Request, include_archived: bool = False) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(agent) for agent in runtime.admin.list_agents(include_archived)]


@router.get("/agent-admin/requests")
def list_agent_admin_requests(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(item) for item in runtime.admin.list_admin_action_requests()]


@router.get("/agent-admin/requests/retention")
def agent_admin_request_retention(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.admin.admin_action_request_retention_status()


@router.post("/agent-admin/requests/cleanup")
def cleanup_agent_admin_requests(
    payload: AdminRequestCleanupPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.admin.cleanup_admin_action_requests(dry_run=payload.dry_run))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agent-admin/requests/{request_id}")
def get_agent_admin_request(request_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.admin.get_admin_action_request(request_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-admin/requests")
def request_agent_admin_action(
    payload: AdminActionRequestPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(
        runtime,
        x_actor_id or payload.actor_agent_id,
        x_actor_type,
        x_device_id,
    )
    try:
        result = runtime.admin.request_admin_action(
            action=payload.action,
            agent_id=payload.agent_id,
            actor_agent_id=payload.actor_agent_id or context.actor_id,
            reason=payload.reason,
            correlation_id=payload.correlation_id,
            context=context,
        )
        return asdict(result)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-admin/requests/{request_id}/approve")
def approve_agent_admin_request(
    request_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.admin.approve_admin_action_request(request_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-admin/requests/{request_id}/reject")
def reject_agent_admin_request(
    request_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.admin.reject_admin_action_request(request_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-admin/requests/{request_id}/apply")
def apply_agent_admin_request(
    request_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.admin.apply_admin_action_request(request_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agents/{agent_id}/admin")
def agent_admin_status(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.admin.get_agent_admin_status(agent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agents/{agent_id}/audit")
def list_agent_audit(agent_id: str, request: Request, limit: int = 50) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(record) for record in runtime.audit.list_agent_audit(agent_id, limit)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agent-audit/recent")
def list_recent_agent_audit(request: Request, limit: int = 100) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(record) for record in runtime.audit.list_recent_audit(limit)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agents/{agent_id}/audit/summary")
def agent_audit_summary(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.audit.get_agent_audit_summary(agent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/activate")
def activate_agent(
    agent_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.admin.activate_agent(agent_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/deactivate")
def deactivate_agent(
    agent_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.admin.deactivate_agent(agent_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/archive")
def archive_agent(
    agent_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.admin.archive_agent(agent_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/restore")
def restore_agent(
    agent_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.admin.restore_agent(agent_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/agents/{agent_id}")
def delete_agent(
    agent_id: str,
    payload: AgentDeletePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.admin.delete_agent(
                agent_id,
                payload.confirmation,
                context,
                force=payload.force,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents")
def create_agent(
    payload: AgentCreatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        provisioning_request = AgentCreateRequest(**payload.model_dump())
        context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        result = runtime.provisioning.create_agent(provisioning_request, context=context)
        return {
            **asdict(result),
            "agent": _agent_profile(runtime, result.agent_id) if result.created else None,
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/preview")
def preview_agent(
    payload: AgentCreatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        provisioning_request = AgentCreateRequest(**payload.model_dump())
        provisioning_request = AgentCreateRequest(
            **{**asdict(provisioning_request), "dry_run": True}
        )
        context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        return asdict(runtime.provisioning.create_agent(provisioning_request, context=context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/agents/{agent_id}")
def update_agent(
    agent_id: str,
    payload: AgentUpdatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        update_request = AgentUpdateRequest(**payload.model_dump())
        context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        result = runtime.provisioning.update_agent(
            agent_id,
            update_request,
            context=context,
        )
        return {
            **asdict(result),
            "agent": _agent_profile(runtime, agent_id) if result.updated else None,
        }
    except Exception as exc:
        raise api_error(exc) from exc


def _agent_profile(runtime: Any, agent_id: str) -> dict[str, Any]:
    agent = runtime.agents.get(agent_id)
    admin = runtime.admin.get_agent_admin_status(agent_id)
    return {
        "agent_id": agent.id,
        "display_name": agent.name,
        "role": agent.role,
        "kind": agent.kind.value,
        "status": admin.status,
        "can_delegate": agent.can_delegate,
        "preferred_model": agent.preferred_model,
        "autonomy": agent.autonomy,
        "skills": list(agent.skills),
        "permissions": list(agent.permissions),
    }


@router.post("/agents/{agent_id}/validate")
def validate_agent(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.provisioning.validate_agent_files(agent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agent-provisioning/status")
def agent_provisioning_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.provisioning.get_agent_provisioning_status()


@router.get("/agent-provisioning/policy")
def agent_provisioning_policy(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.provisioning.current_policy()


@router.get("/agent-provisioning/requests")
def list_agent_provisioning_requests(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(item) for item in runtime.provisioning.list_provisioning_requests()]


@router.get("/agent-provisioning/requests/{request_id}")
def get_agent_provisioning_request(request_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.provisioning.get_provisioning_request(request_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-provisioning/requests/{request_id}/approve")
def approve_agent_provisioning_request(
    request_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.provisioning.approve_provisioning_request(context, request_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-provisioning/requests/{request_id}/reject")
def reject_agent_provisioning_request(
    request_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.provisioning.reject_provisioning_request(context, request_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-provisioning/requests/{request_id}/apply")
def apply_agent_provisioning_request(
    request_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.provisioning.apply_approved_provisioning_request(context, request_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agents/{agent_id}/capabilities")
def list_agent_capabilities(
    agent_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return [
            asdict(capability)
            for capability in runtime.capabilities.agent_capabilities(agent_id, context=context)
        ]
    except Exception as exc:
        raise api_error(exc) from exc


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


@router.post("/agents/{agent_id}/tool-call/preview")
def preview_agent_tool_call(
    agent_id: str,
    payload: AgentToolCallPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.agent_tool_calling.preview_tool_calling(
                agent_id,
                payload.text,
                payload.conversation_id,
                payload.mission_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agents/{agent_id}/tool-call/create")
def create_agent_tool_call(
    agent_id: str,
    payload: AgentToolCallPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.agent_tool_calling.create_intents_from_output(
                agent_id,
                payload.text,
                payload.conversation_id,
                payload.mission_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agents/{agent_id}/tools")
def agent_tool_catalog(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.agent_runtime.available_tools(agent_id))
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


@router.post("/agents/{agent_id}/local-chat")
def local_chat_agent(
    agent_id: str,
    payload: LocalChatRequest,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.chat.submit_turn(
                context,
                content=payload.message,
                target_agent_id=agent_id,
                conversation_id=payload.conversation_id,
                project_id=payload.project_id,
                model_provider_id=payload.model_provider_id,
                model_name=payload.model_name,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc
