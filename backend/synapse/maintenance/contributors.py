from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from synapse.core.serialization import load_structured_file
from synapse.maintenance.models import (
    MaintenanceAction,
    MaintenanceActionResult,
    MaintenanceCapability,
    MaintenanceFinding,
    MaintenanceInspectionRequest,
    MaintenanceInspectionResult,
    MaintenancePlanRequest,
    MaintenanceScopeKind,
)

_AUTHORIZED_TEMP_ROOTS = ("cache", "temp", "tmp")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


class FoundationInspectionContributor:
    contributor_id = "foundation"
    domain = "foundation"
    capabilities = frozenset(
        {MaintenanceCapability.INSPECT.value, MaintenanceCapability.VALIDATE.value}
    )
    categories = frozenset({"escaped_symlink", "root_not_writable"})

    def __init__(self, data_dir: Any) -> None:
        self.data_dir = data_dir

    def inspect(self, request: MaintenanceInspectionRequest) -> MaintenanceInspectionResult:
        findings: list[MaintenanceFinding] = []
        for path in self.data_dir.root.rglob("*"):
            if not path.is_symlink():
                continue
            try:
                escaped = not path.resolve().is_relative_to(self.data_dir.root)
            except OSError:
                escaped = True
            if escaped:
                findings.append(
                    MaintenanceFinding(
                        contributor_id=self.contributor_id,
                        category="escaped_symlink",
                        severity="critical",
                        status="action_required",
                        summary="A symbolic link escapes the authorized data root.",
                        reference=_relative(path, self.data_dir.root),
                        recommended_action="manual_review",
                        safe_to_automate=False,
                        approval_required=True,
                        correlation_id=request.correlation_id,
                    )
                )
        if not os.access(self.data_dir.root, os.W_OK):
            findings.append(
                MaintenanceFinding(
                    contributor_id=self.contributor_id,
                    category="root_not_writable",
                    severity="critical",
                    status="action_required",
                    summary="The authorized data root is not writable.",
                    reference="foundation:root",
                    recommended_action="manual_review",
                    safe_to_automate=False,
                    approval_required=True,
                    correlation_id=request.correlation_id,
                )
            )
        return MaintenanceInspectionResult(
            contributor_id=self.contributor_id,
            status="ready" if not findings else "degraded",
            findings=findings,
            capabilities=sorted(self.capabilities),
        )

    def plan_cleanup(self, request: MaintenancePlanRequest) -> list[MaintenanceAction]:
        return []

    def execute_cleanup(
        self, action: MaintenanceAction, *, dry_run: bool
    ) -> MaintenanceActionResult:
        return MaintenanceActionResult(
            action.action_id, self.contributor_id, "skipped", warning="unsupported"
        )


class ConfigurationInspectionContributor:
    contributor_id = "configuration"
    domain = "foundation"
    capabilities = frozenset(
        {MaintenanceCapability.INSPECT.value, MaintenanceCapability.VALIDATE.value}
    )
    categories = frozenset({"invalid_configuration"})

    def __init__(self, data_dir: Any) -> None:
        self.data_dir = data_dir

    def inspect(self, request: MaintenanceInspectionRequest) -> MaintenanceInspectionResult:
        findings: list[MaintenanceFinding] = []
        for path in sorted(self.data_dir.resolve("config").glob("*.yaml")):
            try:
                load_structured_file(path)
            except Exception as exc:
                findings.append(
                    MaintenanceFinding(
                        contributor_id=self.contributor_id,
                        category="invalid_configuration",
                        severity="critical",
                        status="invalid",
                        summary="A configuration record is invalid.",
                        reference=f"config:{path.name}",
                        recommended_action="manual_review",
                        safe_to_automate=False,
                        approval_required=True,
                        correlation_id=request.correlation_id,
                        evidence={"error_code": type(exc).__name__},
                    )
                )
        return MaintenanceInspectionResult(
            contributor_id=self.contributor_id,
            status="ready" if not findings else "degraded",
            findings=findings,
            capabilities=sorted(self.capabilities),
        )

    def plan_cleanup(self, request: MaintenancePlanRequest) -> list[MaintenanceAction]:
        return []

    def execute_cleanup(
        self, action: MaintenanceAction, *, dry_run: bool
    ) -> MaintenanceActionResult:
        return MaintenanceActionResult(
            action.action_id, self.contributor_id, "skipped", warning="unsupported"
        )


