from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from synapse.agents.registry import AgentRegistry
from synapse.conversations.errors import ConversationError
from synapse.conversations.models import (
    CONVERSATION_STATUSES,
    MESSAGE_STATUSES,
    AgentMessage,
    Conversation,
    ConversationAttachment,
    ConversationSummary,
)
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.observability.correlation import current_correlation_fields

if TYPE_CHECKING:
    from synapse.agents.admin import AgentAdminRuntime


class ConversationRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        agents: AgentRegistry,
        permissions: PermissionManager,
        events: EventBus,
        admin: AgentAdminRuntime | None = None,
    ):
        self.data_dir = data_dir
        self.agents = agents
        self.permissions = permissions
        self.events = events
        self.admin = admin

    def create_conversation(
        self,
        context: PermissionContext,
        participants: list[str],
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> Conversation:
        self.permissions.require(context, "agents.message")
        normalized = self._normalize_participants(participants)
        for agent_id in normalized:
            if agent_id != "local_chat":
                self.agents.get(agent_id)
        conversation = Conversation(
            conversation_id=conversation_id or Conversation().conversation_id,
            title=title,
            participants=normalized,
            metadata=metadata or {},
            conversation_type="local" if "local_chat" in normalized else "agent",
            participant_records=[self._participant_record(item) for item in normalized],
        )
        self._write_conversation(conversation)
        self.events.emit("conversation.created", context.actor_id, asdict(conversation))
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation:
        path = self._conversation_path(conversation_id)
        if not path.exists():
            raise ConversationError(
                "conversation_not_found",
                f"Conversation not found: {conversation_id}",
                status_code=404,
            )
        return self._read_conversation(path)

    def list_conversations(self, status: str | None = None) -> list[Conversation]:
        if status and status not in CONVERSATION_STATUSES:
            raise ValidationError(f"Invalid conversation status: {status}")
        root = self.data_dir.resolve("conversations")
        conversations = [
            self._read_conversation(path) for path in sorted(root.glob("*/CONVERSATION.yaml"))
        ]
        if status:
            conversations = [item for item in conversations if item.status == status]
        return sorted(conversations, key=lambda item: (item.updated_at, item.conversation_id))

    def update_conversation(
        self,
        context: PermissionContext,
        conversation_id: str,
        *,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> Conversation:
        self.permissions.require(context, "agents.message")
        current = self.get_conversation(conversation_id)
        if expected_revision is not None and current.revision != expected_revision:
            raise ConversationError(
                "revision_mismatch",
                "conversation revision mismatch",
                status_code=409,
                details={"expected": expected_revision, "actual": current.revision},
            )
        updated = self._copy_conversation(
            current,
            title=current.title if title is None else title,
            metadata=current.metadata if metadata is None else metadata,
        )
        self._write_conversation(updated)
        self.events.emit("conversation.updated", context.actor_id, asdict(updated))
        return updated

    def add_participant(
        self,
        context: PermissionContext,
        conversation_id: str,
        participant_id: str,
        participant_type: str = "agent",
        role: str = "participant",
        permissions: list[str] | None = None,
    ) -> Conversation:
        self.permissions.require(context, "agents.message")
        current = self.get_conversation(conversation_id)
        normalized = participant_id.strip().lower()
        if participant_type == "agent":
            self.agents.get(normalized)
        if normalized in current.participants:
            return current
        records = [
            *current.participant_records,
            self._participant_record(normalized, participant_type, role, permissions),
        ]
        updated = self._copy_conversation(
            current,
            participants=[*current.participants, normalized],
            participant_records=records,
        )
        self._write_conversation(updated)
        self.events.emit("conversation.participant_added", context.actor_id, asdict(updated))
        return updated

    def remove_participant(
        self, context: PermissionContext, conversation_id: str, participant_id: str
    ) -> Conversation:
        self.permissions.require(context, "agents.message")
        current = self.get_conversation(conversation_id)
        normalized = participant_id.strip().lower()
        remaining = [item for item in current.participants if item != normalized]
        if not remaining:
            raise ValidationError("conversation requires at least one participant")
        now = datetime.now(UTC).isoformat()
        records = [
            {**item, "left_at": now} if item.get("participant_id") == normalized else item
            for item in current.participant_records
        ]
        updated = self._copy_conversation(
            current, participants=remaining, participant_records=records
        )
        self._write_conversation(updated)
        self.events.emit("conversation.participant_removed", context.actor_id, asdict(updated))
        return updated

    def archive_conversation(
        self, context: PermissionContext, conversation_id: str
    ) -> Conversation:
        conversation = self._set_conversation_status(context, conversation_id, "archived")
        self.events.emit("conversation.archived", context.actor_id, asdict(conversation))
        return conversation

    def pause_conversation(self, context: PermissionContext, conversation_id: str) -> Conversation:
        conversation = self._set_conversation_status(context, conversation_id, "paused")
        self.events.emit("conversation.paused", context.actor_id, asdict(conversation))
        return conversation

    def resume_conversation(self, context: PermissionContext, conversation_id: str) -> Conversation:
        conversation = self._set_conversation_status(context, conversation_id, "active")
        self.events.emit("conversation.resumed", context.actor_id, asdict(conversation))
        return conversation

    def delete_conversation(
        self, context: PermissionContext, conversation_id: str, *, confirmed: bool = False
    ) -> Conversation:
        self.permissions.require(context, "agents.message")
        if not confirmed:
            raise ConversationError(
                "confirmation_required",
                "conversation deletion requires explicit confirmation",
                status_code=409,
            )
        conversation = self.get_conversation(conversation_id)
        directory = self._conversation_dir(conversation_id)
        if directory.exists():
            shutil.rmtree(directory)
        self.events.emit("conversation.deleted", context.actor_id, asdict(conversation))
        return conversation

    def send_message(
        self,
        context: PermissionContext,
        sender_agent_id: str,
        receiver_agent_id: str,
        payload: dict[str, Any],
        conversation_id: str | None = None,
        message_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        content_parts: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
        status: str = "pending",
        parent_message_id: str | None = None,
        model_metadata: dict[str, Any] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
    ) -> AgentMessage:
        self.permissions.require(context, "agents.message")
        sender = sender_agent_id.lower()
        receiver = receiver_agent_id.lower()
        if sender != "local_chat":
            self.agents.get(sender)
        if receiver != "local_chat":
            self.agents.get(receiver)
        self._assert_can_receive(receiver)

        if conversation_id:
            conversation = self.get_conversation(conversation_id)
            if conversation.status != "active":
                raise ValidationError(f"Conversation is not active: {conversation_id}")
            self._ensure_participants(conversation, [sender, receiver])
        else:
            conversation = self.create_conversation(
                context,
                [sender, receiver],
                title=str(payload.get("subject") or "Agent conversation"),
            )

        if idempotency_key:
            existing = next(
                (
                    item
                    for item in self._read_messages(conversation.conversation_id)
                    if item.idempotency_key == idempotency_key
                ),
                None,
            )
            if existing:
                return existing
        if status not in MESSAGE_STATUSES:
            raise ValidationError(f"Invalid message status: {status}")
        fields = current_correlation_fields()
        message = AgentMessage(
            message_id=message_id
            or AgentMessage(
                sender_agent_id=sender,
                receiver_agent_id=receiver,
                payload={},
                conversation_id=conversation.conversation_id,
            ).message_id,
            conversation_id=conversation.conversation_id,
            sender_agent_id=sender,
            receiver_agent_id=receiver,
            payload=payload,
            correlation_id=correlation_id or fields.get("correlation_id"),
            causation_id=causation_id or fields.get("causation_id"),
            metadata=metadata or {},
            status=status,
            sender_type="user" if sender == "local_chat" else "agent",
            role=str(payload.get("role") or "user"),
            content_parts=content_parts or self._parts_from_payload(payload),
            attachments=attachments or [],
            idempotency_key=idempotency_key,
            updated_at=datetime.now(UTC).isoformat(),
            parent_message_id=parent_message_id,
            model_metadata=model_metadata or {},
            tool_calls=tool_calls or [],
            error=error,
        )
        self._append_message(message)
        self._touch_conversation(conversation)
        self.events.emit("message.sent", context.actor_id, asdict(message))
        return message

    def receive_message(
        self,
        context: PermissionContext,
        message_id: str,
    ) -> AgentMessage:
        message = self._set_message_status(context, message_id, "delivered")
        self.events.emit("message.delivered", context.actor_id, asdict(message))
        return message

    def acknowledge_message(
        self,
        context: PermissionContext,
        message_id: str,
    ) -> AgentMessage:
        message = self._set_message_status(context, message_id, "acknowledged")
        self.events.emit("message.acknowledged", context.actor_id, asdict(message))
        return message

    def fail_message(
        self,
        context: PermissionContext,
        message_id: str,
        reason: str | None = None,
    ) -> AgentMessage:
        message = self._set_message_status(
            context,
            message_id,
            "failed",
            extra_metadata={"failed_reason": reason} if reason else None,
        )
        self.events.emit("message.failed", context.actor_id, asdict(message))
        return message

    def list_conversation_messages(
        self, conversation_id: str, *, offset: int = 0, limit: int = 100
    ) -> list[AgentMessage]:
        self.get_conversation(conversation_id)
        if offset < 0 or limit < 1 or limit > 500:
            raise ConversationError(
                "invalid_message", "invalid message pagination", status_code=422
            )
        return self._read_messages(conversation_id)[offset : offset + limit]

    def cancel_message(self, context: PermissionContext, message_id: str) -> AgentMessage:
        message = self._set_message_status(context, message_id, "cancelled")
        self.events.emit("generation.cancelled", context.actor_id, asdict(message))
        return message

    def register_attachment(
        self,
        context: PermissionContext,
        conversation_id: str,
        *,
        filename: str,
        mime_type: str,
        size: int,
        storage_ref: str,
        checksum: str,
        owner_id: str,
    ) -> ConversationAttachment:
        self.permissions.require(context, "agents.message")
        self.get_conversation(conversation_id)
        if not filename.strip() or "/" in filename or "\\" in filename or ".." in filename:
            raise ValidationError("attachment_invalid: invalid filename")
        if size < 0 or size > 25 * 1024 * 1024:
            raise ValidationError("attachment_invalid: invalid attachment size")
        if not mime_type.strip() or not checksum.strip():
            raise ValidationError("attachment_invalid: MIME type and checksum are required")
        referenced_path = self.data_dir.resolve(storage_ref)
        if not referenced_path.exists() or not referenced_path.is_file():
            raise ValidationError("attachment_invalid: storage reference does not exist")
        if referenced_path.stat().st_size != size:
            raise ValidationError("attachment_invalid: attachment size does not match storage")
        actual_checksum = hashlib.sha256(referenced_path.read_bytes()).hexdigest()
        if checksum.lower() != actual_checksum:
            raise ValidationError("attachment_invalid: checksum does not match storage")
        attachment = ConversationAttachment(
            attachment_id=str(uuid4()),
            filename=filename,
            mime_type=mime_type,
            size=size,
            storage_ref=storage_ref,
            checksum=checksum,
            conversation_id=conversation_id,
            owner_id=owner_id,
        )
        current = self.list_attachments(conversation_id)
        dump_structured_file(
            self._attachments_path(conversation_id),
            {"schema_version": 1, "attachments": [*current, asdict(attachment)]},
        )
        self.events.emit("conversation.attachment_registered", context.actor_id, asdict(attachment))
        return attachment

    def stage_and_register_attachment(
        self,
        context: PermissionContext,
        conversation_id: str,
        *,
        filename: str,
        mime_type: str,
        content: bytes,
        owner_id: str,
    ) -> ConversationAttachment:
        if not content:
            raise ValidationError("attachment_invalid: empty files are not supported")
        checksum = hashlib.sha256(content).hexdigest()
        storage_ref = f"conversations/{conversation_id}/attachments/storage/sha256-{checksum}/{filename}"
        storage_path = self.data_dir.resolve(storage_ref)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        if storage_path.exists():
            existing_checksum = hashlib.sha256(storage_path.read_bytes()).hexdigest()
            if storage_path.stat().st_size != len(content) or existing_checksum != checksum:
                raise ValidationError(
                    "attachment_storage_conflict: staged identity conflicts with existing content"
                )
        else:
            storage_path.write_bytes(content)
        return self.register_attachment(
            context,
            conversation_id,
            filename=filename,
            mime_type=mime_type,
            size=len(content),
            storage_ref=storage_ref,
            checksum=checksum,
            owner_id=owner_id,
        )

    def list_attachments(self, conversation_id: str) -> list[dict[str, Any]]:
        self.get_conversation(conversation_id)
        path = self._attachments_path(conversation_id)
        if not path.exists():
            return []
        raw = load_structured_file(path)
        return list(raw.get("attachments", []))

    def message_status(self, message_id: str) -> AgentMessage:
        return self._find_message(message_id)[1]

    def get_conversation_summary(self, conversation_id: str) -> ConversationSummary:
        self.get_conversation(conversation_id)
        path = self._summary_yaml_path(conversation_id)
        if not path.exists():
            return ConversationSummary(
                conversation_id=conversation_id,
                summary="",
                message_count=len(self._read_messages(conversation_id)),
                metadata={"exists": False},
            )
        raw = load_structured_file(path)
        raw.setdefault("summary", "")
        raw.setdefault("message_count", len(self._read_messages(conversation_id)))
        raw.setdefault("last_message_id", None)
        raw.setdefault("updated_at", datetime.now(UTC).isoformat())
        raw.setdefault("schema_version", 1)
        raw.setdefault("metadata", {})
        raw.setdefault("status", "completed")
        raw.setdefault("source_message_ids", [])
        raw.setdefault("model", None)
        raw.setdefault("provider", None)
        raw.setdefault("conversation_revision", self.get_conversation(conversation_id).revision)
        raw.setdefault("error", None)
        raw["metadata"] = {"exists": True, **raw["metadata"]}
        return ConversationSummary(**raw)

    def update_conversation_summary(
        self,
        conversation_id: str,
        summary_text: str,
        last_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> ConversationSummary:
        self.get_conversation(conversation_id)
        messages = self._read_messages(conversation_id)
        if last_message_id is None and messages:
            last_message_id = messages[-1].message_id
        summary = ConversationSummary(
            conversation_id=conversation_id,
            summary=summary_text,
            message_count=len(messages),
            last_message_id=last_message_id,
            metadata=metadata or {},
            source_message_ids=[item.message_id for item in messages],
            conversation_revision=self.get_conversation(conversation_id).revision,
            model=model,
            provider=provider,
        )
        self._write_summary(summary)
        self.events.emit("conversation.summary.updated", "conversation", asdict(summary))
        return summary

    def build_conversation_context(
        self,
        conversation_id: str,
        max_messages: int = 10,
    ) -> dict[str, Any]:
        conversation = self.get_conversation(conversation_id)
        summary = self.get_conversation_summary(conversation_id)
        messages = self._read_messages(conversation_id)[-max_messages:]
        context = {
            "conversation_id": conversation.conversation_id,
            "status": conversation.status,
            "participants": conversation.participants,
            "summary": asdict(summary),
            "messages": [asdict(message) for message in messages],
            "message_count": len(messages),
        }
        self.events.emit("conversation.context.built", "conversation", context)
        return context

    def prepare_context(
        self,
        conversation_id: str,
        agent_id: str | None = None,
        incoming_message: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        context = self.build_conversation_context(
            conversation_id,
            max_messages=int(options.get("max_messages", 10)),
        )
        context.update(
            {
                "agent_id": agent_id,
                "incoming_message": incoming_message,
                "options": options,
            }
        )
        self.events.emit("conversation.context.prepared", agent_id or "conversation", context)
        return context

    def _set_conversation_status(
        self,
        context: PermissionContext,
        conversation_id: str,
        status: str,
    ) -> Conversation:
        self.permissions.require(context, "agents.message")
        if status not in CONVERSATION_STATUSES:
            raise ValidationError(f"Invalid conversation status: {status}")
        current = self.get_conversation(conversation_id)
        updated = Conversation(
            conversation_id=current.conversation_id,
            title=current.title,
            status=status,
            participants=current.participants,
            created_at=current.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            metadata=current.metadata,
            conversation_type=current.conversation_type,
            participant_records=current.participant_records,
            active_agent_id=current.active_agent_id,
            active_model=current.active_model,
            revision=current.revision + 1,
        )
        self._write_conversation(updated)
        return updated

    def _set_message_status(
        self,
        context: PermissionContext,
        message_id: str,
        status: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        self.permissions.require(context, "agents.message")
        if status not in MESSAGE_STATUSES:
            raise ValidationError(f"Invalid message status: {status}")
        conversation_id, current = self._find_message(message_id)
        metadata = dict(current.metadata)
        metadata.update(extra_metadata or {})
        updated = AgentMessage(
            message_id=current.message_id,
            conversation_id=current.conversation_id,
            sender_agent_id=current.sender_agent_id,
            receiver_agent_id=current.receiver_agent_id,
            created_at=current.created_at,
            status=status,
            payload=current.payload,
            correlation_id=current.correlation_id,
            causation_id=current.causation_id,
            metadata=metadata,
            sender_type=current.sender_type,
            role=current.role,
            content_parts=current.content_parts,
            parent_message_id=current.parent_message_id,
            model_metadata=current.model_metadata,
            tool_calls=current.tool_calls,
            attachments=current.attachments,
            error=(
                {"code": "generation_failed", "message": str(metadata.get("failed_reason", ""))}
                if status == "failed"
                else current.error
            ),
            idempotency_key=current.idempotency_key,
            updated_at=datetime.now(UTC).isoformat(),
        )
        messages = [
            updated if item.message_id == message_id else item
            for item in self._read_messages(conversation_id)
        ]
        self._write_messages(conversation_id, messages)
        return updated

    def _find_message(self, message_id: str) -> tuple[str, AgentMessage]:
        root = self.data_dir.resolve("conversations")
        for path in sorted(root.glob("*/messages.jsonl")):
            conversation_id = path.parent.name
            for message in self._read_messages(conversation_id):
                if message.message_id == message_id:
                    return conversation_id, message
        raise NotFound(f"Conversation message not found: {message_id}")

    def _assert_can_receive(self, agent_id: str) -> None:
        if agent_id == "local_chat":
            return
        if self.admin:
            self.admin.assert_agent_runnable(agent_id)

    def _normalize_participants(self, participants: list[str]) -> list[str]:
        normalized: list[str] = []
        for participant in participants:
            agent_id = participant.strip().lower()
            if agent_id and agent_id not in normalized:
                normalized.append(agent_id)
        if len(normalized) < 1:
            raise ValidationError("Conversation requires at least one participant.")
        return normalized

    def _ensure_participants(self, conversation: Conversation, participants: list[str]) -> None:
        missing = [item for item in participants if item not in conversation.participants]
        if missing:
            raise ValidationError(
                f"Agent(s) are not conversation participants: {', '.join(missing)}"
            )

    def _touch_conversation(self, conversation: Conversation) -> None:
        updated = Conversation(
            conversation_id=conversation.conversation_id,
            title=conversation.title,
            status=conversation.status,
            participants=conversation.participants,
            created_at=conversation.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            metadata=conversation.metadata,
            conversation_type=conversation.conversation_type,
            participant_records=conversation.participant_records,
            active_agent_id=conversation.active_agent_id,
            active_model=conversation.active_model,
            revision=conversation.revision + 1,
        )
        self._write_conversation(updated)

    def _conversation_dir(self, conversation_id: str) -> Path:
        return self.data_dir.resolve(f"conversations/{conversation_id}")

    def _conversation_path(self, conversation_id: str) -> Path:
        return self.data_dir.resolve(f"conversations/{conversation_id}/CONVERSATION.yaml")

    def _messages_path(self, conversation_id: str) -> Path:
        return self.data_dir.resolve(f"conversations/{conversation_id}/messages.jsonl")

    def _summary_md_path(self, conversation_id: str) -> Path:
        return self.data_dir.resolve(f"conversations/{conversation_id}/SUMMARY.md")

    def _summary_yaml_path(self, conversation_id: str) -> Path:
        return self.data_dir.resolve(f"conversations/{conversation_id}/SUMMARY.yaml")

    def _attachments_path(self, conversation_id: str) -> Path:
        return self.data_dir.resolve(f"conversations/{conversation_id}/ATTACHMENTS.yaml")

    def _write_conversation(self, conversation: Conversation) -> None:
        directory = self._conversation_dir(conversation.conversation_id)
        directory.mkdir(parents=True, exist_ok=True)
        dump_structured_file(
            self._conversation_path(conversation.conversation_id), asdict(conversation)
        )
        self._messages_path(conversation.conversation_id).touch(exist_ok=True)

    @staticmethod
    def _read_conversation(path: Path) -> Conversation:
        raw = load_structured_file(path)
        raw.setdefault("title", None)
        raw.setdefault("status", "active")
        raw.setdefault("participants", [])
        raw.setdefault("metadata", {})
        raw.setdefault("created_at", datetime.now(UTC).isoformat())
        raw.setdefault("updated_at", raw["created_at"])
        raw.setdefault("conversation_type", "agent")
        raw.setdefault(
            "participant_records",
            [ConversationRuntime._participant_record(item) for item in raw["participants"]],
        )
        raw.setdefault("active_agent_id", None)
        raw.setdefault("active_model", None)
        raw.setdefault("revision", 1)
        return Conversation(**raw)

    def _append_message(self, message: AgentMessage) -> None:
        self._write_messages(
            message.conversation_id,
            [*self._read_messages(message.conversation_id), message],
        )

    def _read_messages(self, conversation_id: str) -> list[AgentMessage]:
        path = self._messages_path(conversation_id)
        if not path.exists():
            return []
        messages: list[AgentMessage] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            raw.setdefault("status", "pending")
            raw.setdefault("correlation_id", None)
            raw.setdefault("causation_id", None)
            raw.setdefault("metadata", {})
            raw.setdefault("sender_type", "agent")
            raw.setdefault("role", "user")
            raw.setdefault("content_parts", self._parts_from_payload(raw.get("payload", {})))
            raw.setdefault("parent_message_id", None)
            raw.setdefault("model_metadata", {})
            raw.setdefault("tool_calls", [])
            raw.setdefault("attachments", [])
            raw.setdefault("error", None)
            raw.setdefault("idempotency_key", None)
            raw.setdefault("updated_at", raw.get("created_at"))
            messages.append(AgentMessage(**raw))
        return messages

    def _write_messages(self, conversation_id: str, messages: list[AgentMessage]) -> None:
        path = self._messages_path(conversation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for message in messages:
                handle.write(json.dumps(asdict(message), sort_keys=True) + "\n")
        os.replace(temporary, path)

    @staticmethod
    def _participant_record(
        participant_id: str,
        participant_type: str | None = None,
        role: str = "participant",
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        resolved_type = participant_type or (
            "system" if participant_id == "local_chat" else "agent"
        )
        return {
            "participant_id": participant_id,
            "participant_type": resolved_type,
            "role": role,
            "joined_at": datetime.now(UTC).isoformat(),
            "left_at": None,
            "permissions": permissions or [],
        }

    @staticmethod
    def _parts_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        content = str(payload.get("body") or payload.get("content") or "")
        return [{"type": "text", "content": content, "metadata": {}}] if content else []

    @staticmethod
    def _copy_conversation(current: Conversation, **changes: Any) -> Conversation:
        payload = asdict(current)
        payload.update(changes)
        payload["updated_at"] = datetime.now(UTC).isoformat()
        payload["revision"] = current.revision + 1
        return Conversation(**payload)

    def _write_summary(self, summary: ConversationSummary) -> None:
        dump_structured_file(self._summary_yaml_path(summary.conversation_id), asdict(summary))
        markdown = (
            f"# Conversation Summary\n\n"
            f"Conversation: `{summary.conversation_id}`\n\n"
            f"Message count: {summary.message_count}\n\n"
            f"Last message: `{summary.last_message_id or ''}`\n\n"
            f"Updated at: {summary.updated_at}\n\n"
            f"## Summary\n\n{summary.summary}\n"
        )
        self._summary_md_path(summary.conversation_id).write_text(markdown, encoding="utf-8")
