from __future__ import annotations

import os
import socket
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import dump_structured_file, load_structured_file


@dataclass(frozen=True)
class RunnerIdentity:
    runner_id: str
    hostname: str
    process_id: int
    created_at: str
    last_seen_at: str
    role: str = "daemon"
    status: str = "offline"


class RunnerIdentityStore:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        role: str = "daemon",
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.role = role

    def load(self) -> RunnerIdentity:
        path = self.data_dir.resolve("daemon/runner.yaml")
        if not path.exists():
            return self._create()
        raw = load_structured_file(path)
        return RunnerIdentity(**raw)

    def heartbeat(self) -> RunnerIdentity:
        current = self.load()
        updated = self._with_updates(
            current,
            last_seen_at=self._now(),
            hostname=socket.gethostname(),
            process_id=os.getpid(),
        )
        self._save(updated)
        self.event_bus.emit("runner.heartbeat", updated.runner_id, asdict(updated))
        return updated

    def mark_online(self) -> RunnerIdentity:
        current = self.load()
        updated = self._with_updates(
            current,
            status="online",
            last_seen_at=self._now(),
            hostname=socket.gethostname(),
            process_id=os.getpid(),
        )
        self._save(updated)
        self.event_bus.emit("runner.online", updated.runner_id, asdict(updated))
        return updated

    def mark_offline(self) -> RunnerIdentity:
        current = self.load()
        updated = self._with_updates(current, status="offline", last_seen_at=self._now())
        self._save(updated)
        self.event_bus.emit("runner.offline", updated.runner_id, asdict(updated))
        return updated

    def mark_error(self) -> RunnerIdentity:
        current = self.load()
        updated = self._with_updates(current, status="error", last_seen_at=self._now())
        self._save(updated)
        self.event_bus.emit("runner.error", updated.runner_id, asdict(updated))
        return updated

    def _create(self) -> RunnerIdentity:
        now = self._now()
        identity = RunnerIdentity(
            runner_id=str(uuid4()),
            hostname=socket.gethostname(),
            process_id=os.getpid(),
            created_at=now,
            last_seen_at=now,
            role=self.role,
            status="offline",
        )
        self._save(identity)
        self.event_bus.emit("runner.created", identity.runner_id, asdict(identity))
        return identity

    def _save(self, identity: RunnerIdentity) -> RunnerIdentity:
        dump_structured_file(self.data_dir.resolve("daemon/runner.yaml"), asdict(identity))
        return identity

    @staticmethod
    def _with_updates(identity: RunnerIdentity, **updates) -> RunnerIdentity:
        payload = asdict(identity)
        payload.update(updates)
        return RunnerIdentity(**payload)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
