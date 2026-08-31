from __future__ import annotations

import os
import time
from pathlib import Path

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.maintenance.models import (
    MaintenanceExecutionRequest,
    MaintenancePlanRequest,
    MaintenanceScope,
    MaintenanceScopeKind,
)
from synapse.policies.models import PolicyRule

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _runtime(data_dir: Path):
    return create_runtime(
        Settings(
            project_root=PROJECT_ROOT,
            data_dir=data_dir,
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
    )


def test_planned_cleanup_survives_restart_without_automatic_execution(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    first = _runtime(data_dir)
    candidate = first.data_dir.resolve("cache/restart.tmp")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("temporary", encoding="utf-8")
    old = time.time() - 26 * 3600
    os.utime(candidate, (old, old))
    first.policies.create_rule(
        PolicyRule(
            scope="user",
            subject="local_owner",
            action="maintenance.execute",
            resource="maintenance:temporary_files",
            effect="allow",
            source="acceptance",
        )
    )
    plan = first.maintenance.create_plan(
        first.context(),
        MaintenancePlanRequest(
            scope=MaintenanceScope(
                MaintenanceScopeKind.CONTRIBUTOR, "temporary_files"
            ),
            dry_run=False,
        ),
    )

    restarted = _runtime(data_dir)

    assert candidate.exists()
    recovered = restarted.maintenance.get_plan(plan.plan_id)
    assert recovered.status == "planned"
    result = restarted.maintenance.execute(
        restarted.context(),
        MaintenanceExecutionRequest(
            recovered.plan_id,
            recovered.checksum,
            recovered.revision,
            True,
        ),
    )
    assert result.status == "completed"
    assert not candidate.exists()
