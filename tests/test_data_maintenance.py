from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.maintenance.errors import (
    MaintenanceApprovalRequired,
    MaintenanceConflict,
    MaintenancePlanExpired,
)
from synapse.maintenance.models import (
    MaintenanceAction,
    MaintenanceActionResult,
    MaintenanceCapability,
    MaintenanceExecutionRequest,
    MaintenanceExecutionResult,
    MaintenanceInspectionRequest,
    MaintenanceInspectionResult,
    MaintenancePlanRequest,
    MaintenanceScope,
    MaintenanceScopeKind,
)
from synapse.policies.models import PolicyRule

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def runtime_at(data_dir: Path):
    return create_runtime(
        Settings(
            project_root=PROJECT_ROOT,
            data_dir=data_dir,
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
    )


def old_temp(runtime, name: str = "cache/old.tmp") -> Path:
    path = runtime.data_dir.resolve(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("temporary", encoding="utf-8")
    old = time.time() - 26 * 3600
    os.utime(path, (old, old))
    return path


def allow(runtime, contributor_id: str) -> None:
    runtime.policies.create_rule(
        PolicyRule(
            scope="user",
            subject="local_owner",
            action="maintenance.execute",
            resource=f"maintenance:{contributor_id}",
            effect="allow",
            source="test",
        )
    )


def temp_scope() -> MaintenanceScope:
    return MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, "temporary_files")


def test_inspect_plan_dry_run_execute_idempotency_and_history(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data")
    candidate = old_temp(runtime)
    context = runtime.context()
    report = runtime.maintenance.inspect(
        context, MaintenanceInspectionRequest(temp_scope())
    )
    assert len(report.findings) == 1
    assert report.findings[0].reference == "cache/old.tmp"
    assert str(tmp_path.resolve()) not in json.dumps(asdict(report))

    allow(runtime, "temporary_files")
    preview = runtime.maintenance.create_plan(
        context, MaintenancePlanRequest(scope=temp_scope(), dry_run=True)
    )
    dry_run = runtime.maintenance.execute(
        context,
        MaintenanceExecutionRequest(
            preview.plan_id, preview.checksum, preview.revision, True
        ),
    )
    assert dry_run.status == "dry_run" and candidate.exists()

    plan = runtime.maintenance.create_plan(
        context, MaintenancePlanRequest(scope=temp_scope(), dry_run=False)
    )
    result = runtime.maintenance.execute(
        context,
        MaintenanceExecutionRequest(plan.plan_id, plan.checksum, plan.revision, True),
    )
    repeated = runtime.maintenance.execute(
        context,
        MaintenanceExecutionRequest(plan.plan_id, plan.checksum, plan.revision, True),
    )
    assert result == repeated
    assert result.status == "completed" and result.completed == 1
    assert not candidate.exists()
    assert {item.plan_id for item in runtime.maintenance.history()} >= {
        preview.plan_id,
        plan.plan_id,
    }


def test_checksum_revision_confirmation_policy_and_expiry_guards(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data")
    old_temp(runtime)
    context = runtime.context()
    plan = runtime.maintenance.create_plan(
        context, MaintenancePlanRequest(scope=temp_scope(), dry_run=False)
    )
    with pytest.raises(PermissionDenied):
        runtime.maintenance.execute(
            context,
            MaintenanceExecutionRequest(plan.plan_id, plan.checksum, 1, True),
        )
    allow(runtime, "temporary_files")
    with pytest.raises(MaintenanceConflict, match="checksum"):
        runtime.maintenance.execute(
            context, MaintenanceExecutionRequest(plan.plan_id, "0" * 64, 1, True)
        )
    with pytest.raises(MaintenanceConflict, match="revision"):
        runtime.maintenance.execute(
            context,
            MaintenanceExecutionRequest(plan.plan_id, plan.checksum, 99, True),
        )
    with pytest.raises(MaintenanceConflict, match="confirmation"):
        runtime.maintenance.execute(
            context,
            MaintenanceExecutionRequest(plan.plan_id, plan.checksum, 1, False),
        )
    expired = replace(
        plan,
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        revision=2,
    )
    runtime.maintenance.plans.put(
        plan.plan_id, asdict(expired), expected_revision=plan.revision
    )
    with pytest.raises(MaintenancePlanExpired):
        runtime.maintenance.execute(
            context,
            MaintenanceExecutionRequest(plan.plan_id, plan.checksum, 3, True),
        )


def test_cancel_is_revision_guarded_and_idempotent(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data")
    plan = runtime.maintenance.create_plan(
        runtime.context(), MaintenancePlanRequest(scope=temp_scope())
    )
    with pytest.raises(MaintenanceConflict):
        runtime.maintenance.cancel(runtime.context(), plan.plan_id, 4)
    cancelled = runtime.maintenance.cancel(runtime.context(), plan.plan_id, 1)
    assert cancelled.status == "cancelled"
    assert runtime.maintenance.cancel(
        runtime.context(), plan.plan_id, cancelled.revision
    ) == cancelled


def test_retention_requires_bound_approval_and_rejected_approval_denies(
    tmp_path: Path,
) -> None:
    runtime = runtime_at(tmp_path / "data")
    allow(runtime, "retention")
    context = runtime.context(device_id="trusted-admin")
    runtime.devices.register_device(
        "trusted-admin", trusted=True, permissions=["approve_actions"]
    )
    plan = runtime.maintenance.create_plan(
        context,
        MaintenancePlanRequest(
            scope=MaintenanceScope(MaintenanceScopeKind.DOMAIN, "notifications"),
            dry_run=False,
        ),
    )
    assert plan.approval_required and plan.approval_id
    with pytest.raises(MaintenanceApprovalRequired):
        runtime.maintenance.execute(
            context,
            MaintenanceExecutionRequest(
                plan.plan_id, plan.checksum, plan.revision, True, "wrong"
            ),
        )
    runtime.approvals.reject(context, plan.approval_id)
    with pytest.raises(PermissionDenied, match="rejected"):
        runtime.maintenance.execute(
            context,
            MaintenanceExecutionRequest(
                plan.plan_id,
                plan.checksum,
                plan.revision,
                True,
                plan.approval_id,
            ),
        )


def test_unknown_recent_and_symlink_escape_are_preserved(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data")
    unknown = runtime.data_dir.resolve("cache/unknown.bin")
    unknown.parent.mkdir(parents=True, exist_ok=True)
    unknown.write_text("unknown", encoding="utf-8")
    recent = runtime.data_dir.resolve("cache/recent.tmp")
    recent.write_text("active", encoding="utf-8")
    report = runtime.maintenance.inspect(
        runtime.context(), MaintenanceInspectionRequest(temp_scope())
    )
    assert report.findings == []
    assert unknown.exists() and recent.exists()
    if hasattr(os, "symlink"):
        outside = tmp_path / "outside"
        outside.mkdir()
        link = runtime.data_dir.resolve("escaped-link")
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("Symlink creation is unavailable on this platform")
        foundation = runtime.maintenance.inspect(
            runtime.context(),
            MaintenanceInspectionRequest(
                MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, "foundation")
            ),
        )
        assert any(item.category == "escaped_symlink" for item in foundation.findings)
        with pytest.raises(ValidationError):
            runtime.data_dir.resolve("escaped-link/file.txt")


def test_domain_owned_tmp_reference_is_not_a_cleanup_candidate(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data")
    referenced = runtime.data_dir.resolve("conversations/referenced.tmp")
    referenced.parent.mkdir(parents=True, exist_ok=True)
    referenced.write_text("domain-owned", encoding="utf-8")
    old = time.time() - 26 * 3600
    os.utime(referenced, (old, old))

    report = runtime.maintenance.inspect(
        runtime.context(), MaintenanceInspectionRequest(temp_scope())
    )

    assert all(item.reference != "conversations/referenced.tmp" for item in report.findings)
    assert referenced.exists()


class ControlledContributor:
    contributor_id = "controlled"
    domain = "controlled"
    capabilities = frozenset(
        {MaintenanceCapability.INSPECT.value, MaintenanceCapability.CLEANUP.value}
    )
    categories = frozenset({"controlled"})

    def __init__(self, *, sleep: float = 0, explode_inspection: bool = False):
        self.sleep = sleep
        self.explode_inspection = explode_inspection

    def inspect(self, request):
        if self.sleep:
            time.sleep(self.sleep)
        if self.explode_inspection:
            raise RuntimeError("inspection failed")
        return MaintenanceInspectionResult(
            self.contributor_id, "ready", [], sorted(self.capabilities)
        )

    def plan_cleanup(self, request):
        return [
            MaintenanceAction(self.contributor_id, "controlled", "controlled:ok", "moderate", False),
            MaintenanceAction(self.contributor_id, "controlled", "controlled:fail", "moderate", False),
        ]

    def execute_cleanup(self, action, *, dry_run):
        if action.reference.endswith("fail"):
            raise RuntimeError("controlled failure")
        return MaintenanceActionResult(
            action.action_id, self.contributor_id, "dry_run" if dry_run else "completed"
        )


class ExplodingContributor(ControlledContributor):
    contributor_id = "exploding"


def test_contributor_timeout_exception_partial_failure_and_duplicate_guard(
    tmp_path: Path,
) -> None:
    runtime = runtime_at(tmp_path / "data")
    runtime.maintenance.registry.register(ControlledContributor(sleep=0.1), required=False)
    timed = runtime.maintenance.inspect(
        runtime.context(),
        MaintenanceInspectionRequest(
            MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, "controlled"),
            timeout_seconds=0.01,
        ),
    )
    assert timed.status == "degraded" and timed.results[0].error_code == "timeout"
    with pytest.raises(ValidationError, match="already registered"):
        runtime.maintenance.registry.register(ControlledContributor())

    runtime.maintenance.registry.register(
        ExplodingContributor(explode_inspection=True), required=False
    )
    exploded = runtime.maintenance.inspect(
        runtime.context(),
        MaintenanceInspectionRequest(
            MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, "exploding")
        ),
    )
    assert exploded.status == "degraded"
    assert exploded.results[0].error_code == "RuntimeError"

    runtime.maintenance.registry._contributors.pop("controlled")
    runtime.maintenance.registry.register(ControlledContributor())
    allow(runtime, "controlled")
    plan = runtime.maintenance.create_plan(
        runtime.context(),
        MaintenancePlanRequest(
            scope=MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, "controlled"),
            dry_run=False,
        ),
    )
    result = runtime.maintenance.execute(
        runtime.context(),
        MaintenanceExecutionRequest(plan.plan_id, plan.checksum, plan.revision, True),
    )
    assert result.status == "partial"
    assert result.completed == 1 and result.failed == 1


def test_stale_lock_and_restart_preserve_plan_without_automatic_cleanup(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir)
    candidate = old_temp(runtime)
    allow(runtime, "temporary_files")
    plan = runtime.maintenance.create_plan(
        runtime.context(), MaintenancePlanRequest(scope=temp_scope(), dry_run=False)
    )
    lock = runtime.maintenance.lock.lock_path
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("stale", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock, (old, old))
    assert runtime.maintenance.status().stale_lock

    restarted = runtime_at(data_dir)
    recovered = restarted.maintenance.get_plan(plan.plan_id)
    assert recovered.checksum == plan.checksum and candidate.exists()
    result = restarted.maintenance.execute(
        restarted.context(),
        MaintenanceExecutionRequest(
            recovered.plan_id, recovered.checksum, recovered.revision, True
        ),
    )
    assert result.status == "completed"
    assert not candidate.exists() and not lock.exists()


def test_restart_reconciles_partial_execution_without_repeating_completed_action(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir)
    first = old_temp(runtime, "cache/first.tmp")
    second = old_temp(runtime, "cache/second.tmp")
    allow(runtime, "temporary_files")
    plan = runtime.maintenance.create_plan(
        runtime.context(), MaintenancePlanRequest(scope=temp_scope(), dry_run=False)
    )
    first_action = next(item for item in plan.actions if item.reference == "cache/first.tmp")
    first.unlink()
    interrupted = MaintenanceExecutionResult(
        plan_id=plan.plan_id,
        status="running",
        attempted=1,
        completed=1,
        skipped=0,
        failed=0,
        reclaimed_bytes=9,
        warnings=[],
        errors=[],
        started_at=datetime.now(UTC).isoformat(),
        completed_at="",
        trace_id=None,
        action_results=[
            MaintenanceActionResult(
                first_action.action_id,
                "temporary_files",
                "completed",
                reclaimed_bytes=9,
            )
        ],
    )
    runtime.maintenance.executions.put(
        plan.plan_id, asdict(interrupted), create_only=True
    )
    executing = replace(plan, status="executing", revision=2)
    runtime.maintenance.plans.put(
        plan.plan_id, asdict(executing), expected_revision=1
    )

    restarted = runtime_at(data_dir)
    recovered = restarted.maintenance.get_plan(plan.plan_id)
    reconciled = restarted.maintenance.history()[0]
    assert reconciled.status == "interrupted"
    assert reconciled.completed == 1
    assert second.exists()

    result = restarted.maintenance.execute(
        restarted.context(),
        MaintenanceExecutionRequest(
            recovered.plan_id,
            recovered.checksum,
            recovered.revision,
            True,
        ),
    )
    assert result.completed == 2
    assert result.attempted == 2
    assert not second.exists()
