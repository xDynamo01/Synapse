from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, runtime_from

router = APIRouter()


class MemoryCreatePayload(BaseModel):
    scope: str
    owner_id: str
    source: str = "api"
    content: str
    content_type: str = "text/plain"
    expires_at: str | None = None
    confidence: float | None = None
    importance: int = 50
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdatePayload(BaseModel):
    expected_revision: int
    content: str | None = None
    importance: int | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class MemoryDeletePayload(BaseModel):
    expected_revision: int


class MemorySearchPayload(BaseModel):
    query: str = ""
    scopes: list[str]
    owner_ids: list[str] | None = None
    limit: int = 20
    filters: dict[str, Any] = Field(default_factory=dict)
    budget: int | None = None


class MemoryImportPayload(BaseModel):
    schema_version: int
    records: list[dict[str, Any]]


class ContextPreviewPayload(BaseModel):
    conversation_id: str | None = None
    agent_id: str | None = None
    incoming_message: str | None = None
    mission_id: str | None = None
    session_id: str | None = None
    files: list[dict[str, Any]] = Field(default_factory=list)
    perception: list[dict[str, Any]] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


@router.get("/context/conversation/{conversation_id}")
def fused_conversation_context(conversation_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.context_fusion.build_conversation_context(conversation_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/context/mission/{mission_id}")
def fused_mission_context(mission_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.context_fusion.build_mission_context(mission_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/context/session/{session_id}")
def fused_multimodal_context(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.context_fusion.build_multimodal_context(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/context/validate/{conversation_id}")
def validate_fused_context(conversation_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.context_fusion.build_conversation_context(conversation_id).consistency
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/memory")
def list_memory(
    request: Request,
    scope: str | None = None,
    owner_id: str | None = None,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [
            asdict(item)
            for item in runtime.memory.list(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                scope=scope,
                owner_id=owner_id,
            )
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/memory")
def create_memory(
    payload: MemoryCreatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.memory.create(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id), **payload.model_dump()
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/memory/{memory_id}")
def get_memory(
    memory_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.memory.get(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id), memory_id
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/memory/{memory_id}")
def update_memory(
    memory_id: str,
    payload: MemoryUpdatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.memory.update(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                memory_id,
                **payload.model_dump(),
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/memory/{memory_id}")
def delete_memory(
    memory_id: str,
    payload: MemoryDeletePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.memory.delete(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                memory_id,
                expected_revision=payload.expected_revision,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/memory/search")
def search_memory(
    payload: MemorySearchPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.memory.retrieve_memory(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id), **payload.model_dump()
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/memory/export/records")
def export_memory(
    request: Request,
    scopes: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.memory.export_records(
            context_from(runtime, x_actor_id, x_actor_type, x_device_id),
            scopes=[item for item in scopes.split(",") if item],
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/memory/import")
def import_memory(
    payload: MemoryImportPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [
            asdict(item)
            for item in runtime.memory.import_records(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id), payload.model_dump()
            )
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/context/preview")
def preview_context(
    payload: ContextPreviewPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        permission_context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
        return asdict(
            runtime.context_fusion.build_context(
                **payload.model_dump(),
                permission_context=permission_context,
                persist_snapshot=False,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc
