from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from synapse.agents.provisioning import AgentCreateRequest
from synapse.api.common import api_error, context_from, runtime_from
from synapse.core.exceptions import ValidationError

router = APIRouter(prefix="/frontend", tags=["frontend-v2-boundary"])


class FrontendBootstrapQuery(BaseModel):
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None


class FrontendFirstAgentPayload(BaseModel):
    agent_id: str
    display_name: str = "Synapse"
    role: str = "primary_agent"
    workspace_id: str = "default"
    default_provider: str | None = None
    default_model: str | None = None
    system_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrontendConversationOpenPayload(BaseModel):
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    title: str | None = None
    history_limit: int = Field(default=50, ge=1, le=200)


class FrontendConversationIndexQuery(BaseModel):
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class FrontendConversationDeleteQuery(BaseModel):
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None
    confirmed: bool = False


class FrontendTextTurnPayload(BaseModel):
    content: str
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None
    target_agent_id: str | None = None
    model_provider_id: str | None = None
    model_name: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str | None = None


class FrontendCancelTurnPayload(BaseModel):
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=160)


class FrontendVoiceTranscriptionPayload(BaseModel):
    audio_base64: str = Field(min_length=1)
    audio_format: str = "audio/webm"
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    language: str | None = None
    duration_ms: int | None = None


class FrontendVoiceConversationTurnPayload(BaseModel):
    audio_base64: str = Field(min_length=1)
    audio_format: str = "audio/webm"
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None
    conversation_id: str
    voice_session_id: str | None = None
    idempotency_key: str | None = None


class FrontendAttachmentStagePayload(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    mime_type: str = Field(min_length=1, max_length=120)
    size: int = Field(ge=0, le=25 * 1024 * 1024)
    content_base64: str = Field(min_length=1)
    workspace_id: str = "default"
    project_id: str | None = None
    session_id: str | None = None


SAFE_ATTACHMENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. ()-]{0,179}$")
SUPPORTED_ATTACHMENT_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
}


