from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from synapse.api.common import api_error, context_from, runtime_from

router = APIRouter()


class PrimaryAssignmentPayload(BaseModel):
    agent_id: str
    workspace_id: str = "default"


class PrimaryInteractionPayload(BaseModel):
    workspace_id: str = "default"


class EphemeralCleanupPayload(BaseModel):
    dry_run: bool = True


@router.get("/primary-agent")
def get_primary_agent(request: Request, workspace_id: str = "default") -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.primary_agent.get_state(workspace_id))


@router.put("/primary-agent")
def set_primary_agent(
    payload: PrimaryAssignmentPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        return asdict(
            runtime.primary_agent.set_primary(context, payload.agent_id, payload.workspace_id)
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/primary-agent/replace")
def replace_primary_agent(
    payload: PrimaryAssignmentPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        return asdict(
            runtime.primary_agent.replace_primary(context, payload.agent_id, payload.workspace_id)
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/primary-interaction/bootstrap")
def primary_interaction_bootstrap(
    request: Request, workspace_id: str = "default"
) -> dict[str, Any]:
    return asdict(
        runtime_from(request).primary_agent.get_primary_interaction_bootstrap(workspace_id)
    )


@router.get("/primary-interaction/conversation")
def primary_conversation(request: Request, workspace_id: str = "default") -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        profile = runtime.primary_agent.get_primary(workspace_id)
        return asdict(runtime.conversations.get_conversation(profile.conversation_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/primary-interaction/resume")
def resume_primary_interaction(
    payload: PrimaryInteractionPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        return asdict(runtime.primary_agent.resume_interaction(context, payload.workspace_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/primary-interaction/pause")
def pause_primary_interaction(
    payload: PrimaryInteractionPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        return asdict(runtime.primary_agent.pause_interaction(context, payload.workspace_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/missions/{mission_id}/ephemeral-agents")
def list_ephemeral_agents(mission_id: str, request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).ephemeral_agents.list(mission_id)]


@router.get("/ephemeral-agents/{ephemeral_agent_id}")
def get_ephemeral_agent(ephemeral_agent_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).ephemeral_agents.get(ephemeral_agent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/ephemeral-agents/{ephemeral_agent_id}/result")
def get_ephemeral_agent_result(ephemeral_agent_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).ephemeral_agents.get_result(ephemeral_agent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/swarms/{swarm_id}/workforce-plan")
def get_ephemeral_workforce_plan(swarm_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).swarm.get_workforce_plan(swarm_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/ephemeral-agents/reconcile")
def reconcile_ephemeral_agents(request: Request) -> list[dict[str, Any]]:
    try:
        return [asdict(item) for item in runtime_from(request).ephemeral_agents.reconcile()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/ephemeral-agents/cleanup")
def cleanup_ephemeral_agents(payload: EphemeralCleanupPayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).ephemeral_agents.cleanup(dry_run=payload.dry_run))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/ephemeral-agents/{ephemeral_agent_id}/cancel")
def cancel_ephemeral_agent(ephemeral_agent_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).ephemeral_agents.cancel(ephemeral_agent_id))
    except Exception as exc:
        raise api_error(exc) from exc
