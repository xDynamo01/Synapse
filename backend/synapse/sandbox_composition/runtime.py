"""Explicit local composition without global activation or execution facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from synapse.sandbox import (
    SANDBOX_RECORD_FORMAT,
    SANDBOX_SCHEMA_VERSION,
    SandboxAdmissionDecisionService,
    SandboxAdmissionFactsAssessmentService,
    SandboxAdmissionFactsProvider,
    SandboxAdmissionPolicy,
    SandboxApprovalFactsProvider,
    SandboxArtifactCustodyPort,
    SandboxArtifactFactsProvider,
    SandboxCancellationDecisionService,
    SandboxCancellationService,
    SandboxCapabilityGrantService,
    SandboxDeadlineService,
    SandboxExecutionPlanService,
    SandboxFilesystemGrantService,
    SandboxIsolationCapabilityProvider,
    SandboxMaterializationApplicationService,
    SandboxMaterializationPlanService,
    SandboxMaterializationVerificationPort,
    SandboxNetworkGrantService,
    SandboxPolicySnapshotProvider,
    SandboxProcessGrantService,
    SandboxResourceLimitService,
    SandboxResultMaterializationService,
    SandboxRuntimeDriverCapabilityFact,
    SandboxRuntimeIsolationPort,
    SandboxRuntimeMetricsPort,
    SandboxRuntimeObservationPort,
    SandboxRuntimeSupervisionApplicationService,
    SandboxRuntimeSupervisionService,
    SandboxRuntimeTerminationPort,
    SandboxSecretGrantService,
    SandboxSQLiteConfig,
    SandboxSQLiteDatabase,
    SandboxTerminationEscalationService,
    SandboxWorkloadStartPort,
    SandboxWorkspacePreparationPort,
    SQLiteSandboxAdmissionStore,
    SQLiteSandboxCatalogStore,
    SQLiteSandboxLifecycleStore,
    SQLiteSandboxRecoveryReader,
    SQLiteSandboxResultStore,
    canonical_bytes,
    content_fingerprint,
)
from synapse.sandbox.errors import SandboxPersistenceError
from synapse.sandbox_integrations import SandboxSkillsHandoffAdapter


class SandboxRuntimeBuildError(RuntimeError):
    pass


class SandboxRuntimeClosedError(RuntimeError):
    pass


class SandboxRuntimeCloseError(RuntimeError):
    pass


class SandboxManagedResource(Protocol):
    def open(self) -> None: ...

    def close(self) -> None: ...

    def healthy(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class SandboxRuntimeFeatures:
    materialization: bool = False
    supervision: bool = False
    skills_handoff: bool = False


@dataclass(frozen=True, slots=True)
class SandboxRuntimePorts:
    admission_facts: SandboxAdmissionFactsProvider | None = None
    policies: SandboxPolicySnapshotProvider | None = None
    approvals: SandboxApprovalFactsProvider | None = None
    artifacts: SandboxArtifactFactsProvider | None = None
    isolation_capabilities: SandboxIsolationCapabilityProvider | None = None
    custody: SandboxArtifactCustodyPort | None = None
    workspace: SandboxWorkspacePreparationPort | None = None
    materialization_verification: SandboxMaterializationVerificationPort | None = None
    workload_start: SandboxWorkloadStartPort | None = None
    runtime_observation: SandboxRuntimeObservationPort | None = None
    runtime_termination: SandboxRuntimeTerminationPort | None = None
    runtime_metrics: SandboxRuntimeMetricsPort | None = None
    runtime_isolation: SandboxRuntimeIsolationPort | None = None
    managed_resources: tuple[SandboxManagedResource, ...] = ()


@dataclass(frozen=True, kw_only=True, slots=True)
class SandboxRuntimeConfig:
    database_path: Path
    database_reference: str
    migration_applied_at: datetime
    admission_policy: SandboxAdmissionPolicy
    isolation_capability_facts: tuple[SandboxRuntimeDriverCapabilityFact, ...] = ()
    schema_version: int = SANDBOX_SCHEMA_VERSION
    record_format: str = SANDBOX_RECORD_FORMAT
    features: SandboxRuntimeFeatures = SandboxRuntimeFeatures()
    ports: SandboxRuntimePorts = SandboxRuntimePorts()
    skills_handoff_adapter: SandboxSkillsHandoffAdapter | None = None


@dataclass(frozen=True, slots=True)
class SandboxApplicationServices:
    canonicalize: Callable[[object], bytes]
    fingerprint: Callable[[object], str]
    admission_assessment: SandboxAdmissionFactsAssessmentService
    admission_decisions: SandboxAdmissionDecisionService
    execution_plans: SandboxExecutionPlanService
    capability_grants: SandboxCapabilityGrantService
    filesystem_grants: SandboxFilesystemGrantService
    network_grants: SandboxNetworkGrantService
    process_grants: SandboxProcessGrantService
    resource_limits: SandboxResourceLimitService
    secret_grants: SandboxSecretGrantService
    materialization_plans: SandboxMaterializationPlanService
    materialization: SandboxMaterializationApplicationService | None
    supervision_reducer: SandboxRuntimeSupervisionService
    supervision: SandboxRuntimeSupervisionApplicationService | None
    deadlines: SandboxDeadlineService
    cancellation_decisions: SandboxCancellationDecisionService
    termination_escalation: SandboxTerminationEscalationService
    cancellation: SandboxCancellationService
    results: SandboxResultMaterializationService


@dataclass(frozen=True, slots=True)
class SandboxPersistenceStores:
    catalog: SQLiteSandboxCatalogStore
    admission: SQLiteSandboxAdmissionStore
    lifecycle: SQLiteSandboxLifecycleStore
    results: SQLiteSandboxResultStore
    recovery: SQLiteSandboxRecoveryReader


@dataclass(frozen=True, slots=True)
class SandboxConfiguredAdapters:
    admission_facts: SandboxAdmissionFactsProvider | None
    policies: SandboxPolicySnapshotProvider | None
    approvals: SandboxApprovalFactsProvider | None
    artifacts: SandboxArtifactFactsProvider | None
    isolation_capabilities: SandboxIsolationCapabilityProvider | None
    skills_handoff: SandboxSkillsHandoffAdapter | None


@dataclass(frozen=True, slots=True)
class SandboxRuntimeHealth:
    open: bool
    persistence_available: bool
    schema_valid: bool
    configured_adapters: tuple[str, ...]
    materialization_ports_available: bool
    supervision_ports_available: bool
    managed_resources_healthy: bool
    isolation_driver_available: bool
    real_execution_available: bool
    recovery_finding_count: int


DatabaseFactory = Callable[[SandboxSQLiteConfig], SandboxSQLiteDatabase]


class SandboxRuntime:
    def __init__(
        self,
        *,
        database: SandboxSQLiteDatabase,
        policy: SandboxAdmissionPolicy,
        isolation_capability_facts: tuple[SandboxRuntimeDriverCapabilityFact, ...],
        services: SandboxApplicationServices,
        stores: SandboxPersistenceStores,
        adapters: SandboxConfiguredAdapters,
        managed_resources: tuple[SandboxManagedResource, ...],
    ) -> None:
        self._database = database
        self._policy = policy
        self._isolation_capability_facts = isolation_capability_facts
        self._services = services
        self._stores = stores
        self._adapters = adapters
        self._managed_resources = managed_resources
        self._closed = False

    @property
    def policy(self) -> SandboxAdmissionPolicy:
        self._ensure_open()
        return self._policy

    @property
    def isolation_capability_facts(self) -> tuple[SandboxRuntimeDriverCapabilityFact, ...]:
        self._ensure_open()
        return self._isolation_capability_facts

    @property
    def services(self) -> SandboxApplicationServices:
        self._ensure_open()
        return self._services

    @property
    def stores(self) -> SandboxPersistenceStores:
        self._ensure_open()
        return self._stores

    @property
    def adapters(self) -> SandboxConfiguredAdapters:
        self._ensure_open()
        return self._adapters

    def health(self) -> SandboxRuntimeHealth:
        persistence_available = False
        schema_valid = False
        recovery_count = 0
        if not self._closed:
            try:
                self._database.verify()
                persistence_available = True
                schema_valid = True
                recovery_count = len(self._stores.recovery.findings())
            except SandboxPersistenceError:
                pass
        configured = tuple(
            name
            for name, value in (
                ("admission_facts", self._adapters.admission_facts),
                ("policies", self._adapters.policies),
                ("approvals", self._adapters.approvals),
                ("artifacts", self._adapters.artifacts),
                ("isolation_capabilities", self._adapters.isolation_capabilities),
                ("skills_handoff", self._adapters.skills_handoff),
            )
            if value is not None
        )
        resources_healthy = not self._closed and all(
            resource.healthy() for resource in self._managed_resources
        )
        return SandboxRuntimeHealth(
            not self._closed,
            persistence_available,
            schema_valid,
            configured,
            self._services.materialization is not None and not self._closed,
            self._services.supervision is not None and not self._closed,
            resources_healthy,
            False,
            False,
            recovery_count,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        failures = _close_resources(self._managed_resources)
        if failures:
            raise SandboxRuntimeCloseError("sandbox runtime resource close failed")

    def _ensure_open(self) -> None:
        if self._closed:
            raise SandboxRuntimeClosedError("sandbox runtime is closed")


class SandboxRuntimeBuilder:
    def __init__(self, database_factory: DatabaseFactory = SandboxSQLiteDatabase) -> None:
        self._database_factory = database_factory

    def build(self, config: SandboxRuntimeConfig) -> SandboxRuntime:
        self._validate(config)
        opened: list[SandboxManagedResource] = []
        try:
            for resource in config.ports.managed_resources:
                resource.open()
                opened.append(resource)
            database = self._database_factory(SandboxSQLiteConfig(config.database_path))
            database.migrate(config.migration_applied_at)
            services = self._services(config)
            stores = SandboxPersistenceStores(
                SQLiteSandboxCatalogStore(database),
                SQLiteSandboxAdmissionStore(database),
                SQLiteSandboxLifecycleStore(database),
                SQLiteSandboxResultStore(database),
                SQLiteSandboxRecoveryReader(database),
            )
            adapters = SandboxConfiguredAdapters(
                config.ports.admission_facts,
                config.ports.policies,
                config.ports.approvals,
                config.ports.artifacts,
                config.ports.isolation_capabilities,
                config.skills_handoff_adapter,
            )
            return SandboxRuntime(
                database=database,
                policy=config.admission_policy,
                isolation_capability_facts=config.isolation_capability_facts,
                services=services,
                stores=stores,
                adapters=adapters,
                managed_resources=tuple(opened),
            )
        except Exception as exc:
            cleanup_failures = _close_resources(tuple(opened))
            if cleanup_failures:
                raise SandboxRuntimeBuildError("sandbox runtime build and cleanup failed") from exc
            if isinstance(exc, SandboxRuntimeBuildError):
                raise
            raise SandboxRuntimeBuildError("sandbox runtime build failed") from exc

    @staticmethod
    def _validate(config: SandboxRuntimeConfig) -> None:
        if not isinstance(config, SandboxRuntimeConfig):
            raise SandboxRuntimeBuildError("sandbox runtime configuration is invalid")
        if (
            config.schema_version != SANDBOX_SCHEMA_VERSION
            or config.record_format != SANDBOX_RECORD_FORMAT
            or not config.database_reference
            or not isinstance(config.database_path, Path)
            or not isinstance(config.admission_policy, SandboxAdmissionPolicy)
            or config.migration_applied_at.tzinfo is None
            or config.migration_applied_at.utcoffset() is None
        ):
            raise SandboxRuntimeBuildError("sandbox runtime configuration is invalid")
        materialization_ports = (
            config.ports.custody,
            config.ports.workspace,
            config.ports.materialization_verification,
        )
        supervision_ports = (
            config.ports.workload_start,
            config.ports.runtime_observation,
            config.ports.runtime_termination,
            config.ports.runtime_metrics,
            config.ports.runtime_isolation,
        )
        if config.features.materialization != all(
            item is not None for item in materialization_ports
        ):
            raise SandboxRuntimeBuildError("materialization ports are incomplete")
        if config.features.supervision != all(item is not None for item in supervision_ports):
            raise SandboxRuntimeBuildError("supervision ports are incomplete")
        if config.features.skills_handoff != (config.skills_handoff_adapter is not None):
            raise SandboxRuntimeBuildError("Skills handoff configuration is inconsistent")

    @staticmethod
    def _services(config: SandboxRuntimeConfig) -> SandboxApplicationServices:
        ports = config.ports
        materialization = (
            SandboxMaterializationApplicationService(
                ports.custody,
                ports.workspace,
                ports.materialization_verification,
            )
            if ports.custody is not None
            and ports.workspace is not None
            and ports.materialization_verification is not None
            else None
        )
        supervision = (
            SandboxRuntimeSupervisionApplicationService(
                ports.workload_start,
                ports.runtime_observation,
                ports.runtime_termination,
                ports.runtime_metrics,
                ports.runtime_isolation,
            )
            if ports.workload_start is not None
            and ports.runtime_observation is not None
            and ports.runtime_termination is not None
            and ports.runtime_metrics is not None
            and ports.runtime_isolation is not None
            else None
        )
        return SandboxApplicationServices(
            canonical_bytes,
            content_fingerprint,
            SandboxAdmissionFactsAssessmentService(),
            SandboxAdmissionDecisionService(),
            SandboxExecutionPlanService(),
            SandboxCapabilityGrantService(),
            SandboxFilesystemGrantService(),
            SandboxNetworkGrantService(),
            SandboxProcessGrantService(),
            SandboxResourceLimitService(),
            SandboxSecretGrantService(),
            SandboxMaterializationPlanService(),
            materialization,
            SandboxRuntimeSupervisionService(),
            supervision,
            SandboxDeadlineService(),
            SandboxCancellationDecisionService(),
            SandboxTerminationEscalationService(),
            SandboxCancellationService(),
            SandboxResultMaterializationService(),
        )


def _close_resources(
    resources: tuple[SandboxManagedResource, ...],
) -> tuple[SandboxManagedResource, ...]:
    failures: list[SandboxManagedResource] = []
    for resource in reversed(resources):
        try:
            resource.close()
        except Exception:
            failures.append(resource)
    return tuple(failures)
