from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

ConversationStatus = str
MessageStatus = str

CONVERSATION_STATUSES: set[ConversationStatus] = {"active", "paused", "closed", "archived"}
MESSAGE_STATUSES: set[MessageStatus] = {
    "pending",
    "streaming",
    "completed",
    "delivered",
    "acknowledged",
    "failed",
    "cancelled",
}
CONTENT_PART_TYPES = {"text", "code", "file", "image", "audio", "tool_result", "data"}


@dataclass(frozen=True)
class ConversationParticipant:
    participant_id: str
    participant_type: str
    role: str
    joined_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    left_at: str | None = None
    permissions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContentPart:
    type: str
    content: str | dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversationAttachment:
    attachment_id: str
    filename: str
    mime_type: str
    size: int
    storage_ref: str
    checksum: str
    conversation_id: str
    owner_id: str
    status: str = "available"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Conversation:
    conversation_id: str = field(default_factory=lambda: str(uuid4()))
    title: str | None = None
    status: ConversationStatus = "active"
    participants: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    conversation_type: str = "agent"
    participant_records: list[dict[str, Any]] = field(default_factory=list)
    active_agent_id: str | None = None
    active_model: dict[str, Any] | None = None
    revision: int = 1


@dataclass(frozen=True)
class AgentMessage:
    sender_agent_id: str
    receiver_agent_id: str
    payload: dict[str, Any]
    conversation_id: str
    message_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: MessageStatus = "pending"
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sender_type: str = "agent"
    role: str = "user"
    content_parts: list[dict[str, Any]] = field(default_factory=list)
    parent_message_id: str | None = None
    model_metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, Any] | None = None
    idempotency_key: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: str
    summary: str
    message_count: int
    last_message_id: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "completed"
    source_message_ids: list[str] = field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    conversation_revision: int = 0
    error: dict[str, Any] | None = None
