from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.delegation_execution.models import EXECUTION_STATUSES, DelegationExecution

if TYPE_CHECKING:
    from synapse.delegation.runtime import DelegationRuntime


class DelegationExecutionRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        delegation: DelegationRuntime | None = None,
    ):
        self.data_dir = data_dir
        self.events = events
        self.delegation = delegation

    def create_execution(self, task_id: str) -> DelegationExecution:
        task = self._task(task_id)
        execution = DelegationExecution(
            task_id=task.task_id,
            attempt_number=len(self.list_task_executions(task.task_id)) + 1,
            status="pending",
            started_at=DelegationExecution.now(),
            assignee_agent_id=task.assignee_agent_id,
            correlation_id=task.correlation_id,
            causation_id=task.causation_id or task.task_id,
        )
        self._write(execution)
        self.events.emit(
            "delegation.execution.created", execution.assignee_agent_id, asdict(execution)
        )
        return execution

    def get_execution(self, execution_id: str) -> DelegationExecution:
        path = self._path(execution_id)
        if not path.exists():
            raise NotFound(f"Delegation execution not found: {execution_id}")
        return self._read(path)

    def list_task_executions(self, task_id: str) -> list[DelegationExecution]:
        executions = [
            self._read(path)
            for path in sorted(self.data_dir.resolve("delegation_execution").glob("*.yaml"))
        ]
        return sorted(
            [execution for execution in executions if execution.task_id == task_id],
            key=lambda execution: (execution.attempt_number, execution.started_at),
        )

    def start_execution(self, execution_id: str) -> DelegationExecution:
        return self._transition(execution_id, "running", "delegation.execution.started")

    def complete_execution(
        self,
        execution_id: str,
        result_summary: str | None = None,
    ) -> DelegationExecution:
        return self._transition(
            execution_id,
            "completed",
            "delegation.execution.completed",
            result_summary=result_summary,
        )

    def fail_execution(
        self,
        execution_id: str,
        error_message: str | None = None,
    ) -> DelegationExecution:
        return self._transition(
            execution_id,
            "failed",
            "delegation.execution.failed",
            error_message=error_message,
        )

    def cancel_execution(
        self,
        execution_id: str,
        error_message: str | None = None,
    ) -> DelegationExecution:
        return self._transition(
            execution_id,
            "cancelled",
            "delegation.execution.cancelled",
            error_message=error_message,
        )

    def latest_execution(self, task_id: str) -> DelegationExecution | None:
        executions = self.list_task_executions(task_id)
        return executions[-1] if executions else None

    def complete_latest_for_task(
        self,
        task_id: str,
        result_summary: str | None = None,
    ) -> DelegationExecution:
        execution = self._active_or_new(task_id)
        return self.complete_execution(execution.execution_id, result_summary=result_summary)

    def fail_latest_for_task(
        self,
        task_id: str,
        error_message: str | None = None,
    ) -> DelegationExecution:
        execution = self._active_or_new(task_id)
        return self.fail_execution(execution.execution_id, error_message=error_message)

    def status(self) -> dict[str, Any]:
        executions = [
            self._read(path)
            for path in sorted(self.data_dir.resolve("delegation_execution").glob("*.yaml"))
        ]
        failed = [execution for execution in executions if execution.status == "failed"]
        return {
            "available": True,
            "total": len(executions),
            "failed_recent": len(failed[-20:]),
        }

    def _active_or_new(self, task_id: str) -> DelegationExecution:
        latest = self.latest_execution(task_id)
        if latest and latest.status in {"pending", "running"}:
            return (
                latest if latest.status == "running" else self.start_execution(latest.execution_id)
            )
        return self.start_execution(self.create_execution(task_id).execution_id)

    def _transition(
        self,
        execution_id: str,
        status: str,
        event_type: str,
        result_summary: str | None = None,
        error_message: str | None = None,
    ) -> DelegationExecution:
        if status not in EXECUTION_STATUSES:
            raise ValidationError(f"Invalid execution status: {status}")
        current = self.get_execution(execution_id)
        if current.status in {"completed", "failed", "cancelled"}:
            raise ValidationError(f"Execution already finalized: {execution_id}")
        updated = DelegationExecution(
            execution_id=current.execution_id,
            task_id=current.task_id,
            attempt_number=current.attempt_number,
            status=status,
            started_at=current.started_at,
            finished_at=DelegationExecution.now()
            if status in {"completed", "failed", "cancelled"}
            else current.finished_at,
            assignee_agent_id=current.assignee_agent_id,
            correlation_id=current.correlation_id,
            causation_id=current.causation_id,
            result_summary=result_summary or current.result_summary,
            error_message=error_message or current.error_message,
            metadata=current.metadata,
        )
        self._write(updated)
        self.events.emit(event_type, updated.assignee_agent_id, asdict(updated))
        return updated

    def _task(self, task_id: str):
        if not self.delegation:
            raise ValidationError("DelegationExecutionRuntime requires DelegationRuntime")
        return self.delegation.get_task(task_id)

    def _path(self, execution_id: str) -> Path:
        return self.data_dir.resolve(f"delegation_execution/{execution_id}.yaml")

    def _write(self, execution: DelegationExecution) -> None:
        dump_structured_file(self._path(execution.execution_id), asdict(execution))

    @staticmethod
    def _read(path: Path) -> DelegationExecution:
        raw = load_structured_file(path)
        raw.setdefault("finished_at", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("result_summary", None)
        raw.setdefault("error_message", None)
        raw.setdefault("metadata", {})
        return DelegationExecution(**raw)
