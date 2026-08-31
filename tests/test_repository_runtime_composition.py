from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from tests.test_repository_runtime_persistence import draft
from tests.test_repository_runtime_snapshots import identities, profile

from synapse.repository_runtime import (
    REPOSITORY_MIGRATION_V1_CHECKSUM,
    REPOSITORY_RECORD_FORMAT,
    REPOSITORY_SCHEMA_VERSION,
    RepositoryAdapterFeature,
    RepositoryArtifactKind,
    RepositoryLocalAdapterConfig,
    RepositoryPersistedLifecycleState,
    RepositoryPersistenceUnavailable,
    RepositoryRecordCompleteness,
    RepositorySQLiteConfig,
    RepositorySQLiteDatabase,
    RepositoryStoreResponsibility,
)
from synapse.repository_runtime_composition import (
    RepositoryRuntimeBuilder,
    RepositoryRuntimeBuildError,
    RepositoryRuntimeClosedError,
    RepositoryRuntimeConfig,
)
from synapse.repository_runtime_integrations import CodingSessionRepositoryIntentAdapter

NOW = datetime(2026, 8, 8, 15, tzinfo=timezone.utc)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Composition Test")
    git(root, "config", "user.email", "composition@example.invalid")
    (root / "tracked.txt").write_bytes(b"unchanged")
    git(root, "add", "tracked.txt")
    git(root, "commit", "-m", "base")
    return root


def config(repository: Path, tmp_path: Path, **changes: object) -> RepositoryRuntimeConfig:
    repository_id, checkout_id, worktree_id = identities()
    base = RepositoryRuntimeConfig(
        repository_root=repository.resolve(),
        repository_reference="repository:local",
        restore_root=(tmp_path / "restore").resolve(),
        repository_id=repository_id,
        checkout_id=checkout_id,
        worktree_id=worktree_id,
        platform_profile=profile(),
        persistence_path=(tmp_path / "repository-runtime.db").resolve(),
        persistence_reference="persistence:local",
        migration_applied_at=NOW,
    )
    return replace(base, **changes)


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


class FailingDatabase(RepositorySQLiteDatabase):
    def migrate(self, applied_at: datetime) -> None:
        raise RepositoryPersistenceUnavailable("injected migration failure")


def unavailable_adapter(config: RepositoryLocalAdapterConfig):
    raise RuntimeError("injected adapter unavailable")


def test_minimal_configuration_builds_explicit_runtime_without_mutation(
    repository: Path, tmp_path: Path
) -> None:
    before_head = git(repository, "rev-parse", "HEAD")
    before_status = git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    runtime = RepositoryRuntimeBuilder().build(config(repository, tmp_path))
    assert runtime.observation is not None
    assert runtime.classification is not None
    assert runtime.snapshots is not None
    assert runtime.change_sets is not None
    assert runtime.mutation_planning is not None
    assert runtime.authorization is not None
    assert runtime.restore_points is not None
    assert runtime.mutation_application is not None
    assert runtime.verification is not None
    assert runtime.recovery is not None
    assert not hasattr(runtime, "execute")
    assert runtime.adapters.coding_sessions is None
    assert git(repository, "rev-parse", "HEAD") == before_head
    assert git(repository, "status", "--porcelain=v1", "--untracked-files=all") == before_status
    runtime.close()


def test_complete_configuration_includes_optional_reference_only_integration(
    repository: Path, tmp_path: Path
) -> None:
    integration = CodingSessionRepositoryIntentAdapter()
    runtime = RepositoryRuntimeBuilder().build(
        config(
            repository,
            tmp_path,
            coding_sessions_enabled=True,
            coding_sessions_adapter=integration,
        )
    )
    assert runtime.adapters.coding_sessions is integration
    assert runtime.health().coding_sessions_configured
    runtime.close()


def test_invalid_configuration_fails_before_database_creation(
    repository: Path, tmp_path: Path
) -> None:
    selected = config(
        repository,
        tmp_path,
        schema_version=REPOSITORY_SCHEMA_VERSION + 1,
    )
    with pytest.raises(RepositoryRuntimeBuildError):
        RepositoryRuntimeBuilder().build(selected)
    assert not selected.persistence_path.exists()
    with pytest.raises(RepositoryRuntimeBuildError):
        RepositoryRuntimeBuilder().build(config(repository, tmp_path, coding_sessions_enabled=True))


