from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from synapse.agents.admin import AgentAdminRuntime
from synapse.agents.runtime import AgentRuntime
from synapse.chat.rag_policy import RetrievalDecision, decide_project_knowledge_retrieval
from synapse.chat.routing import ChatModelSelection, ComplexMissionPort, PrimaryModelRoutingPort
from synapse.chat.streaming import stream_response
from synapse.context.loader import ContextLoader, ContextSection
from synapse.conversations.errors import ConversationError
from synapse.conversations.runtime import ConversationRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import load_structured_file
from synapse.memory.store import MemoryStore
from synapse.model_providers.lmstudio import LMStudioProviderRuntime
from synapse.models.types import ModelRequest
from synapse.observability.correlation import (
    correlation_scope,
    current_correlation,
    current_correlation_fields,
    new_correlation,
)
from synapse.presence.runtime import PresenceRuntime
from synapse.retrieval_intent import (
    RetrievalDirective,
    detect_text_retrieval_intent,
    normalize_retrieval_directive,
)

if TYPE_CHECKING:
    from synapse.context_fusion.runtime import ContextFusionRuntime
    from synapse.model_hub.runtime import ModelHubRuntime


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None
    parent_id: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class ChatSession:
    id: str
    agent_id: str
    project_id: str | None
    messages: list[ChatMessage] = field(default_factory=list)
    correlation_id: str | None = None
    causation_id: str | None = None
    parent_id: str | None = None
    source: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class ChatTurnResult:
    session_id: str
    agent_id: str
    response: str
    message: ChatMessage
    command: dict[str, Any] | None = None
    model: dict[str, Any] | None = None
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class LocalChatResult:
    session_id: str
    conversation_id: str | None
    agent_id: str
    response: str
    message: ChatMessage
    model: dict[str, Any]
    policy: dict[str, Any]


