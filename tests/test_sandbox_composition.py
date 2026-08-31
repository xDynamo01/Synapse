from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from tests.test_sandbox_admission_facts import NOW
from tests.test_sandbox_admission_policy import policy
from tests.test_sandbox_persistence import draft

from synapse.sandbox import (
    SandboxAdmissionPolicy,
    SandboxArtifactCustodyPort,
    SandboxArtifactKind,
    SandboxCompleteness,
    SandboxMaterializationVerificationPort,
    SandboxRecoveryState,
    SandboxRuntimeIsolationPort,
    SandboxRuntimeMetricsPort,
    SandboxRuntimeObservationPort,
    SandboxRuntimeTerminationPort,
    SandboxStoreResponsibility,
    SandboxWorkloadStartPort,
    SandboxWorkspacePreparationPort,
)
from synapse.sandbox.errors import SandboxPersistenceUnavailable
from synapse.sandbox.sqlite_persistence import SandboxSQLiteDatabase
from synapse.sandbox_composition import (
    SandboxRuntimeBuilder,
    SandboxRuntimeBuildError,
    SandboxRuntimeClosedError,
    SandboxRuntimeConfig,
    SandboxRuntimeFeatures,
    SandboxRuntimePorts,
)
from synapse.sandbox_integrations import SandboxSkillsHandoffAdapter


class ManagedResource:
    def __init__(self) -> None:
        self.open_count = 0
        self.close_count = 0
        self.is_open = False

    def open(self) -> None:
        self.open_count += 1
        self.is_open = True

    def close(self) -> None:
        self.close_count += 1
        self.is_open = False

    def healthy(self) -> bool:
        return self.is_open


class FailingDatabase(SandboxSQLiteDatabase):
    def migrate(self, applied_at: datetime) -> None:
        raise SandboxPersistenceUnavailable("injected migration failure")


def config(tmp_path: Path, **changes: object) -> SandboxRuntimeConfig:
    base = SandboxRuntimeConfig(
        database_path=(tmp_path / "sandbox-runtime.db").resolve(),
        database_reference="sandbox-database:local",
        migration_applied_at=NOW,
        admission_policy=policy(),
    )
    return replace(base, **changes)


def test_minimal_composition_is_explicit_healthy_for_storage_and_not_executable(
    tmp_path: Path,
) -> None:
    runtime = SandboxRuntimeBuilder().build(config(tmp_path))
    health = runtime.health()

    assert health.open
    assert health.persistence_available and health.schema_valid
    assert not health.materialization_ports_available
    assert not health.supervision_ports_available
    assert not health.isolation_driver_available
    assert not health.real_execution_available
    assert runtime.services.materialization is None
    assert runtime.services.supervision is None
    assert not hasattr(runtime, "execute")
    runtime.close()


def test_complete_abstract_port_composition_still_does_not_activate_execution(
    tmp_path: Path,
) -> None:
    ports = SandboxRuntimePorts(
        custody=cast(SandboxArtifactCustodyPort, object()),
        workspace=cast(SandboxWorkspacePreparationPort, object()),
        materialization_verification=cast(SandboxMaterializationVerificationPort, object()),
        workload_start=cast(SandboxWorkloadStartPort, object()),
        runtime_observation=cast(SandboxRuntimeObservationPort, object()),
        runtime_termination=cast(SandboxRuntimeTerminationPort, object()),
        runtime_metrics=cast(SandboxRuntimeMetricsPort, object()),
        runtime_isolation=cast(SandboxRuntimeIsolationPort, object()),
    )
    runtime = SandboxRuntimeBuilder().build(
        config(
            tmp_path,
            features=SandboxRuntimeFeatures(
                materialization=True, supervision=True, skills_handoff=True
            ),
            ports=ports,
            skills_handoff_adapter=SandboxSkillsHandoffAdapter(),
        )
    )
    health = runtime.health()
    assert health.materialization_ports_available
    assert health.supervision_ports_available
    assert health.configured_adapters == ("skills_handoff",)
    assert not health.isolation_driver_available
    assert not health.real_execution_available
    assert runtime.services.materialization is not None
    assert runtime.services.supervision is not None
    runtime.close()


