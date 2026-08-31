from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


STATE_OPERATIONS = {"set", "merge", "remove", "expire", "increment"}
STATE_ENTITY_TYPES = {
    "user_state",
    "system_state",
    "environment_state",
    "active_context",
    "agents",
    "conversations",
    "missions",
    "devices",
    "applications",
    "notifications",
    "perception_summary",
    "attention_summary",
    "metadata",
}
COLLECTION_ENTITY_TYPES = {
    "agents",
    "conversations",
    "missions",
    "devices",
    "applications",
    "notifications",
}


@dataclass(frozen=True)
class UserState:
    presence: str = "unknown"
    activity: str | None = None
    current_focus: str | None = None
    interaction_mode: str | None = None
    last_interaction_at: str | None = None
    do_not_disturb: bool = False
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SystemState:
    health: str = "unknown"
    load: dict[str, Any] = field(default_factory=dict)
    providers: list[dict[str, Any]] = field(default_factory=list)
    devices: list[dict[str, Any]] = field(default_factory=list)
    storage: dict[str, Any] = field(default_factory=dict)
    network_status: str | None = None
    daemon_status: str = "unknown"
    scheduler_status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnvironmentState:
    active_application: str | None = None
    active_window: str | None = None
    current_project: str | None = None
    screen_summary: str | None = None
    audio_state: dict[str, Any] = field(default_factory=dict)
    camera_state: dict[str, Any] = field(default_factory=dict)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentOperationalState:
    agent_id: str
    lifecycle: str = "unknown"
    presence: str = "unknown"
    busy: bool = False
    active_conversation: str | None = None
    active_mission: str | None = None
    current_task: str | None = None
    last_activity: str | None = None
    health: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldStateSnapshot:
    id: str = "current"
    revision: int = 0
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    user_state: dict[str, Any] = field(default_factory=lambda: asdict(UserState()))
    system_state: dict[str, Any] = field(default_factory=lambda: asdict(SystemState()))
    environment_state: dict[str, Any] = field(default_factory=lambda: asdict(EnvironmentState()))
    active_context: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    conversations: dict[str, dict[str, Any]] = field(default_factory=dict)
    missions: dict[str, dict[str, Any]] = field(default_factory=dict)
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    applications: dict[str, dict[str, Any]] = field(default_factory=dict)
    notifications: dict[str, dict[str, Any]] = field(default_factory=dict)
    perception_summary: dict[str, Any] = field(default_factory=dict)
    attention_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldStateUpdate:
    source: str
    entity_type: str
    operation: str
    values: dict[str, Any] = field(default_factory=dict)
    entity_id: str | None = None
    timestamp: str = field(default_factory=now_iso)
    expires_at: str | None = None
    correlation_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    sensitivity: str = "internal"
    expected_revision: int | None = None
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class StateHistoryEntry:
    update_id: str
    revision: int
    source: str
    entity_type: str
    entity_id: str | None
    operation: str
    timestamp: str
    correlation_id: str | None
    provenance: dict[str, Any]
    sensitivity: str


@dataclass(frozen=True)
class ReconciliationResult:
    checked_sources: list[str]
    applied_updates: int
    inconsistencies: list[dict[str, Any]]
    unavailable_sources: list[str]
    revision: int


def snapshot_from_dict(raw: dict[str, Any]) -> WorldStateSnapshot:
    allowed = WorldStateSnapshot.__dataclass_fields__
    return WorldStateSnapshot(**{key: value for key, value in raw.items() if key in allowed})


def update_from_dict(raw: dict[str, Any]) -> WorldStateUpdate:
    allowed = WorldStateUpdate.__dataclass_fields__
    return WorldStateUpdate(**{key: value for key, value in raw.items() if key in allowed})
