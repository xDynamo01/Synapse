from __future__ import annotations

import os
import socket
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import dump_structured_file, load_structured_file


@dataclass(frozen=True)
class SchedulerLockState:
    locked: bool
    owner_id: str | None = None
    acquired_at: str | None = None
    stale: bool = False
    path: str | None = None
    pid: int | None = None
    hostname: str | None = None
    heartbeat_at: str | None = None
    expires_at: str | None = None
    generation: int = 0


class SchedulerLock:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        owner_id: str | None = None,
        timeout_seconds: int = 300,
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.owner_id = owner_id or f"scheduler-{uuid4()}"
        self.timeout_seconds = timeout_seconds
        self.path = self.data_dir.resolve("locks/scheduler.lock")

    def acquire(self) -> bool:
        now = datetime.now(UTC)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            current = self.status()
            if current.owner_id == self.owner_id and current.locked and not current.stale:
                return True
            if current.stale:
                self.path.unlink(missing_ok=True)
                self.event_bus.emit(
                    "scheduler.lock_stale_recovered",
                    self.owner_id,
                    asdict(current),
                )
            else:
                self.event_bus.emit(
                    "scheduler.lock_skipped",
                    self.owner_id,
                    asdict(current),
                )
                return False

        state = SchedulerLockState(
            locked=True,
            owner_id=self.owner_id,
            acquired_at=now.isoformat(),
            stale=False,
            path=str(self.path),
            pid=os.getpid(),
            hostname=socket.gethostname(),
            heartbeat_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.timeout_seconds)).isoformat(),
            generation=(current.generation + 1) if "current" in locals() else 1,
        )
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                handle.write("")
            dump_structured_file(self.path, asdict(state))
        except FileExistsError:
            self.event_bus.emit(
                "scheduler.lock_skipped",
                self.owner_id,
                asdict(self.status()),
            )
            return False
        self.event_bus.emit("scheduler.lock_acquired", self.owner_id, asdict(state))
        return True

    def release(self) -> bool:
        current = self.status()
        if not current.locked:
            return False
        if current.owner_id != self.owner_id:
            self.event_bus.emit(
                "scheduler.lock_skipped",
                self.owner_id,
                {
                    **asdict(current),
                    "reason": "owned_by_another_runner",
                },
            )
            return False
        self.path.unlink(missing_ok=True)
        self.event_bus.emit("scheduler.lock_released", self.owner_id, asdict(current))
        return True

    def is_locked(self) -> bool:
        state = self.status()
        return state.locked and not state.stale

    def renew(self) -> SchedulerLockState:
        current = self.status()
        if not current.locked or current.owner_id != self.owner_id or current.stale:
            raise RuntimeError("Cannot renew a missing, foreign, or stale scheduler lock.")
        now = datetime.now(UTC)
        updated = SchedulerLockState(
            **{
                **asdict(current),
                "heartbeat_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=self.timeout_seconds)).isoformat(),
                "stale": False,
                "generation": current.generation + 1,
            }
        )
        dump_structured_file(self.path, asdict(updated))
        self.event_bus.emit("scheduler.lock_renewed", self.owner_id, asdict(updated))
        return updated

    def recover_stale(self) -> bool:
        current = self.status()
        if not current.locked:
            return True
        if not current.stale:
            if current.owner_id == self.owner_id:
                return True
            raise RuntimeError("Active scheduler lock cannot be recovered.")
        self.path.unlink(missing_ok=True)
        self.event_bus.emit("scheduler.lock_stale_recovered", self.owner_id, asdict(current))
        return True

    def status(self) -> SchedulerLockState:
        if not self.path.exists():
            return SchedulerLockState(locked=False, path=str(self.path))
        raw = load_structured_file(self.path)
        acquired_at = raw.get("acquired_at")
        heartbeat_at = raw.get("heartbeat_at") or acquired_at
        expires_at = raw.get("expires_at")
        stale = False
        if expires_at:
            stale = datetime.fromisoformat(expires_at) <= datetime.now(UTC)
        elif heartbeat_at:
            stale = datetime.fromisoformat(heartbeat_at) <= datetime.now(UTC) - timedelta(
                seconds=self.timeout_seconds
            )
        return SchedulerLockState(
            locked=True,
            owner_id=raw.get("owner_id"),
            acquired_at=acquired_at,
            stale=stale,
            path=str(self.path),
            pid=raw.get("pid"),
            hostname=raw.get("hostname"),
            heartbeat_at=heartbeat_at,
            expires_at=expires_at,
            generation=int(raw.get("generation", 0)),
        )

    @classmethod
    def from_policy(
        cls,
        data_dir: DataDir,
        event_bus: EventBus,
        owner_id: str | None = None,
    ) -> "SchedulerLock":
        policy = load_structured_file(data_dir.resolve("config/scheduler_policy.yaml"))
        lock_policy = policy.get("scheduler_lock", {})
        return cls(
            data_dir=data_dir,
            event_bus=event_bus,
            owner_id=owner_id,
            timeout_seconds=int(lock_policy.get("timeout_seconds", 300)),
        )