def test_invalid_configuration_fails_before_database_or_runtime_is_exposed(
    tmp_path: Path,
) -> None:
    invalid = config(
        tmp_path,
        admission_policy=cast(SandboxAdmissionPolicy, None),
    )
    with pytest.raises(SandboxRuntimeBuildError):
        SandboxRuntimeBuilder().build(invalid)
    assert not invalid.database_path.exists()

    inconsistent = config(
        tmp_path,
        features=SandboxRuntimeFeatures(skills_handoff=True),
    )
    with pytest.raises(SandboxRuntimeBuildError):
        SandboxRuntimeBuilder().build(inconsistent)


def test_partial_build_failure_closes_resources_in_reverse_order(tmp_path: Path) -> None:
    first = ManagedResource()
    second = ManagedResource()
    runtime_config = config(
        tmp_path,
        ports=SandboxRuntimePorts(managed_resources=(first, second)),
    )
    builder = SandboxRuntimeBuilder(lambda sqlite_config: FailingDatabase(sqlite_config))
    with pytest.raises(SandboxRuntimeBuildError):
        builder.build(runtime_config)
    assert (first.open_count, first.close_count, first.is_open) == (1, 1, False)
    assert (second.open_count, second.close_count, second.is_open) == (1, 1, False)


def test_close_is_idempotent_and_closed_runtime_rejects_application_access(
    tmp_path: Path,
) -> None:
    resource = ManagedResource()
    runtime = SandboxRuntimeBuilder().build(
        config(
            tmp_path,
            ports=SandboxRuntimePorts(managed_resources=(resource,)),
        )
    )
    runtime.close()
    runtime.close()
    assert resource.close_count == 1
    assert not runtime.health().open
    with pytest.raises(SandboxRuntimeClosedError):
        _ = runtime.services
    with pytest.raises(SandboxRuntimeClosedError):
        _ = runtime.stores
    with pytest.raises(SandboxRuntimeClosedError):
        _ = runtime.adapters


def test_restart_preserves_schema_checksums_and_explicit_recovery_facts(
    tmp_path: Path,
) -> None:
    runtime_config = config(tmp_path)
    first = SandboxRuntimeBuilder().build(runtime_config)
    first.stores.lifecycle.append(
        draft(
            SandboxStoreResponsibility.LIFECYCLE,
            kind=SandboxArtifactKind.EXECUTION_ATTEMPT,
            identity="attempt:composition-restart",
            recovery=SandboxRecoveryState.ATTEMPT_INCOMPLETE,
            completeness=SandboxCompleteness.PARTIAL,
        )
    )
    fingerprint = first.stores.lifecycle.replay("attempt:one").records[0].semantic_fingerprint
    first.close()

    second = SandboxRuntimeBuilder().build(runtime_config)
    assert second.health().recovery_finding_count == 1
    assert (
        second.stores.lifecycle.replay("attempt:one").records[0].semantic_fingerprint == fingerprint
    )
    second.close()


def test_configured_policy_and_optional_skills_adapter_preserve_identity(
    tmp_path: Path,
) -> None:
    admission_policy = policy()
    runtime = SandboxRuntimeBuilder().build(
        config(
            tmp_path,
            admission_policy=admission_policy,
            features=SandboxRuntimeFeatures(skills_handoff=True),
            skills_handoff_adapter=SandboxSkillsHandoffAdapter(),
        )
    )
    assert runtime.policy is admission_policy
    assert runtime.policy.policy_fingerprint == admission_policy.policy_fingerprint
    assert isinstance(runtime.adapters.skills_handoff, SandboxSkillsHandoffAdapter)
    runtime.close()
