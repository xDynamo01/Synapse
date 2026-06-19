from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.lifecycle.state import LIFECYCLE_STATES, AgentLifecycle
from synapse.observability.correlation import current_correlation
from synapse.presence.runtime import PresenceRuntime


class LifecycleRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        presence: PresenceRuntime,
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.presence = presence

    def boot(self, agent_id: str) -> AgentLifecycle:
        current = self.get(agent_id)
        updated = self._transition(
            current,
            "idle",
            reason="boot",
            boot_count=current.boot_count + 1,
            last_error=None,
        )
        self.presence.set_state(agent_id, "idle", "Agent booted", {"actor_id": agent_id})
        self.event_bus.emit("agent.booted", agent_id, asdict(updated))
        self.event_bus.emit("agent.lifecycle_changed", agent_id, asdict(updated))
        return updated

    def wake(self, agent_id: str, reason: str | None = None) -> AgentLifecycle:
        current = self.get(agent_id)
        updated = self._transition(
            current,
            "working",
            reason=reason or "wake",
            wake_count=current.wake_count + 1,
            last_error=None,
        )
        self.presence.set_state(
            agent_id,
            "working",
            reason or "Agent woken",
            {"actor_id": agent_id},
        )
        self.event_bus.emit("agent.woken", agent_id, asdict(updated))
        self.event_bus.emit("agent.lifecycle_changed", agent_id, asdict(updated))
        return updated

    def sleep(self, agent_id: str) -> AgentLifecycle:
        current = self.get(agent_id)
        updated = self._transition(
            current,
            "idle",
            reason="sleep",
            sleep_count=current.sleep_count + 1,
            last_error=None,
        )
        self.presence.set_state(agent_id, "idle", "Agent sleeping", {"actor_id": agent_id})
        self.event_bus.emit("agent.sleeping", agent_id, asdict(updated))
        self.event_bus.emit("agent.lifecycle_changed", agent_id, asdict(updated))
        return updated

    def shutdown(self, agent_id: str) -> AgentLifecycle:
        current = self.get(agent_id)
        updated = self._transition(
            current,
            "shutdown",
            reason="shutdown",
            last_error=None,
        )
        self.presence.set_state(agent_id, "offline", "Agent shutdown", {"actor_id": agent_id})
        self.event_bus.emit("agent.shutdown", agent_id, asdict(updated))
        self.event_bus.emit("agent.lifecycle_changed", agent_id, asdict(updated))
        return updated

    def error(self, agent_id: str, message: str) -> AgentLifecycle:
        current = self.get(agent_id)
        updated = self._transition(
            current,
            "error",
            reason="error",
            error_count=current.error_count + 1,
            last_error=message,
        )
        self.presence.set_state(agent_id, "error", message, {"actor_id": agent_id})
        self.event_bus.emit("agent.error", agent_id, asdict(updated))
        self.event_bus.emit("agent.lifecycle_changed", agent_id, asdict(updated))
        return updated

    def get(self, agent_id: str) -> AgentLifecycle:
        path = self._path(agent_id)
        if not path.exists():
            return AgentLifecycle(agent_id=agent_id)
        raw = load_structured_file(path)
        raw.setdefault("state", "offline")
        raw.setdefault("reason", None)
        raw.setdefault("boot_count", 0)
        raw.setdefault("wake_count", 0)
        raw.setdefault("sleep_count", 0)
        raw.setdefault("error_count", 0)
        raw.setdefault("last_error", None)
        raw.setdefault("correlation_id", None)
        return AgentLifecycle(**raw)

    def list_all(self) -> list[AgentLifecycle]:
        lifecycle_dir = self.data_dir.resolve("lifecycle")
        return [self.get(path.stem) for path in sorted(lifecycle_dir.glob("*.yaml"))]

    def _transition(
        self,
        current: AgentLifecycle,
        state: str,
        reason: str | None,
        boot_count: int | None = None,
        wake_count: int | None = None,
        sleep_count: int | None = None,
        error_count: int | None = None,
        last_error: str | None = None,
    ) -> AgentLifecycle:
        if state not in LIFECYCLE_STATES:
            raise ValidationError(f"Invalid lifecycle state: {state}")
        correlation = current_correlation()
        updated = AgentLifecycle(
            agent_id=current.agent_id,
            state=state,
            reason=reason,
            last_transition_at=datetime.now(UTC).isoformat(),
            boot_count=boot_count if boot_count is not None else current.boot_count,
            wake_count=wake_count if wake_count is not None else current.wake_count,
            sleep_count=sleep_count if sleep_count is not None else current.sleep_count,
            error_count=error_count if error_count is not None else current.error_count,
            last_error=last_error,
            correlation_id=correlation.correlation_id if correlation else current.correlation_id,
        )
        dump_structured_file(self._path(current.agent_id), asdict(updated))
        return updated

    def _path(self, agent_id: str) -> Path:
        return self.data_dir.resolve(f"lifecycle/{agent_id}.yaml")