def test_migration_mismatch_fails_closed(repository: Path, tmp_path: Path) -> None:
    selected = config(repository, tmp_path)
    first = RepositoryRuntimeBuilder().build(selected)
    first.close()
    database = RepositorySQLiteDatabase(RepositorySQLiteConfig(str(selected.persistence_path)))
    with database.connection() as connection:
        connection.execute("DROP TRIGGER repository_migration_history_no_update")
        connection.execute("UPDATE repository_migration_history SET checksum='sha256:changed'")
        connection.commit()
    with pytest.raises(RepositoryRuntimeBuildError):
        RepositoryRuntimeBuilder().build(selected)


def test_adapter_unavailable_and_partial_failure_close_open_resources(
    repository: Path, tmp_path: Path
) -> None:
    resource = ManagedResource()
    with pytest.raises(RepositoryRuntimeBuildError):
        RepositoryRuntimeBuilder(adapter_factory=unavailable_adapter).build(
            config(repository, tmp_path, managed_resources=(resource,))
        )
    assert (resource.open_count, resource.close_count, resource.is_open) == (1, 1, False)

    first = ManagedResource()
    second = ManagedResource()
    with pytest.raises(RepositoryRuntimeBuildError):
        RepositoryRuntimeBuilder(database_factory=FailingDatabase).build(
            config(repository, tmp_path, managed_resources=(first, second))
        )
    assert (first.close_count, second.close_count) == (1, 1)
    assert not first.is_open and not second.is_open


def test_restart_preserves_schema_record_and_recovery_state(
    repository: Path, tmp_path: Path
) -> None:
    selected = config(repository, tmp_path)
    first = RepositoryRuntimeBuilder().build(selected)
    record = first.persistence.recovery_evidence.append(
        draft(
            RepositoryStoreResponsibility.RECOVERY_EVIDENCE,
            RepositoryArtifactKind.RECOVERY_PLAN,
            "recovery:composition",
            state=RepositoryPersistedLifecycleState.RECOVERY_REQUIRED,
            completeness=RepositoryRecordCompleteness.PARTIAL,
        )
    ).record
    first.close()

    restarted = RepositoryRuntimeBuilder().build(selected)
    state = restarted.persistence.recovery_evidence.restart_state("repository:stream:one")
    assert state.records[0].semantic_fingerprint == record.semantic_fingerprint
    assert state.lifecycle_states == (RepositoryPersistedLifecycleState.RECOVERY_REQUIRED,)
    assert restarted.health().schema_valid
    restarted.close()


def test_close_is_idempotent_and_closed_runtime_rejects_operations(
    repository: Path, tmp_path: Path
) -> None:
    resource = ManagedResource()
    runtime = RepositoryRuntimeBuilder().build(
        config(repository, tmp_path, managed_resources=(resource,))
    )
    runtime.close()
    runtime.close()
    assert resource.close_count == 1
    assert not runtime.health().open
    with pytest.raises(RepositoryRuntimeClosedError):
        _ = runtime.observation
    with pytest.raises(RepositoryRuntimeClosedError):
        _ = runtime.persistence
    with pytest.raises(RepositoryRuntimeClosedError):
        _ = runtime.adapters


def test_health_reports_factual_schema_adapter_platform_and_feature_states(
    repository: Path, tmp_path: Path
) -> None:
    runtime = RepositoryRuntimeBuilder().build(config(repository, tmp_path))
    health = runtime.health()
    assert health.persistence_available and health.schema_valid
    assert health.schema_version == REPOSITORY_SCHEMA_VERSION
    assert health.record_format == REPOSITORY_RECORD_FORMAT
    assert health.migration_checksum == REPOSITORY_MIGRATION_V1_CHECKSUM
    assert health.local_adapter_available and health.git_available and health.git_version
    assert RepositoryAdapterFeature.MUTATION in health.degraded_features
    assert RepositoryAdapterFeature.RECOVERY in health.degraded_features
    assert RepositoryAdapterFeature.STAGING in health.unsupported_features
    assert RepositoryAdapterFeature.COMMIT in health.unsupported_features
    assert RepositoryAdapterFeature.PUSH in health.unsupported_features
    assert RepositoryAdapterFeature.STAGING not in health.supported_features
    runtime.close()
