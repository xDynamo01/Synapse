from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from queue import Empty, Queue
from threading import Thread
from typing import Any, Callable, TypeVar
from uuid import uuid4

from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.maintenance.errors import (
    MaintenanceApprovalRequired,
    MaintenanceConflict,
    MaintenanceNotFound,
    MaintenancePlanExpired,
)
from synapse.maintenance.models import (
    MaintenanceAction,
    MaintenanceActionResult,
    MaintenanceCapability,
    MaintenanceExecutionRequest,
    MaintenanceExecutionResult,
    MaintenanceFinding,
    MaintenanceInspectionReport,
    MaintenanceInspectionRequest,
    MaintenanceInspectionResult,
    MaintenancePlan,
    MaintenancePlanRequest,
    MaintenanceScope,
    MaintenanceScopeKind,
    MaintenanceStatus,
    now_iso,
)
from synapse.maintenance.registry import MaintenanceContributorRegistry
from synapse.storage.collection import FileCollection
from synapse.storage.errors import StorageRecordNotFound
from synapse.storage.locking import CollectionLock

T = TypeVar("T")
RISK_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


class DataMaintenanceRuntime:
    """Coordinates registered owners; it never interprets or deletes domain data."""

    contributor_id = "data_maintenance"

    def __init__(
        self,
        data_dir: Any,
        events: Any,
        permissions: Any,
        policies: Any,
        approvals: Any,
        registry: MaintenanceContributorRegistry,
    ) -> None:
        self.events = events
        self.permissions = permissions
        self.policies = policies
        self.approvals = approvals
        self.registry = registry
        self.plans = FileCollection(
            collection_id="maintenance_plans",
            root=data_dir.resolve("maintenance/plans"),
            current_schema_version=1,
            validator=_validate_plan,
            revision=lambda payload: int(payload.get("revision", 1)),
            recovery_policy="fail_closed",
            events=events,
        )
        self.executions = FileCollection(
            collection_id="maintenance_executions",
            root=data_dir.resolve("maintenance/executions"),
            current_schema_version=1,
            validator=_validate_execution,
            revision=lambda payload: int(payload.get("revision", 1)),
            recovery_policy="fail_closed",
            events=events,
        )
        self.lock = CollectionLock(
            data_dir.resolve("maintenance/operation.lock"),
            timeout_seconds=5.0,
            stale_after_seconds=60.0,
            reentrant=False,
        )
        self._last_inspection_at: str | None = None
        self._degraded_contributors: set[str] = set()
        self._reconcile_interrupted()

    def list_contributors(self):
        return self.registry.list_info()

    def inspect(
        self, context: Any, request: MaintenanceInspectionRequest
    ) -> MaintenanceInspectionReport:
        self.permissions.require(context, "maintenance.admin")
        started = now_iso()
        monotonic = time.perf_counter()
        self.events.emit(
            "maintenance.inspection_started",
            context.actor_id,
            {"correlation_id": request.correlation_id},
        )
        results: list[MaintenanceInspectionResult] = []
        for registered in self._selected(request.scope):
            contributor = registered.contributor
            try:
                result = _bounded_call(
                    lambda: contributor.inspect(request), request.timeout_seconds
                )
            except TimeoutError:
                result = MaintenanceInspectionResult(
                    contributor.contributor_id,
                    "degraded",
                    [],
                    sorted(contributor.capabilities),
                    warnings=["contributor_timeout"],
                    error_code="timeout",
                )
            except Exception as exc:
                result = MaintenanceInspectionResult(
                    contributor.contributor_id,
                    "degraded",
                    [],
                    sorted(contributor.capabilities),
                    warnings=["contributor_exception"],
                    error_code=type(exc).__name__,
                )
            if result.status != "ready":
                self._degraded_contributors.add(contributor.contributor_id)
            else:
                self._degraded_contributors.discard(contributor.contributor_id)
            results.append(result)
        findings = [finding for result in results for finding in result.findings]
        if request.scope.kind is MaintenanceScopeKind.CATEGORY:
            findings = [item for item in findings if item.category == request.scope.value]
        completed = now_iso()
        self._last_inspection_at = completed
        report = MaintenanceInspectionReport(
            status=("degraded" if any(item.status != "ready" for item in results) else "ready"),
            results=results,
            findings=findings,
            correlation_id=request.correlation_id,
            started_at=started,
            completed_at=completed,
            duration_ms=round((time.perf_counter() - monotonic) * 1000, 3),
        )
        self.events.emit(
            "maintenance.inspection_completed",
            context.actor_id,
            {
                "status": report.status,
                "findings": len(findings),
                "duration_ms": report.duration_ms,
                "correlation_id": request.correlation_id,
            },
        )
        return report

    def create_plan(self, context: Any, request: MaintenancePlanRequest) -> MaintenancePlan:
        self.permissions.require(context, "maintenance.admin")
        if request.older_than_hours < 1:
            raise ValidationError("older_than_hours must be positive")
        if request.expires_in_seconds < 30 or request.expires_in_seconds > 86400:
            raise ValidationError("plan expiry must be between 30 and 86400 seconds")
        inspection = self.inspect(
            context,
            MaintenanceInspectionRequest(
                request.scope, request.correlation_id, request.timeout_seconds
            ),
        )
        actions: list[MaintenanceAction] = []
        for registered in self._selected(request.scope):
            contributor = registered.contributor
            if MaintenanceCapability.CLEANUP.value not in contributor.capabilities:
                continue
            try:
                planned = _bounded_call(
                    lambda: contributor.plan_cleanup(request), request.timeout_seconds
                )
                actions.extend(planned)
            except Exception as exc:
                self._degraded_contributors.add(contributor.contributor_id)
                self.events.emit(
                    "maintenance.action_failed",
                    context.actor_id,
                    {
                        "contributor": contributor.contributor_id,
                        "action_category": "plan",
                        "status": "failed",
                        "error_code": type(exc).__name__,
                        "correlation_id": request.correlation_id,
                    },
                )
        if request.scope.kind is MaintenanceScopeKind.CATEGORY:
            actions = [item for item in actions if item.category == request.scope.value]
        created = datetime.now(UTC)
        plan_id = str(uuid4())
        checksum = _plan_checksum(
            plan_id, request.scope, inspection.findings, actions, request.dry_run
        )
        risks = sorted(
            {item.risk for item in actions},
            key=lambda risk: RISK_ORDER.get(risk, len(RISK_ORDER)),
        )
        approval_required = any(item.approval_required for item in actions)
        plan = MaintenancePlan(
            plan_id=plan_id,
            created_at=created.isoformat(),
            expires_at=(created + timedelta(seconds=request.expires_in_seconds)).isoformat(),
            scope=request.scope,
            findings=inspection.findings,
            actions=actions,
            estimated_reclaimed_bytes=sum(item.estimated_bytes for item in actions),
            risks=risks,
            approval_required=approval_required,
            checksum=checksum,
            revision=1,
            dry_run=request.dry_run,
            correlation_id=request.correlation_id,
        )
        if approval_required:
            approval = self.approvals.create_request(
                context,
                "maintenance.execute",
                _approval_args(plan),
                _highest_risk(plan),
                "Execute an approved maintenance plan.",
                plan.plan_id,
            )
            plan = replace(plan, approval_id=approval.id)
        self.plans.put(plan.plan_id, asdict(plan), create_only=True)
        self.events.emit(
            "maintenance.plan_created",
            context.actor_id,
            {
                "plan_id": plan.plan_id,
                "actions": len(actions),
                "approval_required": approval_required,
                "correlation_id": request.correlation_id,
            },
        )
        return plan

    def get_plan(self, plan_id: str) -> MaintenancePlan:
        try:
            plan = _plan_from_payload(self.plans.get(plan_id).payload)
        except StorageRecordNotFound as exc:
            raise MaintenanceNotFound(f"Maintenance plan not found: {plan_id}") from exc
        if plan.status == "planned" and datetime.fromisoformat(plan.expires_at) <= datetime.now(
            UTC
        ):
            expired = replace(plan, status="expired", revision=plan.revision + 1)
            self.plans.put(plan.plan_id, asdict(expired), expected_revision=plan.revision)
            self.events.emit("maintenance.plan_expired", "maintenance", {"plan_id": plan.plan_id})
            return expired
        return plan

    def execute(
        self, context: Any, request: MaintenanceExecutionRequest
    ) -> MaintenanceExecutionResult:
        self.permissions.require(context, "maintenance.admin")
        existing = self._execution_or_none(request.plan_id)
        if existing and existing.status in {"completed", "partial", "failed", "dry_run"}:
            return existing
        plan = self.get_plan(request.plan_id)
        if plan.status == "expired":
            raise MaintenancePlanExpired("Maintenance plan expired")
        if plan.status == "cancelled":
            raise MaintenanceConflict("Maintenance plan was cancelled")
        if plan.status not in {"planned", "executing"}:
            raise MaintenanceConflict(f"Maintenance plan is {plan.status}")
        if request.checksum != plan.checksum or request.checksum != _plan_checksum(
            plan.plan_id, plan.scope, plan.findings, plan.actions, plan.dry_run
        ):
            raise MaintenanceConflict("Maintenance plan checksum mismatch")
        if request.expected_revision != plan.revision:
            raise MaintenanceConflict("Maintenance plan revision mismatch")
        if not request.confirmed:
            raise MaintenanceConflict("Explicit confirmation is required")
        self._authorize_execution(context, plan, request.approval_id)
        started = existing.started_at if existing else now_iso()
        execution = existing or MaintenanceExecutionResult(
            plan_id=plan.plan_id,
            status="running",
            attempted=0,
            completed=0,
            skipped=0,
            failed=0,
            reclaimed_bytes=0,
            warnings=[],
            errors=[],
            started_at=started,
            completed_at="",
            trace_id=request.correlation_id,
        )
        with self.lock.acquire():
            if existing is None:
                self.executions.put(plan.plan_id, asdict(execution), create_only=True)
                plan = replace(plan, status="executing", revision=plan.revision + 1)
                self.plans.put(plan.plan_id, asdict(plan), expected_revision=plan.revision - 1)
            self.events.emit(
                "maintenance.execution_started",
                context.actor_id,
                {"plan_id": plan.plan_id, "correlation_id": request.correlation_id},
            )
            completed_ids = {
                item.action_id
                for item in execution.action_results
                if item.status in {"completed", "dry_run", "skipped"}
            }
            for action in plan.actions:
                if action.action_id in completed_ids:
                    continue
                result = self._execute_action(action, plan.dry_run, request.timeout_seconds)
                execution = _append_action_result(execution, result)
                self.executions.put(
                    plan.plan_id,
                    asdict(execution),
                    expected_revision=execution.revision - 1,
                )
                event = (
                    "maintenance.action_failed"
                    if result.status == "failed"
                    else "maintenance.action_completed"
                )
                self.events.emit(
                    event,
                    context.actor_id,
                    {
                        "plan_id": plan.plan_id,
                        "contributor": action.contributor_id,
                        "action_category": action.category,
                        "bytes": result.reclaimed_bytes,
                        "status": result.status,
                        "error_code": result.error_code,
                        "correlation_id": request.correlation_id,
                    },
                )
            status = _execution_status(execution, plan.dry_run)
            previous_execution_revision = execution.revision
            execution = replace(
                execution,
                status=status,
                completed_at=now_iso(),
                revision=previous_execution_revision + 1,
            )
            self.executions.put(
                plan.plan_id,
                asdict(execution),
                expected_revision=previous_execution_revision,
            )
            plan = replace(plan, status="executed", revision=plan.revision + 1)
            self.plans.put(plan.plan_id, asdict(plan), expected_revision=plan.revision - 1)
        self.events.emit(
            "maintenance.execution_completed",
            context.actor_id,
            {
                "plan_id": plan.plan_id,
                "status": execution.status,
                "attempted": execution.attempted,
                "completed": execution.completed,
                "failed": execution.failed,
                "bytes": execution.reclaimed_bytes,
                "correlation_id": request.correlation_id,
            },
        )
        return execution

    def cancel(self, context: Any, plan_id: str, expected_revision: int) -> MaintenancePlan:
        self.permissions.require(context, "maintenance.admin")
        plan = self.get_plan(plan_id)
        if plan.revision != expected_revision:
            raise MaintenanceConflict("Maintenance plan revision mismatch")
        if plan.status == "cancelled":
            return plan
        if plan.status != "planned":
            raise MaintenanceConflict(f"Maintenance plan cannot be cancelled: {plan.status}")
        cancelled = replace(plan, status="cancelled", revision=plan.revision + 1)
        self.plans.put(plan.plan_id, asdict(cancelled), expected_revision=plan.revision)
        self.events.emit("maintenance.cancelled", context.actor_id, {"plan_id": plan.plan_id})
        return cancelled

    def history(self, limit: int = 100) -> list[MaintenanceExecutionResult]:
        return [
            _execution_from_payload(item.payload)
            for item in self.executions.list_all()[-max(1, min(limit, 500)) :]
        ]

    def status(self) -> MaintenanceStatus:
        contributors = self.registry.list_info()
        plans = [_plan_from_payload(item.payload) for item in self.plans.list_all()]
        executions = self.history(500)
        lock_exists = self.lock.lock_path.exists()
        stale = lock_exists and self.lock._is_stale()
        return MaintenanceStatus(
            state="degraded" if self._degraded_contributors or stale else "ready",
            contributor_count=len(contributors),
            required_contributors=sum(item.required for item in contributors),
            optional_contributors=sum(not item.required for item in contributors),
            active_operation=lock_exists and not stale,
            stale_lock=stale,
            last_inspection_at=self._last_inspection_at,
            last_execution_at=max(
                (item.completed_at for item in executions if item.completed_at),
                default=None,
            ),
            pending_cleanup_count=sum(
                len(item.actions)
                for item in plans
                if item.status == "planned"
                and datetime.fromisoformat(item.expires_at) > datetime.now(UTC)
            ),
            degraded_contributors=sorted(self._degraded_contributors),
        )

    def _selected(self, scope: MaintenanceScope):
        registered = self.registry.list_registered()
        if scope.kind is MaintenanceScopeKind.ALL:
            return registered
        if not scope.value:
            raise ValidationError(f"Maintenance scope {scope.kind.value} requires a value")
        if any(token in scope.value for token in ("/", "\\", "..")):
            raise ValidationError("Maintenance scope value is not a safe registered reference")
        if scope.kind is MaintenanceScopeKind.CONTRIBUTOR:
            return (self.registry.get(scope.value),)
        if scope.kind is MaintenanceScopeKind.CAPABILITY:
            if not self.registry.has_capability(scope.value):
                raise ValidationError(f"Maintenance capability is not registered: {scope.value}")
            return tuple(
                item for item in registered if scope.value in item.contributor.capabilities
            )
        if scope.kind is MaintenanceScopeKind.DOMAIN:
            return tuple(
                item
                for item in registered
                if item.contributor.domain == scope.value
                or item.contributor.contributor_id == "retention"
            )
        if not self.registry.has_category(scope.value):
            raise ValidationError(f"Maintenance category is not registered: {scope.value}")
        return tuple(item for item in registered if scope.value in item.contributor.categories)

    def _authorize_execution(
        self, context: Any, plan: MaintenancePlan, approval_id: str | None
    ) -> None:
        require_approval = plan.approval_required
        for contributor_id in sorted({item.contributor_id for item in plan.actions}):
            decision = self.policies.evaluate_policy(
                context.actor_id,
                "maintenance.execute",
                f"maintenance:{contributor_id}",
                {"risk": _highest_risk(plan), "dry_run": plan.dry_run},
            )
            if decision.decision == "deny":
                raise PermissionDenied(
                    f"Maintenance execution denied for contributor: {contributor_id}"
                )
            require_approval = require_approval or decision.approval_required
        if not require_approval:
            return
        bound_id = approval_id or plan.approval_id
        if not bound_id or (plan.approval_id and bound_id != plan.approval_id):
            raise MaintenanceApprovalRequired("Maintenance plan approval is required")
        self.approvals.assert_approved_for_tool(
            bound_id,
            context.actor_id,
            "maintenance.execute",
            _approval_args(plan),
            _highest_risk(plan),
        )

    def _execute_action(
        self, action: MaintenanceAction, dry_run: bool, timeout_seconds: float
    ) -> MaintenanceActionResult:
        try:
            contributor = self.registry.get(action.contributor_id).contributor
            if MaintenanceCapability.CLEANUP.value not in contributor.capabilities:
                raise ValidationError("Contributor does not support cleanup")
            return _bounded_call(
                lambda: contributor.execute_cleanup(action, dry_run=dry_run),
                timeout_seconds,
            )
        except TimeoutError:
            return MaintenanceActionResult(
                action.action_id,
                action.contributor_id,
                "failed",
                error_code="timeout",
            )
        except Exception as exc:
            return MaintenanceActionResult(
                action.action_id,
                action.contributor_id,
                "failed",
                error_code=type(exc).__name__,
            )

    def _execution_or_none(self, plan_id: str) -> MaintenanceExecutionResult | None:
        try:
            return _execution_from_payload(self.executions.get(plan_id).payload)
        except StorageRecordNotFound:
            return None

    def _reconcile_interrupted(self) -> None:
        for item in self.executions.list_all():
            execution = _execution_from_payload(item.payload)
            if execution.status != "running":
                continue
            interrupted = replace(
                execution,
                status="interrupted",
                completed_at=now_iso(),
                warnings=[*execution.warnings, "restart_reconciliation_required"],
                revision=execution.revision + 1,
            )
            self.executions.put(
                execution.plan_id,
                asdict(interrupted),
                expected_revision=execution.revision,
            )


