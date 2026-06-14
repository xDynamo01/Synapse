from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager

TASK_STATUSES = {"active", "completed", "failed"}


@dataclass(frozen=True)
class Task:
    title: str
    created_by: str
    description: str = ""
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class TaskRuntime:
    def __init__(self, data_dir: DataDir, permissions: PermissionManager, event_bus: EventBus):
        self.data_dir = data_dir
        self.permissions = permissions
        self.event_bus = event_bus

    def create_task(
        self,
        context: PermissionContext,
        title: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        self.permissions.require(context, "tasks.create")
        task = Task(
            title=title,
            created_by=context.actor_id,
            description=description,
            metadata=metadata or {},
        )
        self._write(task)
        self.event_bus.emit("task.created", context.actor_id, asdict(task))
        return task

    def update_task(
        self,
        context: PermissionContext,
        task_id: str,
        status: str | None = None,
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        self.permissions.require(context, "tasks.update")
        task = self.get_task(task_id)
        next_status = status or task.status
        if next_status not in TASK_STATUSES:
            raise ValidationError(f"Invalid task status: {next_status}")

        next_metadata = dict(task.metadata)
        if metadata:
            next_metadata.update(metadata)
        if note:
            notes = list(next_metadata.get("notes", []))
            notes.append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "actor_id": context.actor_id,
                    "text": note,
                }
            )
            next_metadata["notes"] = notes

        updated = Task(
            id=task.id,
            title=task.title,
            created_by=task.created_by,
            description=task.description,
            status=next_status,
            metadata=next_metadata,
            created_at=task.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._delete_file(task)
        self._write(updated)
        self.event_bus.emit("task.updated", context.actor_id, asdict(updated))
        return updated

    def get_task(self, task_id: str) -> Task:
        for status in TASK_STATUSES:
            path = self.data_dir.resolve(f"tasks/{status}/{task_id}.json")
            if path.exists():
                return self._read(path)
        raise NotFound(f"Task not found: {task_id}")

    def list_tasks(self, status: str | None = None) -> list[Task]:
        statuses = [status] if status else sorted(TASK_STATUSES)
        tasks: list[Task] = []
        for item in statuses:
            if item not in TASK_STATUSES:
                raise ValidationError(f"Invalid task status: {item}")
            directory = self.data_dir.resolve(f"tasks/{item}")
            for path in sorted(directory.glob("*.json")):
                tasks.append(self._read(path))
        return tasks

    def _path(self, task: Task) -> Path:
        return self.data_dir.resolve(f"tasks/{task.status}/{task.id}.json")

    def _write(self, task: Task) -> None:
        path = self._path(task)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(task), indent=2, sort_keys=True), encoding="utf-8")

    def _delete_file(self, task: Task) -> None:
        path = self._path(task)
        if path.exists():
            path.unlink()

    @staticmethod
    def _read(path: Path) -> Task:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Task(**raw)