class TemporaryFilesMaintenanceContributor:
    contributor_id = "temporary_files"
    domain = "foundation"
    capabilities = frozenset(
        {MaintenanceCapability.INSPECT.value, MaintenanceCapability.CLEANUP.value}
    )
    categories = frozenset({"expired_temporary_file"})

    def __init__(self, data_dir: Any) -> None:
        self.data_dir = data_dir

    def inspect(self, request: MaintenanceInspectionRequest) -> MaintenanceInspectionResult:
        findings = self._findings(24, request.correlation_id)
        return MaintenanceInspectionResult(
            contributor_id=self.contributor_id,
            status="ready",
            findings=findings,
            capabilities=sorted(self.capabilities),
        )

    def plan_cleanup(self, request: MaintenancePlanRequest) -> list[MaintenanceAction]:
        return [
            MaintenanceAction(
                contributor_id=self.contributor_id,
                category="expired_temporary_file",
                reference=finding.reference,
                estimated_bytes=finding.estimated_bytes,
                risk="moderate",
                approval_required=False,
                parameters={"older_than_hours": request.older_than_hours},
            )
            for finding in self._findings(request.older_than_hours, request.correlation_id)
        ]

    def execute_cleanup(
        self, action: MaintenanceAction, *, dry_run: bool
    ) -> MaintenanceActionResult:
        reference = Path(action.reference)
        if not reference.parts or reference.parts[0] not in _AUTHORIZED_TEMP_ROOTS:
            return MaintenanceActionResult(
                action.action_id,
                self.contributor_id,
                "failed",
                error_code="unauthorized_temporary_root",
            )
        path = self.data_dir.resolve(action.reference)
        if path.suffix != ".tmp" or path.is_symlink():
            return MaintenanceActionResult(
                action.action_id,
                self.contributor_id,
                "failed",
                error_code="unsafe_reference",
            )
        if not path.exists():
            return MaintenanceActionResult(
                action.action_id, self.contributor_id, "skipped", warning="already_absent"
            )
        hours = int(action.parameters.get("older_than_hours", 24))
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        if datetime.fromtimestamp(path.stat().st_mtime, UTC) >= cutoff:
            return MaintenanceActionResult(
                action.action_id, self.contributor_id, "skipped", warning="active_or_recent"
            )
        size = path.stat().st_size
        if not dry_run:
            path.unlink(missing_ok=True)
        return MaintenanceActionResult(
            action.action_id,
            self.contributor_id,
            "dry_run" if dry_run else "completed",
            reclaimed_bytes=0 if dry_run else size,
        )

    def _findings(self, older_than_hours: int, correlation_id: str) -> list[MaintenanceFinding]:
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        findings: list[MaintenanceFinding] = []
        for root_name in _AUTHORIZED_TEMP_ROOTS:
            root = self.data_dir.resolve(root_name)
            if not root.exists() or root.is_symlink():
                continue
            for path in sorted(root.rglob("*.tmp")):
                try:
                    resolved = path.resolve()
                    if path.is_symlink() or not resolved.is_relative_to(root):
                        continue
                    if datetime.fromtimestamp(path.stat().st_mtime, UTC) >= cutoff:
                        continue
                    findings.append(
                        MaintenanceFinding(
                            contributor_id=self.contributor_id,
                            category="expired_temporary_file",
                            severity="info",
                            status="cleanup_pending",
                            summary="A recognized temporary file is eligible for cleanup.",
                            reference=_relative(path, self.data_dir.root),
                            estimated_bytes=path.stat().st_size,
                            recommended_action="cleanup",
                            safe_to_automate=True,
                            approval_required=False,
                            correlation_id=correlation_id,
                        )
                    )
                except OSError:
                    continue
        return findings


class RetentionMaintenanceContributor:
    contributor_id = "retention"
    domain = "retention"
    capabilities = frozenset(
        {MaintenanceCapability.INSPECT.value, MaintenanceCapability.CLEANUP.value}
    )
    categories = frozenset({"retention_cleanup", "retention_cleanup_pending"})

    def __init__(self, retention: Any) -> None:
        self.retention = retention

    def inspect(self, request: MaintenanceInspectionRequest) -> MaintenanceInspectionResult:
        findings: list[MaintenanceFinding] = []
        for summary in self.retention.retention_status().domains:
            status = dict(summary.status)
            pending = int(status.get("cleanup_pending", status.get("expired", 0)) or 0)
            if pending:
                findings.append(
                    MaintenanceFinding(
                        contributor_id=self.contributor_id,
                        category="retention_cleanup_pending",
                        severity="warning",
                        status="cleanup_pending",
                        summary="A registered domain reports retention cleanup pending.",
                        reference=f"retention:{summary.domain_id}",
                        estimated_bytes=0,
                        recommended_action="cleanup",
                        safe_to_automate=False,
                        approval_required=True,
                        correlation_id=request.correlation_id,
                        evidence={"pending": pending},
                    )
                )
        return MaintenanceInspectionResult(
            contributor_id=self.contributor_id,
            status="ready",
            findings=findings,
            capabilities=sorted(self.capabilities),
        )

    def plan_cleanup(self, request: MaintenancePlanRequest) -> list[MaintenanceAction]:
        domain_ids = [item.domain_id for item in self.retention.list_domains()]
        if request.scope.kind is MaintenanceScopeKind.DOMAIN:
            domain_ids = [str(request.scope.value)]
            self.retention.get_domain(domain_ids[0])
        actions: list[MaintenanceAction] = []
        for domain_id in domain_ids:
            preview = self.retention.cleanup_domain(domain_id, dry_run=True)
            actions.append(
                MaintenanceAction(
                    contributor_id=self.contributor_id,
                    category="retention_cleanup",
                    reference=f"retention:{domain_id}",
                    estimated_bytes=0,
                    risk="high",
                    approval_required=True,
                    parameters={"domain_id": domain_id, "preview_scanned": preview.scanned},
                )
            )
        return actions

    def execute_cleanup(
        self, action: MaintenanceAction, *, dry_run: bool
    ) -> MaintenanceActionResult:
        domain_id = str(action.parameters.get("domain_id", ""))
        if action.reference != f"retention:{domain_id}":
            return MaintenanceActionResult(
                action.action_id,
                self.contributor_id,
                "failed",
                error_code="invalid_domain_reference",
            )
        result = self.retention.cleanup_domain(domain_id, dry_run=dry_run)
        return MaintenanceActionResult(
            action.action_id,
            self.contributor_id,
            "dry_run" if dry_run else ("completed" if result.success else "failed"),
            error_code=None if result.success else "domain_cleanup_failed",
        )
