from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.observability.correlation import current_correlation
from synapse.presence.state import PRESENCE_STATES, AgentPresence


class PresenceRuntime:
    def __init__(self, data_dir: DataDir, event_bus: EventBus):
        self.data_dir = data_dir
        self.event_bus = event_bus

    def get(self, agent_id: str) -> AgentPresence:
        path = self._path(agent_id)
        if not path.exists():
            return AgentPresence(agent_id=agent_id, state="offline")
        raw = load_structured_file(path)
        raw.setdefault("activity", None)
        raw.setdefault("current_task_id", None)
        raw.setdefault("current_job_id", None)
        raw.setdefault("current_session_id", None)
        raw.setdefault("current_approval_id", None)
        raw.setdefault("emotion", None)
        raw.setdefault("correlation_id", None)
        return AgentPresence(**raw)

    def set_state(
        self,
        agent_id: str,
        state: str,
        activity: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentPresence:
        if state not in PRESENCE_STATES:
            raise ValidationError(f"Invalid presence state: {state}")
        metadata = metadata or {}
        correlation = current_correlation()
        presence = AgentPresence(
            agent_id=agent_id,
            state=state,
            activity=activity,
            current_task_id=metadata.get("current_task_id"),
            current_job_id=metadata.get("current_job_id"),
            current_session_id=metadata.get("current_session_id"),
            current_approval_id=metadata.get("current_approval_id"),
            emotion=metadata.get("emotion"),
            correlation_id=metadata.get(
                "correlation_id",
                correlation.correlation_id if correlation else None,
            ),
        )
        dump_structured_file(self._path(agent_id), asdict(presence))
        self.event_bus.emit(
            "presence.updated",
            str(metadata.get("actor_id") or agent_id),
            asdict(presence),
        )
        return presence

    def clear(self, agent_id: str) -> AgentPresence:
        return self.set_state(agent_id, "offline")

    def list_all(self) -> list[AgentPresence]:
        presence_dir = self.data_dir.resolve("presence")
        return [self.get(path.stem) for path in sorted(presence_dir.glob("*.yaml"))]

    def _path(self, agent_id: str) -> Path:
        return self.data_dir.resolve(f"presence/{agent_id}.yaml")
