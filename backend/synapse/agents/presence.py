from __future__ import annotations

import json

from synapse.agents.models import VALID_AGENT_STATUSES, AgentStatus
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError


class PresenceStore:
    def __init__(self, data_dir: DataDir, event_bus: EventBus):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.path = self.data_dir.resolve("logs/presence.json")

    def list_statuses(self) -> dict[str, AgentStatus]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def set_status(self, agent_id: str, status: AgentStatus, actor_id: str) -> None:
        if status not in VALID_AGENT_STATUSES:
            raise ValidationError(f"Invalid agent status: {status}")
        statuses = self.list_statuses()
        statuses[agent_id] = status
        self.path.write_text(json.dumps(statuses, indent=2, sort_keys=True), encoding="utf-8")
        self.event_bus.emit("agent.presence.changed", actor_id, {"agent_id": agent_id, "status": status})

