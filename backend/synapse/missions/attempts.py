from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.missions.errors import AttemptConflict, AttemptInvalidState, AttemptNotFound
from synapse.missions.models import AttemptStatus, TaskAttempt, now_iso
from synapse.storage.collection import FileCollection
from synapse.storage.errors import StorageRecordNotFound, StorageRevisionConflict

TERMINAL_ATTEMPT_STATUSES = {
    AttemptStatus.COMPLETED,
    AttemptStatus.FAILED,
    AttemptStatus.TIMED_OUT,
    AttemptStatus.CANCELLED,
    AttemptStatus.DEAD_LETTERED,
}

ATTEMPT_TRANSITIONS = {
    AttemptStatus.CREATED: {
        AttemptStatus.ASSIGNED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.ASSIGNED: {
        AttemptStatus.ACCEPTED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.ACCEPTED: {
        AttemptStatus.RUNNING,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.RUNNING: {
        AttemptStatus.WAITING_APPROVAL,
        AttemptStatus.WAITING_TOOL,
        AttemptStatus.WAITING_MODEL,
        AttemptStatus.COMPLETED,
        AttemptStatus.FAILED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.WAITING_APPROVAL: {
        AttemptStatus.RUNNING,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.WAITING_TOOL: {
        AttemptStatus.RUNNING,
        AttemptStatus.FAILED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.WAITING_MODEL: {
        AttemptStatus.RUNNING,
        AttemptStatus.FAILED,
        AttemptStatus.TIMED_OUT,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.FAILED: {AttemptStatus.RECOVERY_PENDING, AttemptStatus.DEAD_LETTERED},
    AttemptStatus.TIMED_OUT: {AttemptStatus.RECOVERY_PENDING, AttemptStatus.DEAD_LETTERED},
    AttemptStatus.RECOVERY_PENDING: {AttemptStatus.DEAD_LETTERED},
}


class TaskAttemptRuntime:
    def __init__(self, data_dir: DataDir, events: EventBus):
        self.data_dir = data_dir
        self.events = events

    def create(
        self,
        mission_id: str,
        task_id: str,
        worker_id: str,
        agent_id: str,
        *,
        correlation_id: str | None = None,
        timeout_at: str | None = None,
        input_snapshot: dict | None = None,
        idempotency_key: str | None = None,
    ) -> TaskAttempt:
        existing = self.active_for_task(task_id)
        if existing:
            if idempotency_key and existing.metadata.get("idempotency_key") == idempotency_key:
                return existing
            raise AttemptConflict(f"Task already has an active attempt: {task_id}")
        attempt = TaskAttempt(
            mission_id=mission_id,
            task_id=task_id,
            worker_id=worker_id,
            agent_id=agent_id,
            attempt_number=len(self.list(task_id=task_id)) + 1,
            correlation_id=correlation_id,
            timeout_at=timeout_at,
            input_snapshot=input_snapshot or {},
            metadata={"idempotency_key": idempotency_key} if idempotency_key else {},
        )
        self._write(attempt)
        self.events.emit("attempt.created", agent_id, asdict(attempt))
        return attempt

    def get(self, attempt_id: str) -> TaskAttempt:
        paths = list(self.data_dir.resolve("missions").glob(f"*/attempts/{attempt_id}.yaml"))
        if not paths:
            raise AttemptNotFound(f"Attempt not found: {attempt_id}")
        try:
            return TaskAttempt(
                **self._collection(paths[0].parent.parent.name).get(attempt_id).payload
            )
        except StorageRecordNotFound as exc:
            raise AttemptNotFound(f"Attempt not found: {attempt_id}") from exc

    def list(self, mission_id: str | None = None, task_id: str | None = None) -> list[TaskAttempt]:
        attempts = [
            TaskAttempt(**record.payload)
            for root in self.data_dir.resolve("missions").glob("*/attempts")
            for record in self._collection(root.parent.name).list_all()
        ]
        return sorted(
            (
                item
                for item in attempts
                if (mission_id is None or item.mission_id == mission_id)
                and (task_id is None or item.task_id == task_id)
            ),
            key=lambda item: (item.started_at, item.attempt_number, item.attempt_id),
        )

    def active_for_task(self, task_id: str) -> TaskAttempt | None:
        active = {
            AttemptStatus.CREATED,
            AttemptStatus.ASSIGNED,
            AttemptStatus.ACCEPTED,
            AttemptStatus.RUNNING,
            AttemptStatus.WAITING_APPROVAL,
            AttemptStatus.WAITING_TOOL,
            AttemptStatus.WAITING_MODEL,
        }
        return next(
            (item for item in reversed(self.list(task_id=task_id)) if item.status in active), None
        )

    def transition(
        self, attempt_id: str, status: str, expected_revision: int | None = None, **updates
    ) -> TaskAttempt:
        current = self.get(attempt_id)
        if current.status == status:
            return current
        if expected_revision is not None and current.revision != expected_revision:
            raise AttemptConflict(
                f"Attempt revision conflict: expected {expected_revision}, found {current.revision}"
            )
        target = AttemptStatus(status)
        allowed = ATTEMPT_TRANSITIONS.get(AttemptStatus(current.status), set())
        if target not in allowed:
            raise AttemptInvalidState(f"Invalid attempt transition: {current.status} -> {status}")
        completed_at = now_iso() if target in TERMINAL_ATTEMPT_STATUSES else current.completed_at
        updated = replace(
            current,
            status=target,
            completed_at=completed_at,
            updated_at=now_iso(),
            revision=current.revision + 1,
            **updates,
        )
        self._write(updated)
        self.events.emit(f"attempt.{target.value}", updated.agent_id, asdict(updated))
        return updated

    def _path(self, attempt: TaskAttempt) -> Path:
        return self.data_dir.resolve(
            f"missions/{attempt.mission_id}/attempts/{attempt.attempt_id}.yaml"
        )

    def _write(self, attempt: TaskAttempt) -> None:
        expected = attempt.revision - 1 if attempt.revision > 1 else None
        try:
            self._collection(attempt.mission_id).put(
                attempt.attempt_id,
                asdict(attempt),
                expected_revision=expected,
                create_only=attempt.revision == 1,
            )
        except StorageRevisionConflict as exc:
            raise AttemptConflict("Attempt revision conflict") from exc

    def _collection(self, mission_id: str) -> FileCollection:
        return FileCollection(
            collection_id="task_attempts",
            root=self.data_dir.resolve(f"missions/{mission_id}/attempts"),
            current_schema_version=1,
            validator=_validate_attempt,
            schema_version=lambda _payload: 1,
            revision=lambda payload: int(payload.get("revision", 1)),
            created_at=lambda payload: str(payload.get("started_at", "")),
            updated_at=lambda payload: str(payload.get("updated_at", "")),
            recovery_policy="quarantine_record",
            events=self.events,
        )


def _validate_attempt(payload: Mapping[str, object]) -> None:
    required = {"attempt_id", "mission_id", "task_id", "status", "revision"}
    if not required <= payload.keys():
        raise ValueError("attempt record is incomplete")
