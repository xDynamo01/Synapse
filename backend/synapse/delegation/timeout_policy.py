from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import load_structured_file
from synapse.delegation.models import DelegationTask
from synapse.delegation_execution.models import DelegationExecution

if TYPE_CHECKING:
    from synapse.delegation.runtime import DelegationRuntime
    from synapse.delegation_execution.runtime import DelegationExecutionRuntime

DEFAULT_DELEGATION_TIMEOUT_POLICY: dict[str, Any] = {
    "enabled": True,
    "default_timeout_minutes": 60,
    "timeout_by_priority": {"critical": 30, "high": 45, "normal": 60, "low": 120},
    "timeout_by_status": {"in_progress": 60},
    "mark_execution_failed_on_timeout": True,
    "mark_task_failed_on_timeout": False,
    "require_human_review_for_critical": True,
    "dry_run_default": True,
    "max_timeouts_per_run": 50,
}


@dataclass(frozen=True)
class DelegationTimeoutPolicy:
    enabled: bool = True
    default_timeout_minutes: int = 60
    timeout_by_priority: dict[str, int] = field(default_factory=dict)
    timeout_by_status: dict[str, int] = field(default_factory=dict)
    mark_execution_failed_on_timeout: bool = True
    mark_task_failed_on_timeout: bool = False
    require_human_review_for_critical: bool = True
    dry_run_default: bool = True
    max_timeouts_per_run: int = 50


