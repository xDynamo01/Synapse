from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, require_admin, runtime_from

router = APIRouter()


class DeferPayload(BaseModel):
    until: str | None = None


class SuppressPayload(BaseModel):
    reason: str


class ModePayload(BaseModel):
    mode: str
    allowed_dispositions: list[str] | None = None
    max_proactive_actions_per_hour: int | None = Field(default=None, ge=0, le=100)


@router.get("/world-state")
def world_state_snapshot(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).world_state.snapshot())


@router.get("/world-state/history")
def world_state_history(request: Request, limit: int = 100) -> list[dict[str, Any]]:
    return [
        asdict(item) for item in runtime_from(request).world_state.history(limit=min(limit, 500))
    ]


@router.get("/world-state/{entity_type}")
def world_state_entity(
    entity_type: str, request: Request, entity_id: str | None = None
) -> dict[str, Any]:
    try:
        value = runtime_from(request).world_state.get_entity(entity_type, entity_id)
        return {"entity_type": entity_type, "entity_id": entity_id, "value": value}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/world-state/reconcile")
def world_state_reconcile(
    request: Request, x_actor_type: str | None = Header(default=None)
) -> dict[str, Any]:
    require_admin(x_actor_type)
    return asdict(runtime_from(request).world_state.reconcile_state())


@router.get("/attention")
def attention_list(
    request: Request, status: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    try:
        return [
            asdict(item)
            for item in runtime_from(request).attention.list_items(status, min(limit, 500))
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/attention/{item_id}")
def attention_item(item_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).attention.get_item(item_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/attention/{item_id}/acknowledge")
def attention_acknowledge(item_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).attention.acknowledge(item_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/attention/{item_id}/defer")
def attention_defer(item_id: str, payload: DeferPayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).attention.defer(item_id, payload.until))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/attention/{item_id}/suppress")
def attention_suppress(
    item_id: str,
    payload: SuppressPayload,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        return asdict(runtime_from(request).attention.suppress(item_id, payload.reason))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/attention/{item_id}/resolve")
def attention_resolve(item_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).attention.resolve(item_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agent-loop/status")
def agent_loop_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {"state": asdict(runtime.agent_loop.status()), "health": runtime.agent_loop.health()}


@router.post("/agent-loop/start")
def agent_loop_start(request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).agent_loop.start())
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-loop/pause")
def agent_loop_pause(request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).agent_loop.pause())
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-loop/resume")
def agent_loop_resume(request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).agent_loop.resume())
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-loop/stop")
def agent_loop_stop(request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).agent_loop.stop())
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/agent-loop/run-once")
def agent_loop_run_once(
    request: Request, x_actor_type: str | None = Header(default=None)
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        return asdict(runtime_from(request).agent_loop.run_cycle(trigger="api.run_once"))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agent-loop/cycles")
def agent_loop_cycles(request: Request, limit: int = 100) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).agent_loop.list_cycles(min(limit, 500))]


@router.get("/agent-loop/pending-approvals")
def agent_loop_pending_approvals(request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).agent_loop.pending_approvals()]


@router.get("/agent-loop/mode")
def agent_loop_mode(request: Request) -> dict[str, Any]:
    return runtime_from(request).attention_decisions.load_policy()


@router.put("/agent-loop/mode")
def agent_loop_set_mode(
    payload: ModePayload,
    request: Request,
    x_actor_type: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_actor_type)
    try:
        return runtime_from(request).attention_decisions.update_policy(
            mode=payload.mode,
            allowed_dispositions=payload.allowed_dispositions,
            max_proactive_actions_per_hour=payload.max_proactive_actions_per_hour,
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/agent-events")
def agent_events(request: Request, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    return runtime_from(request).agent_event_stream.list_events(offset, limit)


@router.get("/agent-loop/domain-health")
def agent_loop_domain_health(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {
        "world_state": runtime.world_state.health(),
        "attention": runtime.attention.health(),
        "decision": {"status": "healthy", "policy": runtime.attention_decisions.load_policy()},
        "agent_loop": runtime.agent_loop.health(),
    }