def _bounded_call(operation: Callable[[], T], timeout_seconds: float) -> T:
    queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def invoke() -> None:
        try:
            queue.put((True, operation()))
        except Exception as exc:
            queue.put((False, exc))

    Thread(target=invoke, daemon=True).start()
    try:
        succeeded, value = queue.get(timeout=timeout_seconds)
    except Empty as exc:
        raise TimeoutError("Maintenance contributor timed out") from exc
    if not succeeded:
        raise value
    return value


def _plan_checksum(
    plan_id: str,
    scope: MaintenanceScope,
    findings: list[MaintenanceFinding],
    actions: list[MaintenanceAction],
    dry_run: bool,
) -> str:
    payload = {
        "plan_id": plan_id,
        "scope": asdict(scope),
        "findings": [asdict(item) for item in findings],
        "actions": [asdict(item) for item in actions],
        "dry_run": dry_run,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _approval_args(plan: MaintenancePlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "checksum": plan.checksum,
        "revision": 1,
    }


def _highest_risk(plan: MaintenancePlan) -> str:
    return max(
        plan.risks or ["moderate"],
        key=lambda risk: RISK_ORDER.get(risk, len(RISK_ORDER)),
    )


def _append_action_result(
    execution: MaintenanceExecutionResult, result: MaintenanceActionResult
) -> MaintenanceExecutionResult:
    completed = execution.completed + (result.status in {"completed", "dry_run"})
    skipped = execution.skipped + (result.status == "skipped")
    failed = execution.failed + (result.status == "failed")
    errors = list(execution.errors)
    warnings = list(execution.warnings)
    if result.error_code:
        errors.append(
            {
                "action_id": result.action_id,
                "contributor_id": result.contributor_id,
                "error_code": result.error_code,
            }
        )
    if result.warning:
        warnings.append(result.warning)
    return replace(
        execution,
        attempted=execution.attempted + 1,
        completed=completed,
        skipped=skipped,
        failed=failed,
        reclaimed_bytes=execution.reclaimed_bytes + result.reclaimed_bytes,
        warnings=warnings,
        errors=errors,
        action_results=[*execution.action_results, result],
        revision=execution.revision + 1,
    )


def _execution_status(execution: MaintenanceExecutionResult, dry_run: bool) -> str:
    if execution.failed and (execution.completed or execution.skipped):
        return "partial"
    if execution.failed:
        return "failed"
    return "dry_run" if dry_run else "completed"


def _plan_from_payload(payload: Mapping[str, Any]) -> MaintenancePlan:
    return MaintenancePlan(
        **{
            **payload,
            "scope": MaintenanceScope(
                kind=MaintenanceScopeKind(payload["scope"]["kind"]),
                value=payload["scope"].get("value"),
            ),
            "findings": [MaintenanceFinding(**item) for item in payload["findings"]],
            "actions": [MaintenanceAction(**item) for item in payload["actions"]],
        }
    )


def _execution_from_payload(payload: Mapping[str, Any]) -> MaintenanceExecutionResult:
    return MaintenanceExecutionResult(
        **{
            **payload,
            "action_results": [
                MaintenanceActionResult(**item) for item in payload["action_results"]
            ],
        }
    )


def _validate_plan(payload: Mapping[str, Any]) -> None:
    required = {
        "plan_id",
        "created_at",
        "expires_at",
        "scope",
        "findings",
        "actions",
        "checksum",
        "revision",
        "status",
    }
    if not required <= payload.keys():
        raise ValueError("Maintenance plan is incomplete")


def _validate_execution(payload: Mapping[str, Any]) -> None:
    required = {
        "plan_id",
        "status",
        "attempted",
        "completed",
        "failed",
        "action_results",
        "revision",
    }
    if not required <= payload.keys():
        raise ValueError("Maintenance execution is incomplete")
