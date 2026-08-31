from __future__ import annotations

from typing import Protocol

from synapse.maintenance.models import (
    MaintenanceAction,
    MaintenanceActionResult,
    MaintenanceInspectionRequest,
    MaintenanceInspectionResult,
    MaintenancePlanRequest,
)


class MaintenanceContributor(Protocol):
    contributor_id: str
    capabilities: frozenset[str]
    categories: frozenset[str]
    domain: str

    def inspect(self, request: MaintenanceInspectionRequest) -> MaintenanceInspectionResult: ...

    def plan_cleanup(self, request: MaintenancePlanRequest) -> list[MaintenanceAction]: ...

    def execute_cleanup(
        self, action: MaintenanceAction, *, dry_run: bool
    ) -> MaintenanceActionResult: ...
