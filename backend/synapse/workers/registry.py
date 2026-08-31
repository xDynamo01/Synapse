from __future__ import annotations

import builtins
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, Unpack

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.missions.errors import WorkerNotFound
from synapse.missions.models import WorkerDescriptor, now_iso
from synapse.storage.collection import FileCollection
from synapse.storage.errors import StorageRecordNotFound, StorageRevisionConflict


class _WorkerUpdates(TypedDict, total=False):
    agent_id: str
    status: str
    capabilities: list[str]
    tools: list[str]
    permissions: list[str]
    role: str | None
    current_task_id: str | None
    current_attempt_id: str | None
    workload: float
    last_heartbeat: str
    failure_count: int
    metadata: dict[str, Any]
    revision: int


class WorkerRegistry:
    def __init__(self, data_dir: DataDir, events: EventBus):
        self.data_dir = data_dir
        self.events = events
        self.collection = FileCollection(
            collection_id="workers",
            root=data_dir.resolve("workers"),
            current_schema_version=1,
            validator=_validate_worker,
            schema_version=lambda _payload: 1,
            revision=lambda payload: int(payload.get("revision", 1)),
            created_at=lambda payload: str(payload.get("last_heartbeat", "")),
            updated_at=lambda payload: str(payload.get("last_heartbeat", "")),
            recovery_policy="quarantine_record",
            events=events,
        )

    def register(self, worker: WorkerDescriptor) -> WorkerDescriptor:
        try:
            self.collection.put(worker.worker_id, asdict(worker), create_only=True)
        except StorageRevisionConflict as exc:
            raise ValidationError(f"Worker already registered: {worker.worker_id}") from exc
        self.events.emit("worker.registered", worker.agent_id, asdict(worker))
        return worker

    def get(self, worker_id: str) -> WorkerDescriptor:
        try:
            return WorkerDescriptor(**self.collection.get(worker_id).payload)
        except StorageRecordNotFound as exc:
            raise WorkerNotFound(f"Worker not found: {worker_id}") from exc

    def list(self, status: str | None = None) -> list[WorkerDescriptor]:
        workers = [WorkerDescriptor(**record.payload) for record in self.collection.list_all()]
        return sorted(
            (item for item in workers if status is None or item.status == status),
            key=lambda item: item.worker_id,
        )

    def update(self, worker_id: str, **updates: Unpack[_WorkerUpdates]) -> WorkerDescriptor:
        worker = replace(self.get(worker_id), **updates)
        self._write(worker)
        return worker

    def heartbeat(self, worker_id: str) -> WorkerDescriptor:
        worker = self.update(worker_id, last_heartbeat=now_iso())
        self.events.emit("worker.heartbeat", worker.agent_id, asdict(worker))
        return worker

    def set_workload(
        self,
        worker_id: str,
        workload: float,
        task_id: str | None = None,
        attempt_id: str | None = None,
    ) -> WorkerDescriptor:
        if not 0 <= workload <= 1:
            raise ValidationError("Worker workload must be between 0 and 1.")
        status = "busy" if workload > 0 else "idle"
        current = self.get(worker_id)
        worker = self.update(
            worker_id,
            workload=workload,
            current_task_id=task_id,
            current_attempt_id=attempt_id,
            status=status,
            revision=current.revision + 1,
        )
        self.events.emit(f"worker.{status}", worker.agent_id, asdict(worker))
        return worker

    def expire_stale(
        self, stale_after_seconds: int, now: datetime | None = None
    ) -> builtins.list[WorkerDescriptor]:
        cutoff = (now or datetime.now(UTC)) - timedelta(seconds=stale_after_seconds)
        stale: builtins.list[WorkerDescriptor] = []
        for worker in self.list():
            if (
                datetime.fromisoformat(worker.last_heartbeat) < cutoff
                and worker.status != "offline"
            ):
                worker = self.update(worker.worker_id, status="offline")
                stale.append(worker)
                self.events.emit("worker.stale", worker.agent_id, asdict(worker))
        return stale

    def disable(self, worker_id: str) -> WorkerDescriptor:
        return self.update(worker_id, status="unavailable", current_task_id=None)

    def _path(self, worker_id: str):
        return self.data_dir.resolve(f"workers/{worker_id}.yaml")

    def _write(self, worker: WorkerDescriptor) -> None:
        self.collection.put(worker.worker_id, asdict(worker))


def _validate_worker(payload: Mapping[str, Any]) -> None:
    required = {"worker_id", "agent_id", "status", "revision", "last_heartbeat"}
    if not required <= payload.keys():
        raise ValueError("worker record is incomplete")