class ChatRuntime:
    stream_operation = staticmethod(stream_response)

    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        context_loader: ContextLoader,
        agent_runtime: AgentRuntime,
        commands: Any,
        presence: PresenceRuntime | None = None,
        admin: AgentAdminRuntime | None = None,
        conversations: ConversationRuntime | None = None,
        lmstudio: LMStudioProviderRuntime | None = None,
        model_hub: ModelHubRuntime | None = None,
        memory: MemoryStore | None = None,
        context_fusion: ContextFusionRuntime | None = None,
        models=None,
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.context_loader = context_loader
        self.agent_runtime = agent_runtime
        self.commands = commands
        self.presence = presence
        self.admin = admin
        self.conversations = conversations
        self.lmstudio = lmstudio
        self.model_hub = model_hub
        self.memory = memory
        self.context_fusion = context_fusion
        self.models = models
        self.primary_model_routing: PrimaryModelRoutingPort | None = None
        self.swarm_interactions: Any | None = None
        self.complex_missions: ComplexMissionPort | None = None
        self._cancelled_frontend_turns: set[str] = set()

    def cancel_frontend_turn(self, idempotency_key: str) -> None:
        if idempotency_key.strip():
            self._cancelled_frontend_turns.add(idempotency_key)

    def is_frontend_turn_cancelled(self, idempotency_key: str | None) -> bool:
        return bool(idempotency_key and idempotency_key in self._cancelled_frontend_turns)

    def submit_turn(
        self,
        context: PermissionContext,
        *,
        content: str,
        conversation_id: str | None = None,
        sender_id: str = "local_chat",
        target_agent_id: str | None = None,
        model_provider_id: str | None = None,
        model_name: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        project_id: str | None = None,
        workspace_id: str = "default",
        session_id: str | None = None,
        retrieval_intent: RetrievalDirective | dict[str, str] | None = None,
        manual_model_selection: bool | None = None,
    ) -> ChatTurnResult | LocalChatResult:
        if not content.strip():
            raise ValidationError("invalid_message: message content is required")
        directive = self._resolve_retrieval_directive(content, retrieval_intent)
        project_id = project_id or (workspace_id if workspace_id != "default" else None)
        retrieval_decision = self._retrieval_decision(directive, project_id)
        content_for_model = directive.query if directive.intent.value != "none" else content
        correlation = current_correlation() or new_correlation(
            source="conversation_turn",
            session_id=conversation_id,
            agent_id=target_agent_id,
        )
        with correlation_scope(correlation):
            self.event_bus.emit(
                "conversation.turn_started",
                context.actor_id,
                {"conversation_id": conversation_id, "agent_id": target_agent_id},
            )
            if not target_agent_id:
                return self.local_chat(
                    context,
                    content_for_model,
                    conversation_id=conversation_id,
                    project_id=project_id,
                    model_provider_id=model_provider_id,
                    model_name=model_name,
                    retrieval_decision=retrieval_decision,
                    manual_model_selection=manual_model_selection,
                )
            if not self.conversations:
                raise ValidationError("persistence_failed: conversation runtime is unavailable")
            target = target_agent_id.strip().lower()
            if conversation_id:
                conversation = self.conversations.get_conversation(conversation_id)
                if target not in conversation.participants:
                    conversation = self.conversations.add_participant(
                        context, conversation_id, target, "agent", "assistant"
                    )
                if sender_id not in conversation.participants:
                    self.conversations.add_participant(
                        context, conversation_id, sender_id, "user", "user"
                    )
            else:
                conversation = self.conversations.create_conversation(
                    context,
                    [sender_id, target],
                    title=f"Chat with {target}",
                    metadata={"source": "chat"},
                )
                conversation_id = conversation.conversation_id
            incoming = self.conversations.send_message(
                context,
                sender_agent_id=sender_id,
                receiver_agent_id=target,
                payload={"body": content, "role": "user"},
                conversation_id=conversation_id,
                content_parts=[{"type": "text", "content": content, "metadata": {}}],
                attachments=attachments,
                idempotency_key=idempotency_key,
                status="completed",
                metadata={"source": "chat", "role": "user"},
            )
            try:
                self.event_bus.emit(
                    "conversation.generation_started",
                    context.actor_id,
                    {"conversation_id": conversation_id, "message_id": incoming.message_id},
                )
                swarm_runtime = self.swarm_interactions
                swarm_interaction = swarm_runtime.prepare(
                    text=content,
                    conversation_id=conversation_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    session_id=session_id,
                    actor_id=context.actor_id,
                    idempotency_key=idempotency_key,
                ) if swarm_runtime else None
                if swarm_interaction is not None:
                    assert swarm_runtime is not None
                    command_type = "swarm_confirmation" if swarm_interaction.status == "pending" else "swarm_execution"
                    completed_interaction = (
                        swarm_runtime.execute_accepted(swarm_interaction.request_id)
                        if swarm_interaction.status == "accepted"
                        else swarm_interaction
                    )
                    if completed_interaction.status == "pending":
                        response_text = (
                            "Este pedido de Swarm precisa da sua confirmação. "
                            f"Recomendo {completed_interaction.recommended_agents} agentes temporários."
                        )
                    else:
                        response_text = (
                            f"Swarm criado para a tarefa. Estado: "
                            f"{completed_interaction.execution_status or completed_interaction.status}."
                        )
                        if completed_interaction.outputs:
                            response_text += "\n\n" + "\n\n".join(completed_interaction.outputs)
                        if completed_interaction.execution_status == "waiting_approval":
                            response_text += "\n\nA tarefa ainda não foi concluída. Há alterações aguardando sua aprovação."
                            for approval_id in completed_interaction.approval_ids:
                                response_text += f"\nRevise em /approvals; para autorizar esta alteração: /approve {approval_id}"
                    command = {
                        "type": command_type,
                        "request": asdict(completed_interaction),
                        "options": ["accept_recommended", "keep_requested", "cancel"],
                    }
                    response = self.conversations.send_message(
                        context,
                        sender_agent_id=target,
                        receiver_agent_id=sender_id,
                        payload={"body": response_text, "role": "assistant", "interaction": command},
                        conversation_id=conversation_id,
                        status="completed",
                        parent_message_id=incoming.message_id,
                        metadata={"source": "chat", "role": "assistant", "interaction": command},
                    )
                    self.event_bus.emit(
                        "conversation.generation_completed",
                        context.actor_id,
                        {"conversation_id": conversation_id, "message_id": response.message_id},
                    )
                    return ChatTurnResult(
                        session_id=conversation_id,
                        agent_id=target,
                        response=response_text,
                        message=ChatMessage("assistant", response_text, metadata={"interaction": command}),
                        command=command,
                    )
                result = self.send_message(
                    context,
                    target,
                    content_for_model,
                    project_id=project_id,
                    session_id=conversation_id,
                    model_provider_override=model_provider_id,
                    model_override=model_name,
                    retrieval_decision=retrieval_decision,
                    manual_model_selection=manual_model_selection,
                )
                response = self.conversations.send_message(
                    context,
                    sender_agent_id=target,
                    receiver_agent_id=sender_id,
                    payload={"body": result.response, "role": "assistant"},
                    conversation_id=conversation_id,
                    status="completed",
                    parent_message_id=incoming.message_id,
                    model_metadata=result.model or {},
                    tool_calls=list(result.message.metadata.get("tool_results", [])),
                    metadata={"source": "chat", "role": "assistant"},
                )
                self.event_bus.emit(
                    "conversation.generation_completed",
                    context.actor_id,
                    {"conversation_id": conversation_id, "message_id": response.message_id},
                )
                return result
            except Exception as exc:
                self.conversations.fail_message(context, incoming.message_id, str(exc))
                self.event_bus.emit(
                    "conversation.generation_failed",
                    context.actor_id,
                    {"conversation_id": conversation_id, "error_type": type(exc).__name__},
                )
                raise

    def generate_conversation_summary(
        self,
        context: PermissionContext,
        conversation_id: str,
        agent_id: str | None = None,
    ):
        if not self.conversations:
            raise ValidationError("summary_failed: conversation runtime is unavailable")
        conversation = self.conversations.get_conversation(conversation_id)
        selected_agent = agent_id or next(
            (item for item in conversation.participants if item != "local_chat"), None
        )
        if not selected_agent:
            raise ValidationError("model_not_available: summary requires a configured agent")
        context_payload = self.conversations.prepare_context(
            conversation_id, agent_id=selected_agent, options={"max_messages": 100}
        )
        messages = context_payload["messages"]
        if not messages:
            raise ValidationError("summary_failed: conversation has no messages")
        transcript = "\n".join(
            f"{item['sender_agent_id']}: {item['payload'].get('body', '')}" for item in messages
        )
        result = self.send_message(
            context,
            selected_agent,
            "Summarize this conversation faithfully. Do not invent facts.\n\n" + transcript,
            session_id=f"summary-{conversation_id}",
        )
        if not result.response.strip():
            raise ValidationError("empty_model_response: summary provider returned no content")
        model = result.model or {}
        summary = self.conversations.update_conversation_summary(
            conversation_id,
            result.response,
            metadata={"generated_by": "model"},
            model=model.get("model"),
            provider=model.get("provider"),
        )
        self.event_bus.emit(
            "conversation.summary.generated",
            context.actor_id,
            {"conversation_id": conversation_id, "agent_id": selected_agent, "model": model},
        )
        return summary

    def stream_turn(self, context: PermissionContext, **options: Any):
        conversation_id = options.get("conversation_id")
        yield {"type": "turn_started", "conversation_id": conversation_id}
        yield {"type": "generation_started", "conversation_id": conversation_id}
        try:
            result = self.submit_turn(context, **options)
            command = getattr(result, "command", None)
            if command and command.get("type") in {"swarm_confirmation", "swarm_execution"}:
                yield {
                    "type": "confirmation_required" if command["type"] == "swarm_confirmation" else "swarm_started",
                    "conversation_id": conversation_id,
                    "data": command,
                }
            for kind, content in stream_response(lambda: result.response):
                yield {
                    "type": kind, "conversation_id": conversation_id,
                    "content": content, "streaming_mode": "progressive",
                }
        except Exception as exc:
            yield {
                "type": "generation_failed",
                "conversation_id": conversation_id,
                "error": {"code": type(exc).__name__, "message": str(exc)},
            }

    def send_message(
        self,
        context: PermissionContext,
        agent_id: str,
        user_message: str,
        project_id: str | None = None,
        session_id: str | None = None,
        model_provider_override: str | None = None,
        model_override: str | None = None,
        retrieval_decision: RetrievalDecision | None = None,
        manual_model_selection: bool | None = None,
    ) -> ChatTurnResult:
        if self.admin:
            self.admin.assert_agent_runnable(agent_id)
        session = self._load_or_create_session(session_id, agent_id, project_id)
        project_id = project_id or session.project_id
        correlation = current_correlation() or new_correlation(
            source="chat",
            session_id=session.id,
            agent_id=agent_id,
        )
        with correlation_scope(correlation):
            if retrieval_decision is None:
                directive = self._resolve_retrieval_directive(user_message, None)
                retrieval_decision = self._retrieval_decision(directive, project_id)
                if directive.intent.value != "none":
                    user_message = directive.query
            return self._send_message(
                context=context,
                agent_id=agent_id,
                user_message=user_message,
                project_id=project_id,
                session=session,
                model_provider_override=model_provider_override,
                model_override=model_override,
                retrieval_decision=retrieval_decision,
                manual_model_selection=manual_model_selection,
            )

    def _send_message(
        self,
        context: PermissionContext,
        agent_id: str,
        user_message: str,
        project_id: str | None,
        session: ChatSession,
        model_provider_override: str | None = None,
        model_override: str | None = None,
        retrieval_decision: RetrievalDecision | None = None,
        manual_model_selection: bool | None = None,
    ) -> ChatTurnResult:
        self._set_presence(
            agent_id,
            "listening",
            "Receiving user message",
            session_id=session.id,
            actor_id=context.actor_id,
        )
        self.event_bus.emit(
            "chat.message_received",
            context.actor_id,
            {
                "session_id": session.id,
                "agent_id": agent_id,
                "project_id": project_id,
            },
        )

        user_chat_message = ChatMessage(
            role="user",
            content=user_message,
            **current_correlation_fields(),
        )

        if user_message.strip().startswith("/"):
            self._set_presence(
                agent_id,
                "thinking",
                "Executing command",
                session_id=session.id,
                actor_id=context.actor_id,
            )
            session = self._append_message(session, user_chat_message, agent_id, project_id)
            result = self.commands.execute(context, user_message, source_agent_id=agent_id)
            assistant_message = ChatMessage(
                role="assistant",
                content=result.output,
                metadata={"command": asdict(result)},
                **current_correlation_fields(),
            )
            session = self._append_message(session, assistant_message, agent_id, project_id)
            self.event_bus.emit(
                "chat.response_generated",
                context.actor_id,
                {
                    "session_id": session.id,
                    "agent_id": agent_id,
                    "mode": "command",
                    "command": result.command,
                    "status": result.status,
                },
            )
            self._set_presence(
                agent_id,
                "speaking",
                "Command response generated",
                session_id=session.id,
                actor_id=context.actor_id,
            )
            self._persist_session(session, context.actor_id)
            self._set_presence(
                agent_id,
                "idle",
                "Chat turn completed",
                session_id=session.id,
                actor_id=context.actor_id,
            )
            return ChatTurnResult(
                session_id=session.id,
                agent_id=agent_id,
                response=result.output,
                message=assistant_message,
                command=asdict(result),
            )

        manual = bool(model_provider_override or model_override) if manual_model_selection is None else manual_model_selection
        if not manual:
            planned_turn = self._plan_complex_turn(context, agent_id, user_message, session)
            if planned_turn is not None:
                return planned_turn
        self._set_presence(
            agent_id,
            "thinking",
            "Loading context",
            session_id=session.id,
            actor_id=context.actor_id,
        )
        loaded_context = self._load_context(
            context,
            agent_id,
            user_message,
            session,
            project_id,
            retrieval_decision=retrieval_decision,
        )
        self.event_bus.emit(
            "chat.context_loaded",
            context.actor_id,
            {
                "session_id": session.id,
                "agent_id": agent_id,
                "sections": len(loaded_context.sections),
            },
        )
        routed = (None if manual else
                  self._primary_chat_selection(context, agent_id, user_message, session.id))
        if routed is not None:
            model_provider_override, model_override = routed.provider, routed.model
        agent_result = self.agent_runtime.run(
            context=context,
            agent_id=agent_id,
            loaded_context=loaded_context,
            user_message=user_message,
            session_id=session.id,
            project_id=project_id,
            model_provider_override=model_provider_override,
            model_override=model_override,
        )
        if routed is not None:
            if agent_result.model.get("provider") != routed.provider or agent_result.model.get("model") != routed.model:
                raise ValidationError("A resposta não corresponde ao modelo escolhido pelo MoM.")
            agent_result.model["mom"] = {"operation": routed.operation, "revision": routed.revision}
        assistant_message = ChatMessage(
            role="assistant",
            content=agent_result.response,
            metadata={
                "model": agent_result.model,
                "tool_calling": agent_result.tool_calling,
                "tool_results": [asdict(tool_result) for tool_result in agent_result.tool_results],
                "tool_calling_result": agent_result.tool_calling_result,
            },
            **current_correlation_fields(),
        )
        session = self._append_message(session, user_chat_message, agent_id, project_id)
        session = self._append_message(session, assistant_message, agent_id, project_id)
        self.event_bus.emit(
            "chat.response_generated",
            context.actor_id,
            {
                "session_id": session.id,
                "agent_id": agent_id,
                "mode": "agent",
                "model": agent_result.model,
            },
        )
        awaiting_approval = any(
            tool_result.status == "awaiting_approval" for tool_result in agent_result.tool_results
        )
        if awaiting_approval:
            pending = next(
                result
                for result in agent_result.tool_results
                if result.status == "awaiting_approval"
            )
            self._set_presence(
                agent_id,
                "waiting_approval",
                f"Waiting approval for {pending.request.name}",
                session_id=session.id,
                approval_id=pending.approval_id,
                actor_id=context.actor_id,
            )
        else:
            self._set_presence(
                agent_id,
                "speaking",
                "Response generated",
                session_id=session.id,
                actor_id=context.actor_id,
            )
        self._persist_session(session, context.actor_id)
        if not awaiting_approval:
            self._set_presence(
                agent_id,
                "idle",
                "Chat turn completed",
                session_id=session.id,
                actor_id=context.actor_id,
            )
        return ChatTurnResult(
            session_id=session.id,
            agent_id=agent_id,
            response=agent_result.response,
            message=assistant_message,
            model=agent_result.model,
            context=loaded_context.to_dict(),
        )

    def get_session(self, session_id: str) -> ChatSession:
        path = self._session_path(session_id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ChatSession(
            id=raw["id"],
            agent_id=raw["agent_id"],
            project_id=raw.get("project_id"),
            messages=[self._message_from_raw(message) for message in raw.get("messages", [])],
            correlation_id=raw.get("correlation_id"),
            causation_id=raw.get("causation_id"),
            parent_id=raw.get("parent_id"),
            source=raw.get("source"),
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
        )

    def load_local_chat_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.data_dir.resolve("config/local_chat_policy.yaml"))
        policy = {
            "enabled": False,
            "provider_id": "lmstudio_local",
            "require_explicit_provider": True,
            "persist_conversations": True,
            "max_context_messages": 10,
            "include_conversation_summary": True,
            "include_multimodal_context": False,
        }
        policy.update(raw.get("local_chat", raw))
        self.event_bus.emit(
            "local_chat.policy_loaded",
            "chat",
            {
                "enabled": bool(policy.get("enabled", False)),
                "provider_id": policy.get("provider_id"),
                "policy_path": str(self.data_dir.resolve("config/local_chat_policy.yaml")),
            },
        )
        return policy

    def local_chat(
        self,
        context: PermissionContext,
        message: str,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        session_id: str | None = None,
        project_id: str | None = None,
        model_provider_id: str | None = None,
        model_name: str | None = None,
        retrieval_decision: RetrievalDecision | None = None,
        manual_model_selection: bool | None = None,
    ) -> LocalChatResult:
        policy = self.load_local_chat_policy()
        if not policy.get("enabled", False):
            raise ValidationError(
                "Habilite local_chat em config/local_chat_policy.yaml (local_chat.enabled=true)."
            )
        manual = bool(model_name or model_provider_id) if manual_model_selection is None else manual_model_selection
        if not manual and self.complex_missions is not None:
            planning_session = self._load_or_create_session(
                session_id or conversation_id, agent_id or self._default_agent_id(), project_id)
            planned_turn = self._plan_complex_turn(context, agent_id, message, planning_session)
            if planned_turn is not None:
                conversation_id = self._ensure_local_conversation(
                    context, planned_turn.agent_id, conversation_id,
                    enabled=bool(policy.get("persist_conversations", True)),
                )
                if conversation_id:
                    self._persist_local_conversation_messages(
                        context, planned_turn.agent_id, conversation_id, message, planned_turn.response,
                    )
                return LocalChatResult(planned_turn.session_id, conversation_id, planned_turn.agent_id,
                                       planned_turn.response, planned_turn.message, {}, policy)
        if retrieval_decision is None:
            directive = self._resolve_retrieval_directive(message, None)
            retrieval_decision = self._retrieval_decision(directive, project_id)
            if directive.intent.value != "none":
                message = directive.query
        routed = (None if manual else
                  self._primary_chat_selection(context, agent_id, message, conversation_id))
        selection = ({"provider_id": routed.provider, "model_name": routed.model} if routed is not None
                     else self._resolve_local_chat_model(model_provider_id, model_name, policy))
        if not selection["provider_id"]:
            raise ValidationError("Selecione um provider válido para local chat.")
        if not selection["model_name"]:
            raise ValidationError("Selecione um modelo disponível.")
        direct_route = not bool((agent_id or "").strip())
        target_agent_id = (routed.agent_id if routed else (agent_id or self._default_agent_id())).strip().lower()

        self.event_bus.emit(
            "local_chat.selection_resolved",
            "chat",
            {
                "provider_id": selection["provider_id"],
                "model_name": selection["model_name"],
                "policy_path": str(self.data_dir.resolve("config/local_chat_policy.yaml")),
            },
        )

        if self.admin:
            self.admin.assert_agent_runnable(target_agent_id)

        conversation_id = self._ensure_local_conversation(
            context,
            target_agent_id,
            conversation_id,
            enabled=bool(policy.get("persist_conversations", True)),
        )
        storage_agent_id = target_agent_id
        if direct_route and conversation_id and self.conversations:
            try:
                existing_conversation = self.conversations.get_conversation(conversation_id)
                if existing_conversation.participants:
                    storage_agent_id = existing_conversation.participants[0]
            except Exception:
                storage_agent_id = target_agent_id

        session = self._load_or_create_session(
            session_id or conversation_id, storage_agent_id, project_id
        )
        project_id = project_id or session.project_id
        correlation = current_correlation() or new_correlation(
            source="local_chat",
            session_id=session.id,
            agent_id=storage_agent_id,
        )
        with correlation_scope(correlation):
            provider_config = self.lmstudio.load_config() if self.lmstudio else None
            if provider_config is not None:
                self.event_bus.emit(
                    "local_chat.provider_config_loaded",
                    "chat",
                    {
                        "enabled": provider_config.enabled,
                        "base_url": provider_config.base_url,
                        "default_model": provider_config.default_model,
                    },
                )
            if selection["provider_id"] in {"lmstudio", "lmstudio_local"}:
                health = self.lmstudio.health() if self.lmstudio else None
                if health is None:
                    raise ValidationError("Abra o LM Studio Server.")
                self.event_bus.emit(
                    "local_chat.endpoint_status",
                    "chat",
                    {
                        "provider_id": selection["provider_id"],
                        "available": health.available,
                        "message": health.message,
                        "endpoint": provider_config.base_url if provider_config else None,
                    },
                )
                if not health.available:
                    if "disabled in config/lmstudio_provider.yaml" in (health.message or ""):
                        raise ValidationError(
                            "Habilite LM Studio em config/lmstudio_provider.yaml (lmstudio.enabled=true)."
                        )
                    raise ValidationError("Abra o LM Studio Server.")
                server_models = self._lmstudio_server_model_ids()
                self.event_bus.emit(
                    "local_chat.models_from_server",
                    "chat",
                    {
                        "count": len(server_models),
                        "models": sorted(server_models),
                    },
                )
                if not selection["model_name"] or selection["model_name"] not in server_models:
                    raise ValidationError(
                        "Carregue um modelo no LM Studio e selecione um modelo disponível."
                    )

            try:
                self.event_bus.emit(
                    "local_chat.request_payload",
                    "chat",
                    {
                        "provider_id": selection["provider_id"],
                        "model_name": selection["model_name"],
                        "agent_id": target_agent_id,
                        "conversation_id": conversation_id,
                        "session_id": session.id,
                        "project_id": project_id,
                        "message_length": len(message),
                    },
                )
                self.event_bus.emit(
                    "local_chat.thinking",
                    "chat",
                    {
                        "provider_id": selection["provider_id"],
                        "model_name": selection["model_name"],
                        "agent_id": target_agent_id,
                        "conversation_id": conversation_id,
                        "session_id": session.id,
                        "project_id": project_id,
                        "status": "processing",
                        "phase": "prompt_processing",
                        "current_operation": "Prompt processing",
                        "current_task": "Preparing model context",
                    },
                )
                user_chat_message = ChatMessage(
                    role="user",
                    content=message,
                    metadata={"local_chat": True, "conversation_id": conversation_id},
                    **current_correlation_fields(),
                )
                if direct_route:
                    if not self.models:
                        raise ValidationError("provider_unavailable: model router is unavailable")
                    provider_settings = (
                        self.models.system_config.get("models", {})
                        .get("providers", {})
                        .get(selection["provider_id"], {})
                    )
                    self.event_bus.emit(
                        "local_chat.generating",
                        "chat",
                        {
                            "provider_id": selection["provider_id"],
                            "model_name": selection["model_name"],
                            "agent_id": target_agent_id,
                            "conversation_id": conversation_id,
                            "session_id": session.id,
                            "project_id": project_id,
                            "status": "processing",
                            "phase": "generating",
                            "current_operation": "Generating response",
                            "current_task": "Model is producing output",
                        },
                    )
                    loaded_context = self._load_context(
                        context, target_agent_id, message, session, project_id,
                        max_history_items=int(policy.get("max_context_messages", 10)),
                        retrieval_decision=retrieval_decision,
                    )
                    agent_result = self.agent_runtime.run(
                        context=context, agent_id=target_agent_id,
                        loaded_context=loaded_context, user_message=message,
                        session_id=session.id, project_id=project_id,
                        model_request=ModelRequest(
                            agent_id=target_agent_id,
                            provider=selection["provider_id"],
                            model=selection["model_name"],
                            base_url=provider_settings.get("base_url")
                            or provider_settings.get("endpoint"),
                            user_message=message,
                            context=loaded_context.to_dict(),
                            max_tokens=256 if selection["provider_id"] == "synapse_local" else None,
                            timeout_seconds=(
                                max(float(provider_settings.get("timeout_seconds", 60)), 240.0)
                                if selection["provider_id"] == "synapse_local"
                                else float(provider_settings.get("timeout_seconds", 60))
                            ),
                            api_key=provider_settings.get("api_key"),
                            headers=dict(provider_settings.get("headers", {})),
                            metadata={
                                "agent_id": target_agent_id,
                                "conversation_id": conversation_id,
                                "session_id": session.id,
                                "project_id": project_id,
                            },
                        )
                    )
                else:
                    loaded_context = self._load_context(
                        context,
                        target_agent_id,
                        message,
                        session,
                        project_id,
                        max_history_items=int(policy.get("max_context_messages", 10)),
                        retrieval_decision=retrieval_decision,
                    )
                    agent_result = self.agent_runtime.run(
                        context=context,
                        agent_id=target_agent_id,
                        loaded_context=loaded_context,
                        user_message=message,
                        session_id=session.id,
                        project_id=project_id,
                        model_provider_override=selection["provider_id"],
                        model_override=selection["model_name"],
                    )
            except Exception as exc:
                self.event_bus.emit(
                    "local_chat.request_failed",
                    "chat",
                    {
                        "provider_id": selection["provider_id"],
                        "model_name": selection["model_name"],
                        "error": str(exc),
                    },
                )
                raise
            self.event_bus.emit(
                "local_chat.endpoint_selected",
                "chat",
                {
                    "provider_id": selection["provider_id"],
                    "model_name": selection["model_name"],
                    "endpoint": provider_config.base_url if provider_config else None,
                },
            )
            if routed is not None:
                if agent_result.model.get("provider") != routed.provider or agent_result.model.get("model") != routed.model:
                    raise ValidationError("A resposta não corresponde ao modelo escolhido pelo MoM.")
                agent_result.model["mom"] = {"operation": routed.operation, "revision": routed.revision}
            assistant_message = ChatMessage(
                role="assistant",
                content=agent_result.response,
                metadata={
                    "local_chat": True,
                    "conversation_id": conversation_id,
                    "model": agent_result.model,
                    "tool_results": [asdict(item) for item in agent_result.tool_results],
                },
                **current_correlation_fields(),
            )
            session = self._append_message(session, user_chat_message, storage_agent_id, project_id)
            session = self._append_message(session, assistant_message, storage_agent_id, project_id)
            self._persist_session(session, context.actor_id)
            if conversation_id:
                self._persist_local_conversation_messages(
                    context,
                    storage_agent_id,
                    conversation_id,
                    message,
                    agent_result.response,
                )
            self.event_bus.emit(
                "local_chat.completed",
                context.actor_id,
                {
                    "session_id": session.id,
                    "conversation_id": conversation_id,
                    "agent_id": target_agent_id,
                    "provider_id": selection["provider_id"],
                    "model_name": selection["model_name"],
                    "model": selection["model_name"],
                    "status": "completed",
                    "phase": "completed",
                    "current_operation": "Response generated",
                    "current_task": "Assistant response complete",
                    **_safe_model_activity_metrics(agent_result.model),
                },
            )
            return LocalChatResult(
                session_id=session.id,
                conversation_id=conversation_id,
                agent_id=target_agent_id,
                response=agent_result.response,
                message=assistant_message,
                model=agent_result.model,
                policy=policy,
            )

    def _primary_chat_selection(self, context: PermissionContext, agent_id: str | None,
                                message: str, conversation_id: str | None) -> ChatModelSelection | None:
        if self.primary_model_routing is None or message.lstrip().startswith("/"):
            return None
        workspace = "default"
        if conversation_id and self.conversations:
            try:
                record = self.conversations.get_conversation(conversation_id)
            except ConversationError as exc:
                if exc.code != "conversation_not_found":
                    raise
            else:
                workspace = str(record.metadata.get("workspace_id") or "default")
        recent_intent = None
        if conversation_id and self._session_path(conversation_id).exists():
            session = self.get_session(conversation_id)
            if session.messages and session.messages[-1].role == "assistant":
                recent_intent = session.messages[-1].metadata.get("model", {}).get("mom", {}).get("operation")
        return self.primary_model_routing.select(context, agent_id, message, workspace, recent_intent)

    def _plan_complex_turn(self, context: PermissionContext, agent_id: str | None,
                           message: str, session: ChatSession) -> ChatTurnResult | None:
        if self.complex_missions is None:
            return None
        planned = self.complex_missions.prepare(context, agent_id, message, session.id, session.project_id)
        if planned is None:
            return None
        reply = ChatMessage("assistant", planned.response,
                            metadata={"mission_id": planned.mission_id, "execution_path": "mission"})
        session = self._append_message(session, ChatMessage("user", message), session.agent_id, session.project_id)
        session = self._append_message(session, reply, session.agent_id, session.project_id)
        self._persist_session(session, context.actor_id)
        return ChatTurnResult(session.id, session.agent_id, planned.response, reply,
                              command={"type": "mission_plan", "mission_id": planned.mission_id})

    def _resolve_local_chat_model(
        self,
        model_provider_id: str | None,
        model_name: str | None,
        policy: dict[str, Any],
    ) -> dict[str, str | None]:
        provider_id = (model_provider_id or "").strip() or self._default_local_chat_provider(policy)
        selected_model = (model_name or "").strip() or self._default_local_chat_model()

        if self.model_hub is not None:
            if self._model_hub_has_explicit_defaults():
                defaults = self.model_hub.get_defaults()
                if not provider_id:
                    provider_id = defaults.default_provider or provider_id
                if not selected_model:
                    selected_model = defaults.default_chat_model or selected_model

            if provider_id in {"lmstudio", "lmstudio_local"} and self.lmstudio:
                health = self.lmstudio.health()
                if not health.available:
                    raise ValidationError("The selected runtime 'lmstudio' is unavailable.")

            providers = {item.provider_id: item for item in self.model_hub.list_providers()}
            # A fresh LM Studio probe takes precedence over an older catalog snapshot.
            if (provider_id not in {"lmstudio", "lmstudio_local"} or self.lmstudio is None) and provider_id in providers and not providers[provider_id].active:
                raise ValidationError(f"The selected runtime '{provider_id}' is unavailable.")

        if not provider_id:
            provider_id = "lmstudio"
        if provider_id == "lmstudio_local":
            provider_id = "lmstudio"

        if not selected_model and self.lmstudio:
            selected_model = self.lmstudio.load_config().default_model

        return {"provider_id": provider_id, "model_name": selected_model}

    @staticmethod
    def _default_local_chat_provider(policy: dict[str, Any]) -> str | None:
        provider_id = str(policy.get("provider_id") or "").strip()
        if provider_id == "lmstudio_local":
            return "lmstudio"
        return provider_id or None

    def _default_local_chat_model(self) -> str | None:
        if not self.lmstudio:
            if self.model_hub is not None:
                defaults = self.model_hub.get_defaults()
                if self._model_hub_has_explicit_defaults() and defaults.default_chat_model:
                    return defaults.default_chat_model
            return None
        lmstudio_default = self.lmstudio.load_config().default_model
        if lmstudio_default:
            return lmstudio_default
        if self.model_hub is not None:
            defaults = self.model_hub.get_defaults()
            if self._model_hub_has_explicit_defaults() and defaults.default_chat_model:
                return defaults.default_chat_model
        return None

    def _model_hub_has_explicit_defaults(self) -> bool:
        if self.model_hub is None:
            return False
        return (self.model_hub.root / "defaults.yaml").exists()

    def _lmstudio_server_model_ids(self) -> set[str]:
        if not self.lmstudio:
            return set()
        try:
            return {
                model.model_id
                for model in self.lmstudio.list_models()
                if isinstance(model.model_id, str) and model.model_id.strip()
            }
        except Exception:
            return set()

    def _load_or_create_session(
        self,
        session_id: str | None,
        agent_id: str,
        project_id: str | None,
    ) -> ChatSession:
        if session_id:
            path = self._session_path(session_id)
            if path.exists():
                existing = self.get_session(session_id)
                if project_id and existing.project_id and project_id != existing.project_id:
                    raise ValidationError("session_workspace_mismatch: use a new session for another workspace")
                return existing
            return ChatSession(
                id=session_id,
                agent_id=agent_id,
                project_id=project_id,
                **current_correlation_fields(),
            )
        return ChatSession(
            id=str(uuid4()),
            agent_id=agent_id,
            project_id=project_id,
            **current_correlation_fields(),
        )

    def _load_context(
        self,
        context: PermissionContext,
        agent_id: str,
        incoming_message: str,
        session: ChatSession,
        project_id: str | None,
        *,
        max_history_items: int = 5,
        retrieval_decision: RetrievalDecision | None = None,
    ):
        project_id = project_id or session.project_id
        retrieval_decision = retrieval_decision or self._retrieval_decision(
            RetrievalDirective(), project_id
        )
        fused_context = None
        context_history: list[str | dict[str, str]] = [*self._history_for_context(session)]
        if self.context_fusion:
            conversation_id = None
            if self.conversations:
                try:
                    self.conversations.get_conversation(session.id)
                    conversation_id = session.id
                except Exception:
                    conversation_id = None
            fused_context = asdict(
                self.context_fusion.build_context(
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    incoming_message=incoming_message,
                    session_id=session.id,
                    permission_context=context,
                    options={
                        "workspace_id": project_id,
                        "include_project_knowledge": retrieval_decision.allowed,
                        "retrieval_query": retrieval_decision.directive.query,
                        "retrieval_intent": retrieval_decision.to_dict(),
                    },
                )
            )
            # Frontend conversations are persisted by ConversationRuntime while the
            # legacy chat session file is only updated after generation. Reuse the
            # conversation transcript here so the Workspace and Conversation
            # surfaces address the same memory and history.
            snapshot = fused_context.get("snapshot", {}) if isinstance(fused_context, dict) else {}
            fused_messages = snapshot.get("latest_messages", []) if isinstance(snapshot, dict) else []
            if isinstance(fused_messages, list) and fused_messages:
                context_history = []
                for message in fused_messages:
                    if not isinstance(message, dict):
                        continue
                    payload = message.get("payload", {})
                    if not isinstance(payload, dict):
                        payload = {}
                    body = str(payload.get("body", "")).strip()
                    if not body or body == incoming_message.strip():
                        continue
                    role = str(payload.get("role", "")).strip().lower()
                    if role not in {"user", "assistant", "system"}:
                        role = "assistant" if message.get("sender_agent_id") == agent_id else "user"
                    context_history.append({"role": role, "content": body})
        loaded = self.context_loader.load(
            context=context,
            agent_id=agent_id,
            project_id=project_id,
            history=context_history[-max_history_items:],
            conversation_context=fused_context,
        )
        loaded.agent_identity["application_features"] = [
            "Identidade e personalidade configuráveis do agente",
            *(["Histórico de conversas"] if self.conversations else []),
            *(["Memória persistente e preferências explícitas do usuário"] if self.memory else []),
            *(["Seleção de modelos e provedores"] if self.model_hub else []),
            *(["Indicadores de atividade do agente"] if self.presence else []),
        ]
        if self.memory:
            style = self.memory.response_style(context, incoming_message)
            if style:
                section = ContextSection(
                    kind="memory", name="response_style", source="explicit_response_style",
                    content=style, order=-1,
                )
                loaded.memory.insert(0, section)
                loaded.sections.insert(0, section)
        return loaded

    def _resolve_retrieval_directive(
        self,
        content: str,
        retrieval_intent: RetrievalDirective | dict[str, str] | None,
    ) -> RetrievalDirective:
        provided = normalize_retrieval_directive(retrieval_intent)
        if provided.intent.value != "none":
            return provided
        return detect_text_retrieval_intent(content)

    def _retrieval_decision(
        self, directive: RetrievalDirective, project_id: str | None
    ) -> RetrievalDecision:
        decision = decide_project_knowledge_retrieval(directive, project_id)
        self.event_bus.emit("chat.retrieval_intent_resolved", "chat", decision.to_dict())
        if directive.intent.value != "none" and not decision.allowed:
            raise ValidationError(f"retrieval_blocked: {decision.reason}")
        return decision

    def _default_agent_id(self) -> str:
        raw = load_structured_file(self.data_dir.resolve("config/system.yaml"))
        system = raw.get("system", raw)
        agent_id = system.get("default_agent_id")
        if not agent_id:
            raise ValidationError(
                "No agent_id provided and system.default_agent_id is not configured."
            )
        return str(agent_id)

    def _ensure_local_conversation(
        self,
        context: PermissionContext,
        agent_id: str,
        conversation_id: str | None,
        enabled: bool,
    ) -> str | None:
        if not enabled:
            return None
        if not self.conversations:
            raise ValidationError("Conversation runtime is unavailable for local chat persistence.")
        if conversation_id:
            self.conversations.get_conversation(conversation_id)
            return conversation_id
        conversation = self.conversations.create_conversation(
            context,
            [agent_id],
            title=f"Local chat with {agent_id}",
            metadata={"source": "local_chat"},
        )
        return conversation.conversation_id

    def _persist_local_conversation_messages(
        self,
        context: PermissionContext,
        agent_id: str,
        conversation_id: str | None,
        user_message: str,
        assistant_response: str,
    ) -> None:
        if not conversation_id or not self.conversations:
            return
        self.conversations.send_message(
            context,
            sender_agent_id=agent_id,
            receiver_agent_id=agent_id,
            payload={
                "subject": "Local chat user message",
                "body": user_message,
                "role": "user",
            },
            conversation_id=conversation_id,
            metadata={"source": "local_chat", "role": "user"},
        )
        self.conversations.send_message(
            context,
            sender_agent_id=agent_id,
            receiver_agent_id=agent_id,
            payload={
                "subject": "Local chat model response",
                "body": assistant_response,
                "role": "assistant",
            },
            conversation_id=conversation_id,
            metadata={"source": "local_chat", "role": "assistant"},
        )

    def _append_message(
        self,
        session: ChatSession,
        message: ChatMessage,
        agent_id: str,
        project_id: str | None,
    ) -> ChatSession:
        return ChatSession(
            id=session.id,
            agent_id=agent_id,
            project_id=project_id,
            messages=[*session.messages, message],
            correlation_id=session.correlation_id or message.correlation_id,
            causation_id=session.causation_id or message.causation_id,
            parent_id=session.parent_id or message.parent_id,
            source=session.source or message.source,
            created_at=session.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )

    def _persist_session(self, session: ChatSession, actor_id: str) -> None:
        path = self._session_path(session.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(session), indent=2, sort_keys=True), encoding="utf-8")
        self.event_bus.emit(
            "chat.session_persisted",
            actor_id,
            {
                "session_id": session.id,
                "agent_id": session.agent_id,
                "messages": len(session.messages),
            },
        )

    def _session_path(self, session_id: str) -> Path:
        return self.data_dir.resolve(f"chats/sessions/{session_id}.json")

    def _set_presence(
        self,
        agent_id: str,
        state: str,
        activity: str,
        session_id: str | None = None,
        approval_id: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        if not self.presence:
            return
        self.presence.set_state(
            agent_id,
            state,
            activity,
            {
                "current_session_id": session_id,
                "current_approval_id": approval_id,
                "actor_id": actor_id or agent_id,
            },
        )

    @staticmethod
    def _message_from_raw(raw: dict[str, Any]) -> ChatMessage:
        raw.setdefault("metadata", {})
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("parent_id", None)
        raw.setdefault("source", None)
        return ChatMessage(**raw)

    @staticmethod
    def _history_for_context(session: ChatSession) -> list[dict[str, str]]:
        return [{"role": message.role, "content": message.content} for message in session.messages]

    def _direct_local_chat_messages(
        self,
        session: ChatSession,
        message: str,
        max_context_messages: int,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        memory_sections: list[str] = []
        for relative_path in ("memory/SYSTEM.md", "memory/USER.md", "memory/MEMORY.md"):
            path = self.data_dir.resolve(relative_path)
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    memory_sections.append(content)
        if memory_sections:
            messages.append(
                {
                    "role": "system",
                    "content": "[CONTEXTO PERSISTENTE DO SYNAPSE]\n" + "\n\n".join(memory_sections),
                }
            )
        history = self._history_for_context(session)[-max(0, max_context_messages) :]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        return messages


def _safe_model_activity_metrics(model: object) -> dict[str, int | float | str | None]:
    if not isinstance(model, dict):
        return {}
    metadata = model.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    result: dict[str, int | float | str | None] = {}
    for key in ("latency_ms", "input_count", "output_count", "total_count", "first_output_ms"):
        value = metadata.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            result[key] = value
    output_rate = metadata.get("output_rate")
    if isinstance(output_rate, (int, float)) and not isinstance(output_rate, bool):
        result["output_rate"] = round(float(output_rate), 2)
    finish_reason = metadata.get("finish_reason")
    if isinstance(finish_reason, str):
        result["finish_reason"] = finish_reason[:64]
    return result
