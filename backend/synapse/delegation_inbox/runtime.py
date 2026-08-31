from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.delegation.models import TASK_STATUSES, DelegationTask
from synapse.delegation_inbox.models import DelegationInboxEntry, DelegationInboxSummary

if TYPE_CHECKING:
    from synapse.dead_letter.runtime import DeadLetterRuntime


class DelegationInboxRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        dead_letter: DeadLetterRuntime | None = None,
    ):
        self.data_dir = data_dir
        self.events = events
        self.dead_letter = dead_letter

    def rebuild_agent_inbox(self, agent_id: str) -> list[DelegationInboxEntry]:
        normalized = self._normalize_agent_id(agent_id)
        try:
            entries = [
                self._entry_from_task(task)
                for task in self._read_all_tasks()
                if task.assignee_agent_id == normalized
                and not self._is_dead_letter_open(task.task_id)
            ]
            self._write_agent_inbox(normalized, entries)
            self.events.emit(
                "delegation_inbox.rebuilt",
                "delegation_inbox",
                {"agent_id": normalized, "entries": len(entries)},
            )
            return entries
        except Exception as exc:
            self.events.emit(
                "delegation_inbox.rebuild_failed",
                "delegation_inbox",
                {"agent_id": normalized, "error": str(exc) or type(exc).__name__},
            )
            raise

    def rebuild_all_inboxes(self) -> dict[str, list[DelegationInboxEntry]]:
        try:
            by_agent: dict[str, list[DelegationInboxEntry]] = {}
            for task in self._read_all_tasks():
                if self._is_dead_letter_open(task.task_id):
                    continue
                by_agent.setdefault(task.assignee_agent_id, []).append(self._entry_from_task(task))
            known_agents = {
                path.stem
                for path in self.data_dir.resolve("delegation_inbox").glob("*.yaml")
                if path.is_file()
            }
            for agent_id in sorted(known_agents | set(by_agent)):
                entries = by_agent.get(agent_id, [])
                self._write_agent_inbox(agent_id, entries)
            self.events.emit(
                "delegation_inbox.rebuilt",
                "delegation_inbox",
                {
                    "agent_id": None,
                    "agents": len(by_agent),
                    "entries": sum(len(entries) for entries in by_agent.values()),
                },
            )
            return by_agent
        except Exception as exc:
            self.events.emit(
                "delegation_inbox.rebuild_failed",
                "delegation_inbox",
                {"agent_id": None, "error": str(exc) or type(exc).__name__},
            )
            raise

    def get_agent_inbox(self, agent_id: str) -> list[DelegationInboxEntry]:
        normalized = self._normalize_agent_id(agent_id)
        path = self._inbox_path(normalized)
        if not path.exists():
            return self.rebuild_agent_inbox(normalized)
        return [
            entry
            for entry in self._read_agent_inbox(path)
            if not self._is_dead_letter_open(entry.task_id)
        ]

    def get_pending_tasks(self, agent_id: str) -> list[DelegationInboxEntry]:
        return [entry for entry in self.get_agent_inbox(agent_id) if entry.status == "pending"]

    def get_active_tasks(self, agent_id: str) -> list[DelegationInboxEntry]:
        return [
            entry
            for entry in self.get_agent_inbox(agent_id)
            if entry.status in {"pending", "accepted", "in_progress"}
        ]

    def get_inbox_summary(self, agent_id: str) -> DelegationInboxSummary:
        normalized = self._normalize_agent_id(agent_id)
        entries = self.get_agent_inbox(normalized)
        counts = {
            status: len([entry for entry in entries if entry.status == status])
            for status in TASK_STATUSES
        }
        return DelegationInboxSummary(
            agent_id=normalized,
            pending_count=counts.get("pending", 0),
            accepted_count=counts.get("accepted", 0),
            in_progress_count=counts.get("in_progress", 0),
            completed_count=counts.get("completed", 0),
            failed_count=counts.get("failed", 0),
            cancelled_count=counts.get("cancelled", 0),
            total_count=len(entries),
            metadata={"rejected_count": counts.get("rejected", 0)},
        )

    def update_from_task(self, task: DelegationTask) -> None:
        entries = [
            entry
            for entry in self.get_agent_inbox(task.assignee_agent_id)
            if entry.task_id != task.task_id
        ]
        if not self._is_dead_letter_open(task.task_id):
            entries.append(self._entry_from_task(task))
        entries = sorted(entries, key=lambda entry: (entry.updated_at, entry.task_id))
        self._write_agent_inbox(task.assignee_agent_id, entries)
        self.events.emit(
            "delegation_inbox.updated",
            "delegation_inbox",
            {
                "agent_id": task.assignee_agent_id,
                "task_id": task.task_id,
                "status": task.status,
            },
        )

    def status(self) -> dict[str, Any]:
        root = self.data_dir.resolve("delegation_inbox")
        inbox_files = sorted(root.glob("*.yaml"))
        corrupted: list[str] = []
        total_entries = 0
        for path in inbox_files:
            try:
                total_entries += len(self._read_agent_inbox(path))
            except Exception:
                corrupted.append(path.stem)
        rebuild_failures = len(
            [
                event
                for event in self.events.tail(limit=200)
                if event.type == "delegation_inbox.rebuild_failed"
            ]
        )
        return {
            "available": True,
            "agents_indexed": len(inbox_files),
            "entries": total_entries,
            "corrupted_agents": corrupted,
            "rebuild_failures": rebuild_failures,
        }

    def _read_all_tasks(self) -> list[DelegationTask]:
        return [
            self._read_task(path)
            for path in sorted(self.data_dir.resolve("delegation").glob("*.yaml"))
            if not path.name.endswith(".completion.yaml")
        ]

    def _write_agent_inbox(self, agent_id: str, entries: list[DelegationInboxEntry]) -> None:
        dump_structured_file(
            self._inbox_path(agent_id),
            {"agent_id": agent_id, "entries": [asdict(entry) for entry in entries]},
        )

    @staticmethod
    def _read_agent_inbox(path: Path) -> list[DelegationInboxEntry]:
        raw = load_structured_file(path)
        raw_entries = raw.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValidationError(f"Invalid delegation inbox entries: {path.name}")
        entries: list[DelegationInboxEntry] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                raise ValidationError(f"Invalid delegation inbox entry: {path.name}")
            item.setdefault("conversation_id", None)
            entries.append(DelegationInboxEntry(**item))
        return entries

    @staticmethod
    def _read_task(path: Path) -> DelegationTask:
        raw = load_structured_file(path)
        if "title" not in raw:
            raise NotFound(f"Delegation task not found in file: {path.name}")
        raw.setdefault("status", "pending")
        raw.setdefault("priority", "normal")
        raw.setdefault("conversation_id", None)
        raw.setdefault("due_at", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("metadata", {})
        raw.setdefault("updated_at", raw.get("created_at"))
        return DelegationTask(**raw)

    @staticmethod
    def _entry_from_task(task: DelegationTask) -> DelegationInboxEntry:
        return DelegationInboxEntry(
            task_id=task.task_id,
            status=task.status,
            priority=task.priority,
            requester_agent_id=task.requester_agent_id,
            assignee_agent_id=task.assignee_agent_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            conversation_id=task.conversation_id,
        )

    def _inbox_path(self, agent_id: str) -> Path:
        return self.data_dir.resolve(f"delegation_inbox/{agent_id}.yaml")

    def _is_dead_letter_open(self, task_id: str) -> bool:
        return bool(self.dead_letter and self.dead_letter.is_task_open(task_id))

    @staticmethod
    def _normalize_agent_id(agent_id: str) -> str:
        normalized = agent_id.strip().lower()
        if not normalized:
            raise ValidationError("agent_id is required")
        return normalized
