from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.dead_letter.models import (
    DEAD_LETTER_REASONS,
    DEAD_LETTER_STATUSES,
    DeadLetterEntry,
)

if TYPE_CHECKING:
    from synapse.delegation.runtime import DelegationRuntime
    from synapse.delegation_execution.runtime import DelegationExecutionRuntime
    from synapse.delegation_inbox.runtime import DelegationInboxRuntime


class DeadLetterRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        delegation: DelegationRuntime | None = None,
        executions: DelegationExecutionRuntime | None = None,
        inbox: DelegationInboxRuntime | None = None,
    ):
        self.data_dir = data_dir
        self.events = events
        self.delegation = delegation
        self.executions = executions
        self.inbox = inbox

    def create_entry(
        self,
        task_id: str,
        reason: str = "manual_move",
        metadata: dict[str, Any] | None = None,
    ) -> DeadLetterEntry:
        if reason not in DEAD_LETTER_REASONS:
            raise ValidationError(f"Invalid dead letter reason: {reason}")
        task = self._task(task_id)
        if self.is_task_open(task_id):
            raise ValidationError(f"Delegation already has a dead letter entry: {task_id}")
        latest = self.executions.latest_execution(task_id) if self.executions else None
        entry = DeadLetterEntry(
            task_id=task.task_id,
            latest_execution_id=latest.execution_id if latest else None,
            reason=reason,
            status="open",
            priority=task.priority,
            requester_agent_id=task.requester_agent_id,
            assignee_agent_id=task.assignee_agent_id,
            conversation_id=task.conversation_id,
            correlation_id=task.correlation_id,
            causation_id=task.causation_id,
            metadata=metadata or {},
        )
        self._write(entry)
        self.events.emit("dead_letter.created", entry.assignee_agent_id, asdict(entry))
        self._refresh_inbox(task.assignee_agent_id)
        return entry

    def move_to_dead_letter(
        self,
        task_id: str,
        reason: str = "manual_move",
        metadata: dict[str, Any] | None = None,
    ) -> DeadLetterEntry:
        return self.create_entry(task_id, reason=reason, metadata=metadata)

    def create_attempt_entry(
        self,
        attempt: Any,
        reason: str,
        *,
        error: dict[str, Any] | None = None,
        recovery_options: list[str] | None = None,
    ) -> DeadLetterEntry:
        existing = next(
            (
                entry
                for entry in self.list_entries()
                if entry.attempt_id == attempt.attempt_id
                and entry.status not in {"closed", "archived"}
            ),
            None,
        )
        if existing:
            return existing
        now = datetime.now(UTC).isoformat()
        entry = DeadLetterEntry(
            task_id=attempt.task_id,
            reason=reason if reason in DEAD_LETTER_REASONS else "execution_failure",
            status="open",
            priority="normal",
            requester_agent_id="mission-runtime",
            assignee_agent_id=attempt.agent_id,
            mission_id=attempt.mission_id,
            attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,
            agent_id=attempt.agent_id,
            latest_execution_id=attempt.execution_id,
            attempts=attempt.attempt_number,
            error=error or attempt.error,
            correlation_id=attempt.correlation_id,
            payload_redacted={"task_id": attempt.task_id, "input_snapshot": "[REDACTED]"},
            recovery_options=recovery_options or ["review", "retry", "close"],
            trace_reference=f"mission:{attempt.mission_id}",
            updated_at=now,
        )
        self._write(entry)
        self.events.emit("dead_letter.created", entry.agent_id or "mission-runtime", asdict(entry))
        return entry

    def get_entry(self, dlq_id: str) -> DeadLetterEntry:
        path = self._path(dlq_id)
        if not path.exists():
            raise NotFound(f"Dead letter entry not found: {dlq_id}")
        return self._read(path)

    def list_entries(self, status: str | None = None) -> list[DeadLetterEntry]:
        if status and status not in DEAD_LETTER_STATUSES:
            raise ValidationError(f"Invalid dead letter status: {status}")
        entries = [
            self._read(path) for path in sorted(self.data_dir.resolve("dead_letter").glob("*.yaml"))
        ]
        if status:
            entries = [entry for entry in entries if entry.status == status]
        return sorted(entries, key=lambda entry: (entry.created_at, entry.dlq_id))

    def list_open_entries(self) -> list[DeadLetterEntry]:
        return self.list_entries(status="open")

    def review_entry(self, dlq_id: str) -> DeadLetterEntry:
        return self._transition(dlq_id, "reviewed", "dead_letter.reviewed")

    def restore_entry(self, dlq_id: str, restore_status: str = "accepted") -> DeadLetterEntry:
        entry = self._transition(dlq_id, "restored", "dead_letter.restored")
        if self.delegation:
            self.delegation.restore_from_dead_letter(
                PermissionContext(actor_id="dead_letter", actor_type="system"),
                entry.task_id,
                restore_status,
                entry.dlq_id,
            )
        self._refresh_inbox(entry.assignee_agent_id)
        return entry

    def close_entry(self, dlq_id: str) -> DeadLetterEntry:
        entry = self._transition(dlq_id, "closed", "dead_letter.closed")
        self._refresh_inbox(entry.assignee_agent_id)
        return entry

    def archive_entry(self, dlq_id: str) -> DeadLetterEntry:
        current = self.get_entry(dlq_id)
        if current.status != "closed":
            raise ValidationError("Dead letter entry must be closed before archive.")
        return self._transition(dlq_id, "archived", "dead_letter.archived")

    def restore_attempt_entry(
        self,
        dlq_id: str,
        restored_attempt_id: str,
    ) -> DeadLetterEntry:
        current = self.get_entry(dlq_id)
        previous = current.metadata.get("restored_attempt_id")
        if previous:
            if previous == restored_attempt_id:
                return current
            raise ValidationError("Dead letter entry was already restored.")
        if current.status not in {"open", "reviewed"} or not current.attempt_id:
            raise ValidationError(
                "Attempt dead letter entry cannot be restored from current state."
            )
        updated = replace(
            current,
            status="restored",
            updated_at=datetime.now(UTC).isoformat(),
            metadata={**current.metadata, "restored_attempt_id": restored_attempt_id},
        )
        self._write(updated)
        self.events.emit(
            "dead_letter.restored", updated.agent_id or "mission-runtime", asdict(updated)
        )
        return updated

    def is_task_open(self, task_id: str) -> bool:
        return any(
            entry.task_id == task_id and entry.status != "restored" for entry in self.list_entries()
        )

    def open_task_ids(self) -> set[str]:
        return {entry.task_id for entry in self.list_open_entries()}

    def review_scan(self) -> dict[str, Any]:
        open_entries = self.list_open_entries()
        return {
            "open_count": len(open_entries),
            "entries": [asdict(entry) for entry in open_entries],
        }

    def _transition(self, dlq_id: str, status: str, event_type: str) -> DeadLetterEntry:
        if status not in DEAD_LETTER_STATUSES:
            raise ValidationError(f"Invalid dead letter status: {status}")
        current = self.get_entry(dlq_id)
        now = datetime.now(UTC).isoformat()
        updated = replace(
            current,
            status=status,
            updated_at=now,
            closed_at=now if status == "closed" else current.closed_at,
        )
        self._write(updated)
        self.events.emit(event_type, updated.assignee_agent_id, asdict(updated))
        return updated

    def _task(self, task_id: str):
        if not self.delegation:
            raise ValidationError("DeadLetterRuntime requires DelegationRuntime")
        return self.delegation.get_task(task_id)

    def _refresh_inbox(self, agent_id: str) -> None:
        if self.inbox:
            self.inbox.rebuild_agent_inbox(agent_id)

    def _path(self, dlq_id: str) -> Path:
        return self.data_dir.resolve(f"dead_letter/{dlq_id}.yaml")

    def _write(self, entry: DeadLetterEntry) -> None:
        dump_structured_file(self._path(entry.dlq_id), asdict(entry))

    @staticmethod
    def _read(path: Path) -> DeadLetterEntry:
        raw = load_structured_file(path)
        raw.setdefault("latest_execution_id", None)
        raw.setdefault("conversation_id", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("metadata", {})
        raw.setdefault("mission_id", None)
        raw.setdefault("attempt_id", None)
        raw.setdefault("worker_id", None)
        raw.setdefault("agent_id", None)
        raw.setdefault("attempts", 0)
        raw.setdefault("error", None)
        raw.setdefault("payload_redacted", {})
        raw.setdefault("recovery_options", [])
        raw.setdefault("trace_reference", None)
        raw.setdefault("updated_at", raw.get("created_at"))
        raw.setdefault("closed_at", None)
        return DeadLetterEntry(**raw)
