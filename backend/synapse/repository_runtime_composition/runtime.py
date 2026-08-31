"""Explicit local composition without global bootstrap activation."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from synapse.repository_runtime import (
    REPOSITORY_MIGRATION_V1_CHECKSUM,
    REPOSITORY_RECORD_FORMAT,
    REPOSITORY_SCHEMA_VERSION,
    RepositoryAdapterCapability,
    RepositoryAdapterCapabilityReport,
    RepositoryAdapterCapabilityState,
    RepositoryAdapterFeature,
    RepositoryAuthorizationAssessmentService,
    RepositoryChangeSetService,
    RepositoryCheckoutIdentity,
    RepositoryIdentity,
    RepositoryLocalAdapter,
    RepositoryLocalAdapterConfig,
    RepositoryMutationApplicationService,
    RepositoryMutationMaterial,
    RepositoryMutationPlan,
    RepositoryMutationPlanService,
    RepositoryObservationService,
    RepositoryPathClassificationService,
    RepositoryPersistenceError,
    RepositoryPlatformProfile,
    RepositoryRecoveryMaterial,
    RepositoryRecoveryPlan,
    RepositoryRecoveryService,
    RepositoryRestorePointManifest,
    RepositoryRestorePointService,
    RepositorySnapshotService,
    RepositorySQLiteConfig,
    RepositorySQLiteDatabase,
    RepositoryVerificationService,
    RepositoryWorktreeIdentity,
    SQLiteRepositoryMutationLifecycleStore,
    SQLiteRepositoryObservationSnapshotStore,
    SQLiteRepositoryPlanningAuthorizationStore,
    SQLiteRepositoryRecoveryEvidenceStore,
)
from synapse.repository_runtime_integrations import CodingSessionRepositoryIntentAdapter

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


class RepositoryRuntimeBuildError(RuntimeError):
    pass


class RepositoryRuntimeClosedError(RuntimeError):
    pass


class RepositoryRuntimeCloseError(RuntimeError):
    pass


class RepositoryRuntimeManagedResource(Protocol):
    def open(self) -> None: ...

    def close(self) -> None: ...

    def healthy(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class RepositoryRuntimeFeatureDeclaration:
    required_supported: tuple[RepositoryAdapterFeature, ...] = ()
    allowed_degraded: tuple[RepositoryAdapterFeature, ...] = (
        RepositoryAdapterFeature.ENCODINGS,
        RepositoryAdapterFeature.MUTATION,
        RepositoryAdapterFeature.RECOVERY,
        RepositoryAdapterFeature.SUBMODULES,
        RepositoryAdapterFeature.NESTED_REPOSITORIES,
    )
    required_unsupported: tuple[RepositoryAdapterFeature, ...] = (
        RepositoryAdapterFeature.STAGING,
        RepositoryAdapterFeature.COMMIT,
        RepositoryAdapterFeature.PUSH,
    )

    def __post_init__(self) -> None:
        supported = tuple(sorted(set(self.required_supported), key=lambda item: item.value))
        degraded = tuple(sorted(set(self.allowed_degraded), key=lambda item: item.value))
        unsupported = tuple(sorted(set(self.required_unsupported), key=lambda item: item.value))
        if (
            (set(supported) & set(degraded))
            or (set(supported) & set(unsupported))
            or (set(degraded) & set(unsupported))
        ):
            raise RepositoryRuntimeBuildError("repository feature declaration overlaps")
        object.__setattr__(self, "required_supported", supported)
        object.__setattr__(self, "allowed_degraded", degraded)
        object.__setattr__(self, "required_unsupported", unsupported)


@dataclass(frozen=True, kw_only=True, slots=True)
class RepositoryRuntimeConfig:
    repository_root: Path
    repository_reference: str
    restore_root: Path
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity
    platform_profile: RepositoryPlatformProfile
    persistence_path: Path
    persistence_reference: str
    migration_applied_at: datetime
    schema_version: int = REPOSITORY_SCHEMA_VERSION
    record_format: str = REPOSITORY_RECORD_FORMAT
    migration_checksum: str = REPOSITORY_MIGRATION_V1_CHECKSUM
    adapter_kind: str = "repository-local-hybrid"
    adapter_version: str = "v1"
    features: RepositoryRuntimeFeatureDeclaration = RepositoryRuntimeFeatureDeclaration()
    coding_sessions_enabled: bool = False
    coding_sessions_adapter: CodingSessionRepositoryIntentAdapter | None = None
    managed_resources: tuple[RepositoryRuntimeManagedResource, ...] = ()
    mutation_plan: RepositoryMutationPlan | None = None
    mutation_materials: tuple[RepositoryMutationMaterial, ...] = ()
    recovery_plan: RepositoryRecoveryPlan | None = None
    recovery_materials: tuple[RepositoryRecoveryMaterial, ...] = ()
    restore_manifest: RepositoryRestorePointManifest | None = None


@dataclass(frozen=True, slots=True)
class RepositoryRuntimePersistence:
    observation_snapshots: SQLiteRepositoryObservationSnapshotStore
    planning_authorization: SQLiteRepositoryPlanningAuthorizationStore
    mutation_lifecycle: SQLiteRepositoryMutationLifecycleStore
    recovery_evidence: SQLiteRepositoryRecoveryEvidenceStore


@dataclass(frozen=True, slots=True)
class RepositoryRuntimeAdapters:
    local: RepositoryLocalAdapter
    coding_sessions: CodingSessionRepositoryIntentAdapter | None


@dataclass(frozen=True, slots=True)
class RepositoryRuntimeHealth:
    open: bool
    persistence_available: bool
    schema_valid: bool
    schema_version: int
    record_format: str
    migration_checksum: str
    local_adapter_available: bool
    adapter_kind: str
    adapter_version: str
    git_available: bool
    git_version: str | None
    platform_profile: RepositoryPlatformProfile
    supported_features: tuple[RepositoryAdapterFeature, ...]
    degraded_features: tuple[RepositoryAdapterFeature, ...]
    unsupported_features: tuple[RepositoryAdapterFeature, ...]
    unavailable_features: tuple[RepositoryAdapterFeature, ...]
    coding_sessions_configured: bool
    managed_resources_healthy: bool


DatabaseFactory = Callable[[RepositorySQLiteConfig], RepositorySQLiteDatabase]
AdapterFactory = Callable[[RepositoryLocalAdapterConfig], RepositoryLocalAdapter]


class RepositoryRuntime:
    def __init__(
        self,
        *,
        config: RepositoryRuntimeConfig,
        database: RepositorySQLiteDatabase,
        persistence: RepositoryRuntimePersistence,
        adapters: RepositoryRuntimeAdapters,
        capabilities: RepositoryAdapterCapabilityReport,
        managed_resources: tuple[RepositoryRuntimeManagedResource, ...],
    ) -> None:
        self._config = config
        self._database = database
        self._persistence = persistence
        self._adapters = adapters
        self._capabilities = capabilities
        self._managed_resources = managed_resources
        self._closed = False
        self._observation = RepositoryObservationService()
        self._classification = RepositoryPathClassificationService()
        self._snapshots = RepositorySnapshotService()
        self._change_sets = RepositoryChangeSetService()
        self._mutation_planning = RepositoryMutationPlanService()
        self._authorization = RepositoryAuthorizationAssessmentService()
        self._restore_points = RepositoryRestorePointService()
        self._mutation_application = RepositoryMutationApplicationService()
        self._verification = RepositoryVerificationService()
        self._recovery = RepositoryRecoveryService()

    @property
    def observation(self) -> RepositoryObservationService:
        self._ensure_open()
        return self._observation

    @property
    def classification(self) -> RepositoryPathClassificationService:
        self._ensure_open()
        return self._classification

    @property
    def snapshots(self) -> RepositorySnapshotService:
        self._ensure_open()
        return self._snapshots

    @property
    def change_sets(self) -> RepositoryChangeSetService:
        self._ensure_open()
        return self._change_sets

    @property
    def mutation_planning(self) -> RepositoryMutationPlanService:
        self._ensure_open()
        return self._mutation_planning

    @property
    def authorization(self) -> RepositoryAuthorizationAssessmentService:
        self._ensure_open()
        return self._authorization

    @property
    def restore_points(self) -> RepositoryRestorePointService:
        self._ensure_open()
        return self._restore_points

    @property
    def mutation_application(self) -> RepositoryMutationApplicationService:
        self._ensure_open()
        return self._mutation_application

    @property
    def verification(self) -> RepositoryVerificationService:
        self._ensure_open()
        return self._verification

    @property
    def recovery(self) -> RepositoryRecoveryService:
        self._ensure_open()
        return self._recovery

    @property
    def persistence(self) -> RepositoryRuntimePersistence:
        self._ensure_open()
        return self._persistence

    @property
    def adapters(self) -> RepositoryRuntimeAdapters:
        self._ensure_open()
        return self._adapters

    def health(self) -> RepositoryRuntimeHealth:
        persistence_available = False
        schema_valid = False
        if not self._closed:
            try:
                self._database.verify()
                persistence_available = True
                schema_valid = True
            except RepositoryPersistenceError:
                pass
        grouped = _group_capabilities(self._capabilities.capabilities)
        resources_healthy = not self._closed and all(
            resource.healthy() for resource in self._managed_resources
        )
        return RepositoryRuntimeHealth(
            not self._closed,
            persistence_available,
            schema_valid,
            self._config.schema_version,
            self._config.record_format,
            self._config.migration_checksum,
            bool(self._capabilities.git_version) and not self._closed,
            self._capabilities.adapter_id,
            self._capabilities.adapter_version,
            bool(self._capabilities.git_version) and not self._closed,
            self._capabilities.git_version or None,
            self._config.platform_profile,
            grouped[RepositoryAdapterCapabilityState.SUPPORTED],
            grouped[RepositoryAdapterCapabilityState.DEGRADED],
            grouped[RepositoryAdapterCapabilityState.UNSUPPORTED],
            grouped[RepositoryAdapterCapabilityState.UNAVAILABLE],
            self._adapters.coding_sessions is not None and not self._closed,
            resources_healthy,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if _close_resources(self._managed_resources):
            raise RepositoryRuntimeCloseError("repository runtime resource close failed")

    def _ensure_open(self) -> None:
        if self._closed:
            raise RepositoryRuntimeClosedError("repository runtime is closed")


class RepositoryRuntimeBuilder:
    def __init__(
        self,
        database_factory: DatabaseFactory = RepositorySQLiteDatabase,
        adapter_factory: AdapterFactory = RepositoryLocalAdapter,
    ) -> None:
        self._database_factory = database_factory
        self._adapter_factory = adapter_factory

    def build(self, config: RepositoryRuntimeConfig) -> RepositoryRuntime:
        self._validate(config)
        opened: list[RepositoryRuntimeManagedResource] = []
        try:
            for resource in config.managed_resources:
                resource.open()
                opened.append(resource)
            database = self._database_factory(
                RepositorySQLiteConfig(str(config.persistence_path.resolve()))
            )
            database.migrate(config.migration_applied_at)
            local = self._adapter_factory(
                RepositoryLocalAdapterConfig(
                    str(config.repository_root.resolve()),
                    str(config.restore_root.resolve()),
                    config.repository_id,
                    config.checkout_id,
                    config.worktree_id,
                    config.platform_profile,
                    config.mutation_plan,
                    config.mutation_materials,
                    config.recovery_plan,
                    config.recovery_materials,
                    config.restore_manifest,
                )
            )
            capabilities = local.capability_report()
            self._validate_capabilities(config, capabilities)
            persistence = RepositoryRuntimePersistence(
                SQLiteRepositoryObservationSnapshotStore(database),
                SQLiteRepositoryPlanningAuthorizationStore(database),
                SQLiteRepositoryMutationLifecycleStore(database),
                SQLiteRepositoryRecoveryEvidenceStore(database),
            )
            adapters = RepositoryRuntimeAdapters(local, config.coding_sessions_adapter)
            return RepositoryRuntime(
                config=config,
                database=database,
                persistence=persistence,
                adapters=adapters,
                capabilities=capabilities,
                managed_resources=tuple(opened),
            )
        except Exception as exc:
            cleanup_failures = _close_resources(tuple(opened))
            if cleanup_failures:
                raise RepositoryRuntimeBuildError(
                    "repository runtime build and cleanup failed"
                ) from exc
            if isinstance(exc, RepositoryRuntimeBuildError):
                raise
            raise RepositoryRuntimeBuildError("repository runtime build failed") from exc

    @staticmethod
    def _validate(config: RepositoryRuntimeConfig) -> None:
        if not isinstance(config, RepositoryRuntimeConfig):
            raise RepositoryRuntimeBuildError("repository runtime configuration is invalid")
        references = (config.repository_reference, config.persistence_reference)
        if (
            not all(_REFERENCE.fullmatch(value) for value in references)
            or config.schema_version != REPOSITORY_SCHEMA_VERSION
            or config.record_format != REPOSITORY_RECORD_FORMAT
            or config.migration_checksum != REPOSITORY_MIGRATION_V1_CHECKSUM
            or config.adapter_kind != "repository-local-hybrid"
            or config.adapter_version != "v1"
            or not isinstance(config.repository_root, Path)
            or not config.repository_root.is_absolute()
            or not config.repository_root.is_dir()
            or not isinstance(config.restore_root, Path)
            or not config.restore_root.is_absolute()
            or not isinstance(config.persistence_path, Path)
            or not config.persistence_path.is_absolute()
            or not config.persistence_path.parent.is_dir()
            or config.migration_applied_at.tzinfo is None
            or config.migration_applied_at.utcoffset() is None
            or config.coding_sessions_enabled != (config.coding_sessions_adapter is not None)
            or config.mutation_plan is None
            and bool(config.mutation_materials)
            or config.recovery_plan is None
            and bool(config.recovery_materials)
        ):
            raise RepositoryRuntimeBuildError("repository runtime configuration is invalid")
        binding = (
            config.repository_id,
            config.checkout_id,
            config.worktree_id,
            config.platform_profile,
        )
        for artifact in (
            config.mutation_plan,
            config.recovery_plan,
            config.restore_manifest,
        ):
            if (
                artifact is not None
                and (
                    artifact.repository_id,
                    artifact.checkout_id,
                    artifact.worktree_id,
                    artifact.platform_profile,
                )
                != binding
            ):
                raise RepositoryRuntimeBuildError("repository artifact binding mismatch")

    @staticmethod
    def _validate_capabilities(
        config: RepositoryRuntimeConfig, report: RepositoryAdapterCapabilityReport
    ) -> None:
        if (
            report.adapter_id != config.adapter_kind
            or report.adapter_version != config.adapter_version
        ):
            raise RepositoryRuntimeBuildError("repository adapter identity mismatch")
        states = {item.feature: item.state for item in report.capabilities}
        declaration = config.features
        if any(
            states.get(feature) is not RepositoryAdapterCapabilityState.SUPPORTED
            for feature in declaration.required_supported
        ):
            raise RepositoryRuntimeBuildError("required repository capability unavailable")
        if any(
            states.get(feature)
            not in {
                RepositoryAdapterCapabilityState.SUPPORTED,
                RepositoryAdapterCapabilityState.DEGRADED,
            }
            for feature in declaration.allowed_degraded
        ):
            raise RepositoryRuntimeBuildError("repository degraded capability unavailable")
        if any(
            states.get(feature) is not RepositoryAdapterCapabilityState.UNSUPPORTED
            for feature in declaration.required_unsupported
        ):
            raise RepositoryRuntimeBuildError("unsupported repository feature was widened")
        if not report.git_version:
            raise RepositoryRuntimeBuildError("Git adapter is unavailable")


def _group_capabilities(
    capabilities: tuple[RepositoryAdapterCapability, ...],
) -> dict[RepositoryAdapterCapabilityState, tuple[RepositoryAdapterFeature, ...]]:
    return {
        state: tuple(
            sorted(
                (item.feature for item in capabilities if item.state is state),
                key=lambda item: item.value,
            )
        )
        for state in RepositoryAdapterCapabilityState
    }


def _close_resources(
    resources: tuple[RepositoryRuntimeManagedResource, ...],
) -> tuple[RepositoryRuntimeManagedResource, ...]:
    failures: list[RepositoryRuntimeManagedResource] = []
    for resource in reversed(resources):
        try:
            resource.close()
        except Exception:
            failures.append(resource)
    return tuple(failures)
