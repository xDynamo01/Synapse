from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, payload_dict, runtime_from

router = APIRouter()


class ConversationCreatePayload(BaseModel):
    participants: list[str]
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationUpdatePayload(BaseModel):
    title: str | None = None
    metadata: dict[str, Any] | None = None
    expected_revision: int | None = None


class ConversationParticipantPayload(BaseModel):
    participant_id: str
    participant_type: str = "agent"
    role: str = "participant"
    permissions: list[str] = Field(default_factory=list)


class ConversationTurnPayload(BaseModel):
    content: str
    sender_id: str = "local_chat"
    target_agent_id: str | None = None
    model_provider_id: str | None = None
    model_name: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str | None = None
    project_id: str | None = None


class ConversationAttachmentPayload(BaseModel):
    filename: str
    mime_type: str
    size: int
    storage_ref: str
    checksum: str
    owner_id: str


class ConversationSummaryPayload(BaseModel):
    summary: str
    last_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSummaryGeneratePayload(BaseModel):
    agent_id: str | None = None


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    project_id: str | None = None
    session_id: str | None = None


class LocalChatRequest(BaseModel):
    message: str
    agent_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    model_provider_id: str | None = None
    model_name: str | None = None


@router.get("/conversations")
def list_conversations(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(item) for item in runtime.conversations.list_conversations()]


@router.post("/conversations")
def create_conversation(
    payload: ConversationCreatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.conversations.create_conversation(
                context=context,
                participants=payload.participants,
                title=payload.title,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.conversations.get_conversation(conversation_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdatePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.conversations.update_conversation(
                context,
                conversation_id,
                title=payload.title,
                metadata=payload.metadata,
                expected_revision=payload.expected_revision,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/archive")
def archive_conversation_api(
    conversation_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.conversations.archive_conversation(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id), conversation_id
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/restore")
def restore_conversation_api(
    conversation_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.conversations.resume_conversation(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id), conversation_id
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    request: Request,
    confirmed: bool = False,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(
            runtime.conversations.delete_conversation(context, conversation_id, confirmed=confirmed)
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/conversations/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str, request: Request, offset: int = 0, limit: int = 100
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [
            asdict(message)
            for message in runtime.conversations.list_conversation_messages(
                conversation_id, offset=offset, limit=limit
            )
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/conversations/{conversation_id}/summary")
def get_conversation_summary(conversation_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.conversations.get_conversation_summary(conversation_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/summary")
def update_conversation_summary(
    conversation_id: str,
    payload: ConversationSummaryPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.conversations.update_conversation_summary(
                conversation_id,
                payload.summary,
                last_message_id=payload.last_message_id,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/summary/generate")
def generate_conversation_summary(
    conversation_id: str,
    payload: ConversationSummaryGeneratePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.chat.generate_conversation_summary(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                conversation_id,
                payload.agent_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/conversations/{conversation_id}/context")
def build_conversation_context(
    conversation_id: str,
    request: Request,
    max_messages: int = 10,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.conversations.build_conversation_context(
            conversation_id,
            max_messages=max_messages,
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/participants")
def add_conversation_participant(
    conversation_id: str,
    payload: ConversationParticipantPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.conversations.add_participant(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                conversation_id,
                payload.participant_id,
                payload.participant_type,
                payload.role,
                payload.permissions,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/conversations/{conversation_id}/participants/{participant_id}")
def remove_conversation_participant(
    conversation_id: str,
    participant_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.conversations.remove_participant(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                conversation_id,
                participant_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/turns")
def submit_conversation_turn(
    conversation_id: str,
    payload: ConversationTurnPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.chat.submit_turn(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                conversation_id=conversation_id,
                content=payload.content,
                sender_id=payload.sender_id,
                target_agent_id=payload.target_agent_id,
                model_provider_id=payload.model_provider_id,
                model_name=payload.model_name,
                attachments=payload.attachments,
                idempotency_key=payload.idempotency_key,
                project_id=payload.project_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/turns/stream")
def stream_conversation_turn(
    conversation_id: str,
    payload: ConversationTurnPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)

    def stream():
        for event in runtime.chat.stream_turn(
            context,
            conversation_id=conversation_id,
            content=payload.content,
            sender_id=payload.sender_id,
            target_agent_id=payload.target_agent_id,
            model_provider_id=payload.model_provider_id,
            model_name=payload.model_name,
            attachments=payload.attachments,
            idempotency_key=payload.idempotency_key,
            project_id=payload.project_id,
        ):
            yield json.dumps(event, sort_keys=True) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/conversations/{conversation_id}/attachments")
def list_conversation_attachments(conversation_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return runtime.conversations.list_attachments(conversation_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/attachments")
def register_conversation_attachment(
    conversation_id: str,
    payload: ConversationAttachmentPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.conversations.register_attachment(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id),
                conversation_id,
                **payload_dict(payload),
            )
        )
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
        result = runtime.chat.submit_turn(
            context,
            content=payload.message,
            target_agent_id=payload.agent_id,
            project_id=payload.project_id,
        )
        return asdict(result)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/local-chat")
def local_chat(
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
                target_agent_id=payload.agent_id,
                conversation_id=payload.conversation_id,
                project_id=payload.project_id,
                model_provider_id=payload.model_provider_id,
                model_name=payload.model_name,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/local-chat")
def local_chat_conversation(
    conversation_id: str,
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
                target_agent_id=payload.agent_id,
                conversation_id=conversation_id,
                project_id=payload.project_id,
                model_provider_id=payload.model_provider_id,
                model_name=payload.model_name,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc
