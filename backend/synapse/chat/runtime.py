from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse.agents.runtime import AgentRuntime
from synapse.commands.runtime import CommandRuntime
from synapse.context.loader import ContextLoader
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.observability.correlation import (
    correlation_scope,
    current_correlation,
    current_correlation_fields,
    new_correlation,
)


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


class ChatRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        context_loader: ContextLoader,
        agent_runtime: AgentRuntime,
        commands: CommandRuntime,
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.context_loader = context_loader
        self.agent_runtime = agent_runtime
        self.commands = commands

    def send_message(
        self,
        context: PermissionContext,
        agent_id: str,
        user_message: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> ChatTurnResult:
        session = self._load_or_create_session(session_id, agent_id, project_id)
        correlation = current_correlation() or new_correlation(
            source="chat",
            session_id=session.id,
            agent_id=agent_id,
        )
        with correlation_scope(correlation):
            return self._send_message(
                context=context,
                agent_id=agent_id,
                user_message=user_message,
                project_id=project_id,
                session=session,
            )

    def _send_message(
        self,
        context: PermissionContext,
        agent_id: str,
        user_message: str,
        project_id: str | None,
        session: ChatSession,
    ) -> ChatTurnResult:
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
            self._persist_session(session, context.actor_id)
            return ChatTurnResult(
                session_id=session.id,
                agent_id=agent_id,
                response=result.output,
                message=assistant_message,
                command=asdict(result),
            )

        loaded_context = self.context_loader.load(
            context=context,
            agent_id=agent_id,
            project_id=project_id,
            history=self._history_for_context(session),
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
        agent_result = self.agent_runtime.run(
            context=context,
            agent_id=agent_id,
            loaded_context=loaded_context,
            user_message=user_message,
            session_id=session.id,
            project_id=project_id,
        )
        assistant_message = ChatMessage(
            role="assistant",
            content=agent_result.response,
            metadata={
                "model": agent_result.model,
                "tool_calling": agent_result.tool_calling,
                "tool_results": [asdict(tool_result) for tool_result in agent_result.tool_results],
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
        self._persist_session(session, context.actor_id)
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

    def _load_or_create_session(
        self,
        session_id: str | None,
        agent_id: str,
        project_id: str | None,
    ) -> ChatSession:
        if session_id:
            path = self._session_path(session_id)
            if path.exists():
                return self.get_session(session_id)
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
        return [
            {"role": message.role, "content": message.content}
            for message in session.messages
        ]