@router.get("/bootstrap")
def frontend_bootstrap(
    request: Request,
    workspace_id: str = "default",
    project_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    query = FrontendBootstrapQuery(
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
    )
    primary_state = runtime.primary_agent.get_state(query.workspace_id)
    model_options = frontend_model_options(runtime)
    bootstrap = runtime.primary_agent.get_primary_interaction_bootstrap(
        query.workspace_id, query.project_id
    )
    usable_primary = primary_state.state == "configured" and bootstrap.primary_agent is not None
    degraded: list[dict[str, Any]] = []
    if primary_state.state == "misconfigured":
        degraded.append(
            {
                "code": "primary_agent_misconfigured",
                "message": "Primary Agent is configured but not usable.",
                "detail": primary_state.reason,
            }
        )
    if not model_options:
        degraded.append(
            {
                "code": "no_provider_model_options",
                "message": "No usable provider/model options are available for onboarding.",
            }
        )
    return {
        "schema": "frontend-v2-bootstrap-v1",
        "workspace_id": query.workspace_id,
        "project_id": query.project_id,
        "session_id": query.session_id,
        "onboarding_required": not usable_primary,
        "primary_agent_state": primary_state.state,
        "usable_primary_agent": usable_primary,
        "primary_agent": bootstrap.primary_agent,
        "conversation": bootstrap.conversation if usable_primary else None,
        "resume_token": bootstrap.resume_token if usable_primary else None,
        "provider_model_options": model_options,
        "degraded": degraded,
        "errors": [],
    }


@router.post("/first-agent")
def create_frontend_first_agent(
    payload: FrontendFirstAgentPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        primary_state = runtime.primary_agent.get_state(payload.workspace_id)
        if primary_state.state == "configured":
            raise ValidationError("first_run_closed: usable Primary Agent already exists")
        provider_id = payload.default_provider
        model_id = payload.default_model
        if not provider_id and not model_id:
            default_selection = frontend_default_model_selection(runtime)
            provider_id = default_selection.get("provider_id")
            model_id = default_selection.get("model_id")
        validate_frontend_model_selection(runtime, provider_id, model_id)
        configure_frontend_selected_provider(
            runtime,
            provider_id,
            model_id,
        )
        result = runtime.provisioning.create_agent(
            AgentCreateRequest(
                agent_id=payload.agent_id,
                display_name=payload.display_name,
                role=payload.role,
                autonomy_level="manual",
                default_provider=provider_id,
                default_model=model_id,
                system_prompt=payload.system_prompt,
                metadata={**payload.metadata, "created_by": "frontend_v2_first_run"},
                agent_kind="persistent",
            ),
            context=context,
        )
        profile = runtime.primary_agent.set_primary(
            context,
            result.agent_id,
            payload.workspace_id,
            replace_existing=primary_state.profile is not None,
        )
        bootstrap = runtime.primary_agent.get_primary_interaction_bootstrap(payload.workspace_id)
        return {
            "schema": "frontend-v2-first-agent-result-v1",
            "status": "ready",
            "workspace_id": payload.workspace_id,
            "agent": asdict(runtime.agents.get(result.agent_id)),
            "primary_profile": asdict(profile),
            "bootstrap": asdict(bootstrap),
            "degraded": ([{"code": "model_configuration_required", "message": "Configure a chat model in Settings → Models before sending a message."}] if not provider_id or not model_id else []),
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/open")
def open_frontend_text_conversation(
    payload: FrontendConversationOpenPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        profile = runtime.primary_agent.get_primary(payload.workspace_id)
        if payload.conversation_id:
            conversation = runtime.conversations.get_conversation(payload.conversation_id)
            enforce_frontend_conversation_scope(
                conversation.metadata,
                payload.workspace_id,
                payload.project_id,
                payload.session_id,
            )
        else:
            conversation = runtime.conversations.create_conversation(
                context,
                ["local_chat", profile.agent_id],
                title=payload.title or "Synapse conversation",
                metadata={
                    "source": "frontend_v2_text_boot",
                    "workspace_id": payload.workspace_id,
                    "project_id": payload.project_id,
                    "session_id": payload.session_id,
                    "primary_agent_id": profile.agent_id,
                },
            )
        page = frontend_recent_history_page(
            runtime,
            conversation.conversation_id,
            payload.history_limit,
        )
        return {
            "schema": "frontend-v2-conversation-state-v1",
            "workspace_id": payload.workspace_id,
            "project_id": payload.project_id,
            "session_id": payload.session_id,
            "primary_agent_id": profile.agent_id,
            "conversation": asdict(conversation),
            "messages": page["messages"],
            "pagination": page["pagination"],
            "summary": frontend_summary(runtime, conversation.conversation_id),
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/conversations")
def frontend_conversation_index(
    request: Request,
    workspace_id: str = "default",
    project_id: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        query = FrontendConversationIndexQuery(
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
            limit=limit,
        )
        conversations = [
            conversation
            for conversation in runtime.conversations.list_conversations()
            if frontend_conversation_matches_scope(
                conversation.metadata,
                query.workspace_id,
                query.project_id,
                query.session_id,
            )
        ]
        ordered = sorted(
            conversations,
            key=lambda item: (item.updated_at, item.conversation_id),
            reverse=True,
        )[: query.limit]
        return {
            "schema": "frontend-v2-conversation-index-v1",
            "workspace_id": query.workspace_id,
            "project_id": query.project_id,
            "session_id": query.session_id,
            "conversations": [
                frontend_conversation_index_item(runtime, conversation)
                for conversation in ordered
            ],
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/conversations/{conversation_id}/history")
def frontend_conversation_history(
    conversation_id: str,
    request: Request,
    workspace_id: str = "default",
    project_id: str | None = None,
    session_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        conversation = runtime.conversations.get_conversation(conversation_id)
        enforce_frontend_conversation_scope(
            conversation.metadata,
            workspace_id,
            project_id,
            session_id,
        )
        page = frontend_history_page(runtime, conversation_id, offset, limit)
        return {
            "schema": "frontend-v2-conversation-history-v1",
            "workspace_id": workspace_id,
            "project_id": project_id,
            "session_id": session_id,
            "conversation": asdict(conversation),
            "messages": page["messages"],
            "pagination": page["pagination"],
            "summary": frontend_summary(runtime, conversation_id),
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/conversations/{conversation_id}")
def delete_frontend_conversation(
    conversation_id: str,
    request: Request,
    workspace_id: str = "default",
    project_id: str | None = None,
    session_id: str | None = None,
    confirmed: bool = False,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        query = FrontendConversationDeleteQuery(
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
            confirmed=confirmed,
        )
        conversation = runtime.conversations.get_conversation(conversation_id)
        enforce_frontend_conversation_scope(
            conversation.metadata,
            query.workspace_id,
            query.project_id,
            query.session_id,
        )
        deleted = runtime.conversations.delete_conversation(
            context,
            conversation_id,
            confirmed=query.confirmed,
        )
        return {
            "schema": "frontend-v2-conversation-delete-v1",
            "workspace_id": query.workspace_id,
            "project_id": query.project_id,
            "session_id": query.session_id,
            "conversation_id": deleted.conversation_id,
            "deleted": True,
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/conversations")
def clear_frontend_conversation_history(
    request: Request,
    workspace_id: str = "default",
    project_id: str | None = None,
    session_id: str | None = None,
    confirmed: bool = False,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        query = FrontendConversationDeleteQuery(
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
            confirmed=confirmed,
        )
        candidates = [
            conversation
            for conversation in runtime.conversations.list_conversations()
            if frontend_conversation_matches_deletion_scope(
                conversation.metadata,
                query.workspace_id,
                query.project_id,
                query.session_id,
            )
            and len(
                runtime.conversations.list_conversation_messages(
                    conversation.conversation_id,
                    offset=0,
                    limit=1,
                )
            )
            > 0
        ]
        deleted_ids: list[str] = []
        for conversation in candidates:
            deleted = runtime.conversations.delete_conversation(
                context,
                conversation.conversation_id,
                confirmed=query.confirmed,
            )
            deleted_ids.append(deleted.conversation_id)
        return {
            "schema": "frontend-v2-conversation-clear-history-v1",
            "workspace_id": query.workspace_id,
            "project_id": query.project_id,
            "session_id": query.session_id,
            "deleted": len(deleted_ids),
            "conversation_ids": deleted_ids,
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/turns")
def submit_frontend_text_turn(
    conversation_id: str,
    payload: FrontendTextTurnPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        conversation = runtime.conversations.get_conversation(conversation_id)
        enforce_frontend_conversation_scope(
            conversation.metadata,
            payload.workspace_id,
            payload.project_id,
            payload.session_id,
        )
        profile = runtime.primary_agent.get_primary(payload.workspace_id)
        result = runtime.chat.submit_turn(
            context,
            conversation_id=conversation_id,
            content=payload.content,
            sender_id="local_chat",
            target_agent_id=payload.target_agent_id or profile.agent_id,
            model_provider_id=payload.model_provider_id,
            model_name=payload.model_name,
            attachments=validated_frontend_attachment_refs(
                runtime,
                conversation_id,
                payload.attachments,
            ),
            idempotency_key=payload.idempotency_key,
            project_id=payload.project_id,
        )
        return {
            "schema": "frontend-v2-text-turn-result-v1",
            "workspace_id": payload.workspace_id,
            "project_id": payload.project_id,
            "session_id": payload.session_id,
            "conversation_id": conversation_id,
            "agent_id": getattr(result, "agent_id", profile.agent_id),
            "result": asdict(result),
            "history": [
                asdict(message)
                for message in runtime.conversations.list_conversation_messages(conversation_id)
            ],
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/turns/stream")
def stream_frontend_text_turn(
    conversation_id: str,
    payload: FrontendTextTurnPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)

    def stream():
        try:
            conversation = runtime.conversations.get_conversation(conversation_id)
            enforce_frontend_conversation_scope(
                conversation.metadata,
                payload.workspace_id,
                payload.project_id,
                payload.session_id,
            )
            profile = runtime.primary_agent.get_primary(payload.workspace_id)
            if runtime.chat.is_frontend_turn_cancelled(payload.idempotency_key):
                yield frontend_stream_event(
                    payload,
                    {
                        "type": "generation_cancelled",
                        "conversation_id": conversation_id,
                        "idempotency_key": payload.idempotency_key,
                    },
                )
                return
            for event in runtime.chat.stream_turn(
                context,
                conversation_id=conversation_id,
                content=payload.content,
                sender_id="local_chat",
                target_agent_id=payload.target_agent_id or profile.agent_id,
                model_provider_id=payload.model_provider_id,
                model_name=payload.model_name,
                attachments=validated_frontend_attachment_refs(
                    runtime,
                    conversation_id,
                    payload.attachments,
                ),
                idempotency_key=payload.idempotency_key,
                project_id=payload.project_id,
            ):
                if runtime.chat.is_frontend_turn_cancelled(payload.idempotency_key):
                    cancel_latest_assistant_message(runtime, context, conversation_id)
                    yield frontend_stream_event(
                        payload,
                        {
                            "type": "generation_cancelled",
                            "conversation_id": conversation_id,
                            "idempotency_key": payload.idempotency_key,
                        },
                    )
                    return
                yield json.dumps(
                    {
                        "schema": "frontend-v2-text-stream-event-v1",
                        "workspace_id": payload.workspace_id,
                        "project_id": payload.project_id,
                        "session_id": payload.session_id,
                        **event,
                    },
                    sort_keys=True,
                ) + "\n"
        except Exception as exc:
            yield json.dumps(
                {
                    "schema": "frontend-v2-text-stream-event-v1",
                    "workspace_id": payload.workspace_id,
                    "project_id": payload.project_id,
                    "session_id": payload.session_id,
                    "type": "generation_failed",
                    "conversation_id": conversation_id,
                    "error": frontend_safe_error(exc),
                },
                sort_keys=True,
            ) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/conversations/{conversation_id}/turns/cancel")
def cancel_frontend_text_turn(
    conversation_id: str,
    payload: FrontendCancelTurnPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        conversation = runtime.conversations.get_conversation(conversation_id)
        enforce_frontend_conversation_scope(
            conversation.metadata,
            payload.workspace_id,
            payload.project_id,
            payload.session_id,
        )
        runtime.chat.cancel_frontend_turn(payload.idempotency_key)
        cancelled_message = cancel_latest_assistant_message(runtime, context, conversation_id)
        return {
            "schema": "frontend-v2-turn-cancel-result-v1",
            "workspace_id": payload.workspace_id,
            "project_id": payload.project_id,
            "session_id": payload.session_id,
            "conversation_id": conversation_id,
            "idempotency_key": payload.idempotency_key,
            "status": "cancel_requested",
            "cancelled_message": asdict(cancelled_message) if cancelled_message else None,
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/conversations/{conversation_id}/attachments/stage")
def stage_frontend_conversation_attachment(
    conversation_id: str,
    payload: FrontendAttachmentStagePayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        conversation = runtime.conversations.get_conversation(conversation_id)
        enforce_frontend_conversation_scope(
            conversation.metadata,
            payload.workspace_id,
            payload.project_id,
            payload.session_id,
        )
        filename = validate_frontend_attachment_metadata(
            payload.filename,
            payload.mime_type,
            payload.size,
        )
        content = decode_frontend_attachment(payload.content_base64, payload.size)
        attachment = runtime.conversations.stage_and_register_attachment(
            context,
            conversation_id,
            filename=filename,
            mime_type=payload.mime_type,
            owner_id=context.actor_id,
            content=content,
        )
        return {
            "schema": "frontend-v2-attachment-stage-result-v1",
            "workspace_id": payload.workspace_id,
            "project_id": payload.project_id,
            "session_id": payload.session_id,
            "conversation_id": conversation_id,
            "attachment": asdict(attachment),
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/transcriptions")
def transcribe_frontend_voice_recording(
    payload: FrontendVoiceTranscriptionPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        profile = runtime.primary_agent.get_primary(payload.workspace_id)
        if payload.conversation_id:
            conversation = runtime.conversations.get_conversation(payload.conversation_id)
            enforce_frontend_conversation_scope(
                conversation.metadata,
                payload.workspace_id,
                payload.project_id,
                payload.session_id,
            )
        settings = runtime.voice.get_settings()
        if not settings.enabled:
            raise ValidationError("voice_disabled: voice transcription is disabled")
        recording = runtime.voice.start_recording(
            session_id=None,
            conversation_id=payload.conversation_id,
            agent_id=profile.agent_id,
            audio_format=payload.audio_format,
        )
        runtime.voice.append_recording_chunk(
            recording.recording_id,
            decode_frontend_audio(payload.audio_base64),
            sequence=0,
            idempotency_key=f"frontend-v2:{recording.recording_id}:0",
        )
        completed = runtime.voice.complete_recording(recording.recording_id)
        result = runtime.voice.complete_voice_message(completed.recording_id)
        transcript = result.text.strip()
        if not transcript:
            raise ValidationError("empty_transcription: STT did not produce text")
        transcribed = runtime.voice.get_recording(completed.recording_id)
        return {
            "schema": "frontend-v2-voice-transcription-v1",
            "workspace_id": payload.workspace_id,
            "project_id": payload.project_id,
            "session_id": payload.session_id,
            "conversation_id": payload.conversation_id,
            "recording_id": completed.recording_id,
            "transcript": transcript,
            "provider_id": transcribed.provider_id,
            "language": result.language,
            "duration_ms": result.duration_ms,
            "status": result.status,
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/conversation-turn")
def run_frontend_voice_conversation_turn(
    payload: FrontendVoiceConversationTurnPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        profile = runtime.primary_agent.get_primary(payload.workspace_id)
        conversation = runtime.conversations.get_conversation(payload.conversation_id)
        enforce_frontend_conversation_scope(
            conversation.metadata,
            payload.workspace_id,
            payload.project_id,
            payload.session_id,
        )
        settings = runtime.voice.get_settings()
        if not settings.enabled:
            raise ValidationError("voice_disabled: voice conversation mode is disabled")
        voice_session = (
            runtime.voice.get_session(payload.voice_session_id)
            if payload.voice_session_id
            else runtime.voice.create_session(
                agent_id=profile.agent_id,
                conversation_id=payload.conversation_id,
                metadata={"source": "frontend_v2_conversation_mode"},
            )
        )
        recording = runtime.voice.start_recording(
            session_id=voice_session.session_id,
            conversation_id=payload.conversation_id,
            agent_id=profile.agent_id,
            audio_format=payload.audio_format,
        )
        if runtime.voice.get_session(voice_session.session_id).status == "idle":
            runtime.voice.transition_session(voice_session.session_id, "listening")
        runtime.voice.transition_session(voice_session.session_id, "recording")
        runtime.voice.append_recording_chunk(
            recording.recording_id,
            decode_frontend_audio(payload.audio_base64),
            sequence=0,
            idempotency_key=f"frontend-v2:{recording.recording_id}:0",
        )
        completed = runtime.voice.complete_recording(recording.recording_id)
        result = runtime.voice.run_conversation_turn(
            voice_session.session_id,
            completed.recording_id,
            idempotency_key=payload.idempotency_key or f"frontend-v2:{completed.recording_id}",
        )
        synthesis = runtime.voice.get_synthesis(result.synthesis_id)
        audio_base64, audio_format = frontend_synthesis_audio(runtime, synthesis.audio_reference)
        page = frontend_recent_history_page(runtime, result.conversation_id, 50)
        return {
            "schema": "frontend-v2-voice-conversation-turn-v1",
            "workspace_id": payload.workspace_id,
            "project_id": payload.project_id,
            "session_id": payload.session_id,
            "voice_session_id": voice_session.session_id,
            "conversation_id": result.conversation_id,
            "recording_id": result.recording_id,
            "transcript": result.transcript,
            "response": result.response,
            "user_message_id": result.user_message_id,
            "assistant_message_id": result.assistant_message_id,
            "synthesis_id": result.synthesis_id,
            "tts": {
                "status": synthesis.status,
                "provider_id": synthesis.provider_id,
                "voice_id": synthesis.voice_id,
                "audio_base64": audio_base64,
                "audio_format": audio_format,
                "duration_ms": synthesis.duration_ms,
            },
            "messages": page["messages"],
            "pagination": page["pagination"],
            "summary": frontend_summary(runtime, result.conversation_id),
            "degraded": [],
            "errors": [],
        }
    except Exception as exc:
        raise api_error(exc) from exc


def frontend_stream_event(payload: FrontendTextTurnPayload, event: dict[str, Any]) -> str:
    return (
        json.dumps(
            {
                "schema": "frontend-v2-text-stream-event-v1",
                "workspace_id": payload.workspace_id,
                "project_id": payload.project_id,
                "session_id": payload.session_id,
                **event,
            },
            sort_keys=True,
        )
        + "\n"
    )


def frontend_history_page(runtime: Any, conversation_id: str, offset: int, limit: int) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 499))
    messages = runtime.conversations.list_conversation_messages(
        conversation_id,
        offset=offset,
        limit=bounded_limit + 1,
    )
    page_messages = messages[:bounded_limit]
    next_offset = offset + len(page_messages)
    return {
        "messages": [asdict(message) for message in page_messages],
        "pagination": {
            "offset": offset,
            "limit": bounded_limit,
            "returned": len(page_messages),
            "has_more": len(messages) > bounded_limit,
            "next_offset": next_offset if len(messages) > bounded_limit else None,
            "has_older": offset > 0,
            "previous_offset": max(0, offset - bounded_limit) if offset > 0 else None,
        },
    }


def frontend_recent_history_page(runtime: Any, conversation_id: str, limit: int) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 500))
    messages = runtime.conversations.list_conversation_messages(
        conversation_id,
        offset=0,
        limit=500,
    )
    offset = max(0, len(messages) - bounded_limit)
    page_messages = messages[offset : offset + bounded_limit]
    return {
        "messages": [asdict(message) for message in page_messages],
        "pagination": {
            "offset": offset,
            "limit": bounded_limit,
            "returned": len(page_messages),
            "has_more": False,
            "next_offset": None,
            "has_older": offset > 0,
            "previous_offset": max(0, offset - bounded_limit) if offset > 0 else None,
            "known_total": len(messages),
        },
    }


def frontend_summary(runtime: Any, conversation_id: str) -> dict[str, Any]:
    return asdict(runtime.conversations.get_conversation_summary(conversation_id))


def cancel_latest_assistant_message(runtime: Any, context: Any, conversation_id: str) -> Any | None:
    messages = runtime.conversations.list_conversation_messages(
        conversation_id,
        offset=0,
        limit=500,
    )
    for message in reversed(messages):
        if message.role == "assistant" and message.status != "cancelled":
            return runtime.conversations.cancel_message(context, message.message_id)
    return None


def decode_frontend_audio(audio_base64: str) -> bytes:
    encoded = audio_base64.strip()
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("invalid_audio: audio payload is not valid base64") from exc
    if not decoded:
        raise ValidationError("empty_recording: audio payload is empty")
    return decoded


def validate_frontend_attachment_metadata(filename: str, mime_type: str, size: int) -> str:
    normalized = filename.strip()
    if not normalized or "/" in normalized or "\\" in normalized or ".." in normalized:
        raise ValidationError("attachment_invalid: invalid filename")
    if not SAFE_ATTACHMENT_NAME.fullmatch(normalized):
        raise ValidationError("attachment_invalid: unsupported filename")
    if size <= 0:
        raise ValidationError("attachment_invalid: empty files are not supported")
    if size > 25 * 1024 * 1024:
        raise ValidationError("attachment_invalid: file exceeds 25 MiB")
    if mime_type not in SUPPORTED_ATTACHMENT_MIME_TYPES:
        raise ValidationError("attachment_invalid: unsupported file type")
    return normalized


def decode_frontend_attachment(content_base64: str, expected_size: int) -> bytes:
    encoded = content_base64.strip()
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("attachment_invalid: attachment payload is not valid base64") from exc
    if len(decoded) != expected_size:
        raise ValidationError("attachment_invalid: attachment size does not match payload")
    if not decoded:
        raise ValidationError("attachment_invalid: empty files are not supported")
    return decoded


def validated_frontend_attachment_refs(
    runtime: Any,
    conversation_id: str,
    refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not refs:
        return []
    registered = {
        item.get("attachment_id"): item
        for item in runtime.conversations.list_attachments(conversation_id)
    }
    validated: list[dict[str, Any]] = []
    for ref in refs:
        attachment_id = ref.get("attachment_id")
        if not isinstance(attachment_id, str) or not attachment_id:
            raise ValidationError("attachment_invalid: attachment_id is required")
        existing = registered.get(attachment_id)
        if existing is None:
            raise ValidationError(
                "attachment_scope_mismatch: attachment is not registered for this conversation"
            )
        validated.append(
            {
                "attachment_id": existing["attachment_id"],
                "filename": existing["filename"],
                "mime_type": existing["mime_type"],
                "size": existing["size"],
                "storage_ref": existing["storage_ref"],
                "checksum": existing["checksum"],
            }
        )
    return validated


def frontend_synthesis_audio(runtime: Any, audio_reference: str | None) -> tuple[str | None, str | None]:
    if not audio_reference:
        return None, None
    synthesis_id = audio_reference.rsplit("/", 1)[-1].removesuffix(".wav")
    audio_base64 = runtime.voice.read_synthesis_audio_base64(synthesis_id)
    if not audio_base64:
        raise ValidationError("tts_audio_unavailable: synthesized audio is unavailable")
    return audio_base64, "audio/wav"


def frontend_model_options(runtime: Any) -> list[dict[str, Any]]:
    providers = {provider.provider_id: provider for provider in runtime.model_hub.list_providers()}
    options: list[dict[str, Any]] = []
    for model in runtime.model_hub.list_catalog():
        provider = providers.get(model.provider)
        provider_status = provider.status if provider else "unknown"
        provider_active = bool(provider.active) if provider else False
        usable = (
            model.status in {"available", "configured"}
            and model.type in {"chat", "gguf"}
            and (model.chat_usable or model.status == "configured")
        )
        if not usable:
            continue
        options.append(
            {
                "provider_id": model.provider,
                "provider_status": provider_status,
                "provider_active": provider_active,
                "model_id": model.name,
                "model_status": model.status,
                "runtime": model.runtime,
                "origin": model.origin,
                "availability_state": model.availability_state,
                "is_default": model.is_default,
            }
        )
    return options


def frontend_default_model_selection(runtime: Any) -> dict[str, str | None]:
    options = frontend_model_options(runtime)
    if not options:
        return {"provider_id": None, "model_id": None}
    default_option = next((option for option in options if option.get("is_default")), None)
    if default_option:
        return {
            "provider_id": default_option["provider_id"],
            "model_id": default_option["model_id"],
        }
    defaults = runtime.model_hub.get_defaults()
    if defaults.default_provider and defaults.default_chat_model:
        governed = next(
            (
                option
                for option in options
                if option["provider_id"] == defaults.default_provider
                and option["model_id"] == defaults.default_chat_model
            ),
            None,
        )
        if governed:
            return {"provider_id": governed["provider_id"], "model_id": governed["model_id"]}
    lmstudio_default = runtime.lmstudio.load_config().default_model if getattr(runtime, "lmstudio", None) else None
    if lmstudio_default:
        governed = next(
            (
                option
                for option in options
                if option["provider_id"] == "lmstudio" and option["model_id"] == lmstudio_default
            ),
            None,
        )
        if governed:
            return {"provider_id": governed["provider_id"], "model_id": governed["model_id"]}
    return {"provider_id": None, "model_id": None}


def validate_frontend_model_selection(
    runtime: Any,
    provider_id: str | None,
    model_id: str | None,
) -> None:
    if not provider_id and not model_id:
        # A Primary Agent identity is still valid without a configured model;
        # conversation readiness is reported as degraded and Settings owns setup.
        return
    if not provider_id or not model_id:
        raise ValidationError("invalid_model_selection: provider and model must be selected together")
    options = frontend_model_options(runtime)
    if not any(
        option["provider_id"] == provider_id and option["model_id"] == model_id
        for option in options
    ):
        raise ValidationError("invalid_model_selection: provider/model is not usable")


def configure_frontend_selected_provider(
    runtime: Any,
    provider_id: str | None,
    model_id: str | None,
) -> None:
    if provider_id != "lmstudio" or not model_id:
        return
    provider_settings = getattr(runtime, "provider_settings", None)
    if provider_settings is None:
        raise ValidationError("provider_configuration_unavailable: LM Studio settings are unavailable")
    provider = next(
        (item for item in runtime.model_hub.list_providers() if item.provider_id == "lmstudio"),
        None,
    )
    endpoint = getattr(provider, "endpoint", None) or "http://127.0.0.1:1234/v1"
    provider_settings.update_setting(
        "lmstudio_local",
        enabled=True,
        endpoint=endpoint,
        default_model=model_id,
    )


def enforce_frontend_conversation_scope(
    metadata: dict[str, Any],
    workspace_id: str,
    project_id: str | None,
    session_id: str | None,
) -> None:
    expected = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "session_id": session_id,
    }
    for key, value in expected.items():
        recorded = metadata.get(key)
        if recorded is not None and value is not None and recorded != value:
            raise ValidationError(f"scope_mismatch: conversation {key} does not match request")


def frontend_conversation_matches_scope(
    metadata: dict[str, Any],
    workspace_id: str,
    project_id: str | None,
    session_id: str | None,
) -> bool:
    recorded_workspace = metadata.get("workspace_id")
    if recorded_workspace is not None and recorded_workspace != workspace_id:
        return False
    recorded_project = metadata.get("project_id")
    if project_id is not None and recorded_project not in {None, project_id}:
        return False
    recorded_session = metadata.get("session_id")
    if session_id is not None and recorded_session not in {None, session_id}:
        return False
    return True


def frontend_conversation_matches_deletion_scope(
    metadata: dict[str, Any],
    workspace_id: str,
    project_id: str | None,
    session_id: str | None,
) -> bool:
    return frontend_conversation_matches_scope(metadata, workspace_id, project_id, session_id)


def frontend_conversation_index_item(runtime: Any, conversation: Any) -> dict[str, Any]:
    messages = runtime.conversations.list_conversation_messages(
        conversation.conversation_id,
        offset=0,
        limit=500,
    )
    last_message = messages[-1] if messages else None
    preview_message = next(
        (
            message
            for message in reversed(messages)
            if getattr(message, "role", "") == "user"
            and str(message.payload.get("body") or "").strip()
        ),
        last_message,
    )
    preview = ""
    if preview_message is not None:
        preview = str(preview_message.payload.get("body") or "").strip()
        if len(preview) > 140:
            preview = f"{preview[:137]}..."
    return {
        "conversation": asdict(conversation),
        "message_count": len(messages),
        "last_message": asdict(last_message) if last_message else None,
        "preview": preview,
    }


def frontend_safe_error(exc: Exception) -> dict[str, str]:
    return {
        "code": type(exc).__name__,
        "message": str(exc),
    }
