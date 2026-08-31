"""Explicit local composition with no global activation or external execution."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from synapse.coding_sessions import (
    CODING_SESSION_CHECKPOINT_POLICY_VERSION,
    CODING_SESSION_CONTRACT_VERSION,
    CODING_SESSION_CONTROL_POLICY_VERSION,
    CODING_SESSION_INTENT_POLICY_VERSION,
    CODING_SESSION_LEASE_POLICY_VERSION,
    CODING_SESSION_LIFECYCLE_POLICY_VERSION,
    CODING_SESSION_RECORD_VERSION,
    CODING_SESSION_RECOVERY_POLICY_VERSION,
    CODING_SESSION_RESTART_POLICY_VERSION,
    CodingSessionCheckpointAssessment,
    CodingSessionContractAssessment,
    CodingSessionDomainError,
    CodingSessionIntentAssessment,
    CodingSessionJournalAssessment,
    CodingSessionLeaseAssessment,
    CodingSessionPauseAssessment,
    CodingSessionReceiptAssessment,
    CodingSessionReconciliationAssessment,
    CodingSessionRecoveryAssessment,
    CodingSessionRestartAssessment,
    CodingSessionResumeAssessment,
    CodingSessionTransitionAssessment,
)
from synapse.coding_sessions.sqlite_persistence import (
    CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM,
    CODING_SESSION_SQLITE_SCHEMA_VERSION,
    CodingSessionSQLiteConfig,
    CodingSessionSQLiteDatabase,
    SQLiteCodingSessionContractBindingsStore,
    SQLiteCodingSessionControlCancellationStore,
    SQLiteCodingSessionIntentsReceiptsStore,
    SQLiteCodingSessionJournalCheckpointsStore,
    SQLiteCodingSessionLifecycleCoordinationStore,
    SQLiteCodingSessionRecoveryOutcomeStore,
    SQLiteCodingSessionRestartReconciliationStore,
)
from synapse.coding_sessions_integrations import (
    CODING_SESSION_DEPLOYMENT_REFERENCE_VERSION,
    CODING_SESSION_GOVERNANCE_COMPATIBILITY_VERSION,
    CODING_SESSION_PRIVATE_EVALS_COMPATIBILITY_VERSION,
    CODING_SESSION_SANDBOX_COMPATIBILITY_VERSION,
    CODING_SESSION_WORK_COMPATIBILITY_VERSION,
    CodingSessionDeploymentReferenceService,
    CodingSessionGovernanceCompatibilityAdapter,
    CodingSessionPrivateEvalsCompatibilityAdapter,
    CodingSessionRepositoryCompatibilityAdapter,
    CodingSessionSandboxCompatibilityAdapter,
    CodingSessionWorkersMissionsCompatibilityAdapter,
)
from synapse.coding_sessions_integrations.repository_runtime import (
    CODING_SESSION_REPOSITORY_COMPATIBILITY_VERSION,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


class CodingSessionsRuntimeBuildError(RuntimeError):
    pass


class CodingSessionsRuntimeClosedError(RuntimeError):
    pass


class CodingSessionsRuntimeCloseError(RuntimeError):
    pass


class CodingSessionsManagedResource(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def healthy(self) -> bool: ...


class CodingSessionsCapability(str, Enum):
    PERSISTENCE = "persistence"
    REPOSITORY_RUNTIME = "repository-runtime"
    GOVERNANCE_APPROVALS = "governance-approvals"
    WORKERS_MISSIONS = "workers-missions"
    SANDBOX_REFERENCES = "sandbox-references"
    SANDBOX_CONCRETE_EXECUTION = "sandbox-concrete-execution"
    PRIVATE_EVALS = "private-evals"
    DEPLOYMENT_REFERENCES = "deployment-references"
    DEPLOYMENT_RUNTIME = "deployment-runtime"


class CodingSessionsCapabilityState(str, Enum):
    SUPPORTED = "supported"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionsIntegrationCapability:
    capability: CodingSessionsCapability
    state: CodingSessionsCapabilityState
    version: str


@dataclass(frozen=True, slots=True)
class CodingSessionsRuntimeConfig:
    persistence_path: Path
    persistence_reference: str
    migration_applied_at: str
    enabled_integrations: frozenset[CodingSessionsCapability] = frozenset()
    schema_version: int = CODING_SESSION_SQLITE_SCHEMA_VERSION
    record_version: str = CODING_SESSION_RECORD_VERSION
    migration_checksum: str = CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM
    policy_versions: tuple[tuple[str, str], ...] = (
        ("checkpoint", CODING_SESSION_CHECKPOINT_POLICY_VERSION),
        ("contract", CODING_SESSION_CONTRACT_VERSION),
        ("control", CODING_SESSION_CONTROL_POLICY_VERSION),
        ("intent", CODING_SESSION_INTENT_POLICY_VERSION),
        ("lease", CODING_SESSION_LEASE_POLICY_VERSION),
        ("lifecycle", CODING_SESSION_LIFECYCLE_POLICY_VERSION),
        ("recovery", CODING_SESSION_RECOVERY_POLICY_VERSION),
        ("restart", CODING_SESSION_RESTART_POLICY_VERSION),
    )
    sandbox_driver_available: bool = False
    deployment_runtime_available: bool = False
    managed_resources: tuple[CodingSessionsManagedResource, ...] = ()


@dataclass(frozen=True, slots=True)
class CodingSessionsPersistence:
    contracts: SQLiteCodingSessionContractBindingsStore
    lifecycle: SQLiteCodingSessionLifecycleCoordinationStore
    intents: SQLiteCodingSessionIntentsReceiptsStore
    journal: SQLiteCodingSessionJournalCheckpointsStore
    control: SQLiteCodingSessionControlCancellationStore
    restart: SQLiteCodingSessionRestartReconciliationStore
    recovery: SQLiteCodingSessionRecoveryOutcomeStore


@dataclass(frozen=True, slots=True)
class CodingSessionsDomainServices:
    contracts: type[CodingSessionContractAssessment] = CodingSessionContractAssessment
    lifecycle: type[CodingSessionTransitionAssessment] = CodingSessionTransitionAssessment
    leases: type[CodingSessionLeaseAssessment] = CodingSessionLeaseAssessment
    intents: type[CodingSessionIntentAssessment] = CodingSessionIntentAssessment
    receipts: type[CodingSessionReceiptAssessment] = CodingSessionReceiptAssessment
    journal: type[CodingSessionJournalAssessment] = CodingSessionJournalAssessment
    checkpoints: type[CodingSessionCheckpointAssessment] = CodingSessionCheckpointAssessment
    pause: type[CodingSessionPauseAssessment] = CodingSessionPauseAssessment
    resume: type[CodingSessionResumeAssessment] = CodingSessionResumeAssessment
    restart: type[CodingSessionRestartAssessment] = CodingSessionRestartAssessment
    reconciliation: type[CodingSessionReconciliationAssessment] = CodingSessionReconciliationAssessment
    recovery: type[CodingSessionRecoveryAssessment] = CodingSessionRecoveryAssessment


@dataclass(frozen=True, slots=True)
class CodingSessionsIntegrations:
    repository: CodingSessionRepositoryCompatibilityAdapter | None
    governance: CodingSessionGovernanceCompatibilityAdapter | None
    workers_missions: CodingSessionWorkersMissionsCompatibilityAdapter | None
    sandbox: CodingSessionSandboxCompatibilityAdapter | None
    private_evals: CodingSessionPrivateEvalsCompatibilityAdapter | None
    deployment: CodingSessionDeploymentReferenceService | None


@dataclass(frozen=True, slots=True)
class CodingSessionsHealth:
    open: bool
    persistence_available: bool
    schema_valid: bool
    schema_version: int
    record_version: str
    migration_checksum: str
    integrations: tuple[CodingSessionsIntegrationCapability, ...]
    managed_resources_healthy: bool


DatabaseFactory = Callable[[CodingSessionSQLiteConfig], CodingSessionSQLiteDatabase]


class CodingSessionsRuntime:
    def __init__(self, *, config, database, persistence, integrations, resources) -> None:
        self._config = config
        self._database = database
        self._persistence = persistence
        self._integrations = integrations
        self._resources = resources
        self._domain = CodingSessionsDomainServices()
        self._closed = False

    @property
    def domain(self) -> CodingSessionsDomainServices:
        self._ensure_open()
        return self._domain

    @property
    def persistence(self) -> CodingSessionsPersistence:
        self._ensure_open()
        return self._persistence

    @property
    def integrations(self) -> CodingSessionsIntegrations:
        self._ensure_open()
        return self._integrations

    def health(self) -> CodingSessionsHealth:
        persistence_available = schema_valid = False
        if not self._closed:
            try:
                self._database.verify()
                persistence_available = schema_valid = True
            except CodingSessionDomainError:
                pass
        return CodingSessionsHealth(
            not self._closed,
            persistence_available,
            schema_valid,
            self._config.schema_version,
            self._config.record_version,
            self._config.migration_checksum,
            _capabilities(self._config, self._integrations, self._closed),
            not self._closed and all(resource.healthy() for resource in self._resources),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if _close_resources(self._resources):
            raise CodingSessionsRuntimeCloseError("coding sessions resource close failed")

    def _ensure_open(self) -> None:
        if self._closed:
            raise CodingSessionsRuntimeClosedError("coding sessions runtime is closed")


class CodingSessionsRuntimeBuilder:
    def __init__(self, database_factory: DatabaseFactory = CodingSessionSQLiteDatabase) -> None:
        self._database_factory = database_factory

    def build(self, config: CodingSessionsRuntimeConfig) -> CodingSessionsRuntime:
        self._validate(config)
        opened: list[CodingSessionsManagedResource] = []
        try:
            for resource in config.managed_resources:
                resource.open()
                opened.append(resource)
            database = self._database_factory(
                CodingSessionSQLiteConfig(str(config.persistence_path.resolve()))
            )
            database.migrate(applied_at=config.migration_applied_at)
            integrations = _integrations(config.enabled_integrations)
            persistence = CodingSessionsPersistence(
                SQLiteCodingSessionContractBindingsStore(database),
                SQLiteCodingSessionLifecycleCoordinationStore(database),
                SQLiteCodingSessionIntentsReceiptsStore(database),
                SQLiteCodingSessionJournalCheckpointsStore(database),
                SQLiteCodingSessionControlCancellationStore(database),
                SQLiteCodingSessionRestartReconciliationStore(database),
                SQLiteCodingSessionRecoveryOutcomeStore(database),
            )
            return CodingSessionsRuntime(
                config=config,
                database=database,
                persistence=persistence,
                integrations=integrations,
                resources=tuple(opened),
            )
        except Exception as exc:
            cleanup_failures = _close_resources(tuple(opened))
            if cleanup_failures:
                raise CodingSessionsRuntimeBuildError("build and cleanup failed") from exc
            if isinstance(exc, CodingSessionsRuntimeBuildError):
                raise
            raise CodingSessionsRuntimeBuildError("coding sessions build failed") from exc

    @staticmethod
    def _validate(config: CodingSessionsRuntimeConfig) -> None:
        if (
            not isinstance(config, CodingSessionsRuntimeConfig)
            or not isinstance(config.persistence_path, Path)
            or not config.persistence_path.is_absolute()
            or not config.persistence_path.parent.is_dir()
            or not _REFERENCE.fullmatch(config.persistence_reference)
            or not config.migration_applied_at
            or config.schema_version != CODING_SESSION_SQLITE_SCHEMA_VERSION
            or config.record_version != CODING_SESSION_RECORD_VERSION
            or config.migration_checksum != CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM
            or tuple(sorted(set(config.policy_versions))) != config.policy_versions
            or config.sandbox_driver_available
            or config.deployment_runtime_available
            or CodingSessionsCapability.SANDBOX_CONCRETE_EXECUTION in config.enabled_integrations
            or CodingSessionsCapability.DEPLOYMENT_RUNTIME in config.enabled_integrations
            or not config.enabled_integrations
            <= {
                CodingSessionsCapability.REPOSITORY_RUNTIME,
                CodingSessionsCapability.GOVERNANCE_APPROVALS,
                CodingSessionsCapability.WORKERS_MISSIONS,
                CodingSessionsCapability.SANDBOX_REFERENCES,
                CodingSessionsCapability.PRIVATE_EVALS,
                CodingSessionsCapability.DEPLOYMENT_REFERENCES,
            }
        ):
            raise CodingSessionsRuntimeBuildError("coding sessions configuration is invalid")


def _integrations(enabled: frozenset[CodingSessionsCapability]) -> CodingSessionsIntegrations:
    return CodingSessionsIntegrations(
        CodingSessionRepositoryCompatibilityAdapter() if CodingSessionsCapability.REPOSITORY_RUNTIME in enabled else None,
        CodingSessionGovernanceCompatibilityAdapter() if CodingSessionsCapability.GOVERNANCE_APPROVALS in enabled else None,
        CodingSessionWorkersMissionsCompatibilityAdapter() if CodingSessionsCapability.WORKERS_MISSIONS in enabled else None,
        CodingSessionSandboxCompatibilityAdapter() if CodingSessionsCapability.SANDBOX_REFERENCES in enabled else None,
        CodingSessionPrivateEvalsCompatibilityAdapter() if CodingSessionsCapability.PRIVATE_EVALS in enabled else None,
        CodingSessionDeploymentReferenceService() if CodingSessionsCapability.DEPLOYMENT_REFERENCES in enabled else None,
    )


def _capabilities(config, integrations, closed):
    versions = {
        CodingSessionsCapability.REPOSITORY_RUNTIME: CODING_SESSION_REPOSITORY_COMPATIBILITY_VERSION,
        CodingSessionsCapability.GOVERNANCE_APPROVALS: CODING_SESSION_GOVERNANCE_COMPATIBILITY_VERSION,
        CodingSessionsCapability.WORKERS_MISSIONS: CODING_SESSION_WORK_COMPATIBILITY_VERSION,
        CodingSessionsCapability.SANDBOX_REFERENCES: CODING_SESSION_SANDBOX_COMPATIBILITY_VERSION,
        CodingSessionsCapability.PRIVATE_EVALS: CODING_SESSION_PRIVATE_EVALS_COMPATIBILITY_VERSION,
        CodingSessionsCapability.DEPLOYMENT_REFERENCES: CODING_SESSION_DEPLOYMENT_REFERENCE_VERSION,
    }
    available = {
        CodingSessionsCapability.REPOSITORY_RUNTIME: integrations.repository,
        CodingSessionsCapability.GOVERNANCE_APPROVALS: integrations.governance,
        CodingSessionsCapability.WORKERS_MISSIONS: integrations.workers_missions,
        CodingSessionsCapability.SANDBOX_REFERENCES: integrations.sandbox,
        CodingSessionsCapability.PRIVATE_EVALS: integrations.private_evals,
        CodingSessionsCapability.DEPLOYMENT_REFERENCES: integrations.deployment,
    }
    facts = [
        CodingSessionsIntegrationCapability(
            CodingSessionsCapability.PERSISTENCE,
            CodingSessionsCapabilityState.UNAVAILABLE if closed else CodingSessionsCapabilityState.SUPPORTED,
            config.record_version,
        )
    ]
    for capability, version in versions.items():
        state = CodingSessionsCapabilityState.SUPPORTED if available[capability] is not None and not closed else CodingSessionsCapabilityState.UNAVAILABLE
        if capability is CodingSessionsCapability.DEPLOYMENT_REFERENCES and state is CodingSessionsCapabilityState.SUPPORTED:
            state = CodingSessionsCapabilityState.DEGRADED
        facts.append(CodingSessionsIntegrationCapability(capability, state, version))
    facts.extend(
        (
            CodingSessionsIntegrationCapability(CodingSessionsCapability.SANDBOX_CONCRETE_EXECUTION, CodingSessionsCapabilityState.UNAVAILABLE, "external"),
            CodingSessionsIntegrationCapability(CodingSessionsCapability.DEPLOYMENT_RUNTIME, CodingSessionsCapabilityState.UNAVAILABLE, "future"),
        )
    )
    return tuple(sorted(facts, key=lambda item: item.capability.value))


def _close_resources(resources):
    failures = []
    for resource in reversed(resources):
        try:
            resource.close()
        except Exception:
            failures.append(resource)
    return tuple(failures)
