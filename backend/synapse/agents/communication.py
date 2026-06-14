from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from synapse.agents.models import AGENT_MESSAGE_STATUSES, AgentMessage
from synapse.agents.registry import AgentRegistry
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import dump_structured_file, load_structured_file


class AgentCommunication:
    def __init__(
        self,
        data_dir: DataDir,
        registry: AgentRegistry,
        permissions: PermissionManager,
        event_bus: EventBus,
    ):
        self.data_dir = data_dir
        self.registry = registry
        self.permissions = permissions
        self.event_bus = event_bus

    def send_agent_message(
        self,
        context: PermissionContext,
        from_agent_id: str,
        to_agent_id: str,
        body: str,
        subject: str | None = None,
        task_id: str | None = None,
    ) -> AgentMessage:
        self.permissions.require(context, "agents.message")
        self.registry.get(from_agent_id)
        self.registry.get(to_agent_id)

        message = AgentMessage(
            from_agent=from_agent_id,
            to_agent=to_agent_id,
            subject=subject or "Agent message",
            body=body,
            task_id=task_id,
        )
        inbox_entry = (
            f"\n## {message.created_at} | {message.from_agent} | {message.subject} | {message.id}\n\n"
            f"{message.body}\n"
        )
        self.data_dir.append_text(f"agents/{to_agent_id}/INBOX.md", inbox_entry)
        self._write_message(message)
        self.event_bus.emit("agent.message.sent", context.actor_id, asdict(message))
        return message

    def list_messages(
        self,
        context: PermissionContext,
        agent_id: str,
        status: str | None = None,
    ) -> list[AgentMessage]:
        self.permissions.require(context, "agents.message")
        self.registry.get(agent_id)
        if status and status not in AGENT_MESSAGE_STATUSES:
            raise ValidationError(f"Invalid message status: {status}")

        messages_dir = self._messages_dir(agent_id)
        if not messages_dir.exists():
            return []

        messages = [self._read_message(path) for path in sorted(messages_dir.glob("*.yaml"))]
        if status:
            messages = [message for message in messages if message.status == status]
        return sorted(messages, key=lambda message: (message.created_at, message.id))

    def mark_read(self, context: PermissionContext, agent_id: str, message_id: str) -> AgentMessage:
        return self._set_status(context, agent_id, message_id, "read")

    def mark_processed(
        self,
        context: PermissionContext,
        agent_id: str,
        message_id: str,
    ) -> AgentMessage:
        return self._set_status(context, agent_id, message_id, "processed")

    def mark_failed(self, context: PermissionContext, agent_id: str, message_id: str) -> AgentMessage:
        return self._set_status(context, agent_id, message_id, "failed")

    def _set_status(
        self,
        context: PermissionContext,
        agent_id: str,
        message_id: str,
        status: str,
    ) -> AgentMessage:
        self.permissions.require(context, "agents.message")
        if status not in AGENT_MESSAGE_STATUSES:
            raise ValidationError(f"Invalid message status: {status}")

        message = self._get_message(agent_id, message_id)
        previous_status = message.status
        updated = AgentMessage(
            id=message.id,
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            subject=message.subject,
            body=message.body,
            task_id=message.task_id,
            status=status,
            timestamp=message.timestamp,
            created_at=message.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write_message(updated)
        self.event_bus.emit(
            "agent.message.status_changed",
            context.actor_id,
            {
                "id": message_id,
                "agent_id": agent_id,
                "from_status": previous_status,
                "to_status": status,
            },
        )
        return updated

    def _get_message(self, agent_id: str, message_id: str) -> AgentMessage:
        path = self._message_path(agent_id, message_id)
        if not path.exists():
            raise NotFound(f"Agent message not found: {message_id}")
        return self._read_message(path)

    def _messages_dir(self, agent_id: str) -> Path:
        return self.data_dir.resolve(f"agents/{agent_id}/messages")

    def _message_path(self, agent_id: str, message_id: str) -> Path:
        return self.data_dir.resolve(f"agents/{agent_id}/messages/{message_id}.yaml")

    def _write_message(self, message: AgentMessage) -> None:
        path = self._message_path(message.to_agent, message.id)
        dump_structured_file(path, asdict(message))

    @staticmethod
    def _read_message(path: Path) -> AgentMessage:
        raw = load_structured_file(path)
        if "from_agent_id" in raw:
            raw["from_agent"] = raw.pop("from_agent_id")
        if "to_agent_id" in raw:
            raw["to_agent"] = raw.pop("to_agent_id")
        if "created_at" not in raw and "timestamp" in raw:
            raw["created_at"] = raw["timestamp"]
        if "updated_at" not in raw:
            raw["updated_at"] = raw.get("created_at", datetime.now(UTC).isoformat())
        if "subject" not in raw:
            raw["subject"] = "Agent message"
        if "status" not in raw:
            raw["status"] = "pending"
        return AgentMessage(**raw)