@dataclass(frozen=True)
class DelegationTimeoutCandidate:
    task_id: str
    assignee_agent_id: str
    priority: str
    task_status: str
    timeout_minutes: int
    age_minutes: float
    reason: str
    execution_id: str | None = None
    execution_status: str | None = None
    requires_human_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DelegationTimeoutResult:
    dry_run: bool
    scanned: int
    candidates: list[DelegationTimeoutCandidate] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DelegationTimeoutPolicyRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        delegation: DelegationRuntime | None = None,
        executions: DelegationExecutionRuntime | None = None,
    ):
        self.data_dir = data_dir
        self.events = events
        self.delegation = delegation
        self.executions = executions

    def load_policy(self) -> DelegationTimeoutPolicy:
        raw = load_structured_file(self.data_dir.resolve("config/delegation_timeout_policy.yaml"))
        policy_raw = raw.get("delegation_timeout", raw)
        merged = dict(DEFAULT_DELEGATION_TIMEOUT_POLICY)
        merged.update(policy_raw)
        merged["timeout_by_priority"] = {
            **DEFAULT_DELEGATION_TIMEOUT_POLICY["timeout_by_priority"],
            **dict(merged.get("timeout_by_priority", {})),
        }
        merged["timeout_by_status"] = {
            **DEFAULT_DELEGATION_TIMEOUT_POLICY["timeout_by_status"],
            **dict(merged.get("timeout_by_status", {})),
        }
        return DelegationTimeoutPolicy(**merged)

    def find_timeout_candidates(self) -> list[DelegationTimeoutCandidate]:
        delegation, executions = self._require_runtimes()
        candidates: list[DelegationTimeoutCandidate] = []
        for task in delegation.list_tasks():
            latest = executions.latest_execution(task.task_id)
            candidate = self.evaluate_timeout(task, latest)
            if candidate:
                candidates.append(candidate)
        return candidates

    def evaluate_timeout(
        self,
        task: DelegationTask,
        latest_execution: DelegationExecution | None,
    ) -> DelegationTimeoutCandidate | None:
        policy = self.load_policy()
        if not policy.enabled:
            return None
        timeout_minutes = int(
            policy.timeout_by_priority.get(
                task.priority,
                policy.timeout_by_status.get(task.status, policy.default_timeout_minutes),
            )
        )
        now = datetime.now(UTC)
        if latest_execution and latest_execution.status == "running":
            started = self._parse_time(latest_execution.started_at)
            age = max((now - started).total_seconds() / 60, 0)
            if age >= timeout_minutes:
                return self._candidate(
                    task,
                    timeout_minutes,
                    age,
                    "execution_running_timeout",
                    latest_execution,
                    policy,
                )
        if task.status == "in_progress":
            updated = self._parse_time(task.updated_at)
            age = max((now - updated).total_seconds() / 60, 0)
            status_timeout = int(policy.timeout_by_status.get(task.status, timeout_minutes))
            if age >= status_timeout:
                return self._candidate(
                    task,
                    status_timeout,
                    age,
                    "task_in_progress_timeout",
                    latest_execution,
                    policy,
                )
        return None

    def apply_timeout(self, task_id: str, dry_run: bool = True) -> DelegationTimeoutResult:
        delegation, executions = self._require_runtimes()
        task = delegation.get_task(task_id)
        latest = executions.latest_execution(task_id)
        candidate = self.evaluate_timeout(task, latest)
        if not candidate:
            return DelegationTimeoutResult(dry_run=dry_run, scanned=1)
        result = DelegationTimeoutResult(dry_run=dry_run, scanned=1, candidates=[candidate])
        if dry_run:
            self.events.emit(
                "delegation.timeout.skipped", task.assignee_agent_id, asdict(candidate)
            )
            return result
        if candidate.requires_human_review:
            self.events.emit(
                "delegation.timeout.skipped", task.assignee_agent_id, asdict(candidate)
            )
            return DelegationTimeoutResult(
                dry_run=False,
                scanned=1,
                candidates=[candidate],
                skipped=[task_id],
            )
        policy = self.load_policy()
        try:
            if policy.mark_execution_failed_on_timeout and latest and latest.status == "running":
                executions.fail_execution(latest.execution_id, "timeout")
            if policy.mark_task_failed_on_timeout:
                delegation.fail_task(
                    PermissionContext(actor_id="delegation_timeout", actor_type="system"),
                    task_id,
                    reason="timeout",
                )
            self.events.emit(
                "delegation.timeout.applied", task.assignee_agent_id, asdict(candidate)
            )
            return DelegationTimeoutResult(
                dry_run=False,
                scanned=1,
                candidates=[candidate],
                applied=[task_id],
            )
        except Exception as exc:
            self.events.emit(
                "delegation.timeout.failed",
                task.assignee_agent_id,
                {"task_id": task_id, "error": str(exc) or type(exc).__name__},
            )
            return DelegationTimeoutResult(
                dry_run=False,
                scanned=1,
                candidates=[candidate],
                errors=[str(exc) or type(exc).__name__],
            )

    def run_timeout_scan(self, dry_run: bool = True) -> DelegationTimeoutResult:
        self.events.emit(
            "delegation.timeout.scan_started", "delegation_timeout", {"dry_run": dry_run}
        )
        candidates = self.find_timeout_candidates()
        policy = self.load_policy()
        selected = candidates[: policy.max_timeouts_per_run]
        applied: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        for candidate in selected:
            self.events.emit(
                "delegation.timeout.candidate_found",
                candidate.assignee_agent_id,
                asdict(candidate),
            )
            if dry_run:
                skipped.append(candidate.task_id)
                continue
            result = self.apply_timeout(candidate.task_id, dry_run=False)
            applied.extend(result.applied)
            skipped.extend(result.skipped)
            errors.extend(result.errors)
        result = DelegationTimeoutResult(
            dry_run=dry_run,
            scanned=len(self.delegation.list_tasks()) if self.delegation else 0,
            candidates=selected,
            applied=applied,
            skipped=skipped,
            errors=errors,
        )
        self.events.emit("delegation.timeout.scan_completed", "delegation_timeout", asdict(result))
        return result

    def status(self) -> dict[str, Any]:
        try:
            return {"available": True, "timeout_candidates": len(self.find_timeout_candidates())}
        except Exception as exc:
            return {"available": True, "timeout_candidates": 0, "error": str(exc)}

    def _candidate(
        self,
        task: DelegationTask,
        timeout_minutes: int,
        age_minutes: float,
        reason: str,
        execution: DelegationExecution | None,
        policy: DelegationTimeoutPolicy,
    ) -> DelegationTimeoutCandidate:
        candidate = DelegationTimeoutCandidate(
            task_id=task.task_id,
            assignee_agent_id=task.assignee_agent_id,
            priority=task.priority,
            task_status=task.status,
            timeout_minutes=timeout_minutes,
            age_minutes=age_minutes,
            reason=reason,
            execution_id=execution.execution_id if execution else None,
            execution_status=execution.status if execution else None,
            requires_human_review=(
                task.priority == "critical" and policy.require_human_review_for_critical
            ),
        )
        return candidate

    def _require_runtimes(
        self,
    ) -> tuple[DelegationRuntime, DelegationExecutionRuntime]:
        if not self.delegation or not self.executions:
            raise ValidationError(
                "Delegation timeout policy requires delegation and execution runtimes."
            )
        return self.delegation, self.executions

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
