"""Explicit local Deployment wiring without global bootstrap activation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

from synapse.deployment import (
    DeploymentFencingAuthority,
    LocalActiveStatePort,
    LocalRollbackPreparationPort,
    LocalRollbackStatePort,
)
from synapse.deployment_adapters import (
    DeploymentSQLiteConfig,
    SQLiteDeploymentAuthorityStore,
    SQLiteDeploymentJournalStore,
)
from synapse.deployment_integrations import (
    CurrentDeploymentApplyAuthorizationPort,
    CurrentRollbackAuthorizationPort,
    LocalApplyOrchestrator,
    LocalIndependentVerificationFlow,
    LocalRollbackOrchestrator,
    SandboxLocalApplyPort,
    SandboxRollbackStartPort,
)
from synapse.deployment_integrations.local_verification import (
    LocalObservationPort,
    LocalVerifierPort,
)


class DeploymentRuntimeBuildError(RuntimeError):
    pass


class DeploymentRuntimeStartupError(RuntimeError):
    pass


class DeploymentRuntimeClosedError(RuntimeError):
    pass


class DeploymentRuntimeCloseError(RuntimeError):
    pass


class DeploymentRuntimeManagedResource(Protocol):
    def open(self) -> None: ...

    def close(self) -> None: ...

    def healthy(self) -> bool: ...


class DeploymentCompositionLifecycleState(StrEnum):
    CONSTRUCTED = "constructed"
    STARTED = "started"
    DEGRADED = "degraded"
    CLOSED = "closed"


class DeploymentCompositionCapabilityState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_EVALUATED = "not-evaluated"


class DeploymentCompositionReconciliationState(StrEnum):
    NOT_REQUIRED = "not-required"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class DeploymentRuntimeConfig:
    database_path: Path
    busy_timeout_ms: int = 5_000
    reconciliation_required: bool = False
    managed_resources: tuple[DeploymentRuntimeManagedResource, ...] = ()

    def __post_init__(self) -> None:
        try:
            DeploymentSQLiteConfig(self.database_path, self.busy_timeout_ms)
        except ValueError as exc:
            raise DeploymentRuntimeBuildError("deployment configuration is invalid") from exc
        if not isinstance(self.reconciliation_required, bool):
            raise DeploymentRuntimeBuildError("deployment reconciliation fact is invalid")


@dataclass(frozen=True, slots=True)
class DeploymentRuntimeDependencies:
    apply_authorization: CurrentDeploymentApplyAuthorizationPort | None = None
    sandbox_apply: SandboxLocalApplyPort | None = None
    active_state: LocalActiveStatePort | None = None
    observer: LocalObservationPort | None = None
    verifier: LocalVerifierPort | None = None
    rollback_authorization: CurrentRollbackAuthorizationPort | None = None
    rollback_preparation: LocalRollbackPreparationPort | None = None
    sandbox_rollback: SandboxRollbackStartPort | None = None
    rollback_state: LocalRollbackStatePort | None = None


@dataclass(frozen=True, slots=True)
class DeploymentRuntimeComponents:
    journal: SQLiteDeploymentJournalStore
    authority_store: SQLiteDeploymentAuthorityStore
    fencing: DeploymentFencingAuthority
    apply: LocalApplyOrchestrator | None
    verification: LocalIndependentVerificationFlow | None
    rollback: LocalRollbackOrchestrator | None


@dataclass(frozen=True, slots=True)
class DeploymentCompositionHealth:
    lifecycle: DeploymentCompositionLifecycleState
    persistence: DeploymentCompositionCapabilityState
    fencing: DeploymentCompositionCapabilityState
    apply: DeploymentCompositionCapabilityState
    verification: DeploymentCompositionCapabilityState
    rollback: DeploymentCompositionCapabilityState
    managed_resources: DeploymentCompositionCapabilityState
    reconciliation: DeploymentCompositionReconciliationState


class DeploymentRuntime:
    def __init__(
        self,
        config: DeploymentRuntimeConfig,
        components: DeploymentRuntimeComponents,
    ) -> None:
        self._config = config
        self._components = components
        self._state = DeploymentCompositionLifecycleState.CONSTRUCTED
        self._opened_resources: tuple[DeploymentRuntimeManagedResource, ...] = ()

    @property
    def components(self) -> DeploymentRuntimeComponents:
        self._ensure_open()
        return self._components

    def start(self) -> DeploymentCompositionHealth:
        self._ensure_open()
        if self._state is DeploymentCompositionLifecycleState.STARTED:
            return self.health()
        opened: list[DeploymentRuntimeManagedResource] = []
        try:
            for resource in self._config.managed_resources:
                resource.open()
                opened.append(resource)
            self._components.journal.initialize()
            self._components.authority_store.initialize()
        except Exception as exc:
            self._close_resources(tuple(opened))
            self._state = DeploymentCompositionLifecycleState.DEGRADED
            raise DeploymentRuntimeStartupError("deployment runtime startup failed") from exc
        self._opened_resources = tuple(opened)
        self._state = DeploymentCompositionLifecycleState.STARTED
        return self.health()

    def health(self) -> DeploymentCompositionHealth:
        self._ensure_open()
        persistence = DeploymentCompositionCapabilityState.NOT_EVALUATED
        fencing = DeploymentCompositionCapabilityState.NOT_EVALUATED
        if self._state in {
            DeploymentCompositionLifecycleState.STARTED,
            DeploymentCompositionLifecycleState.DEGRADED,
        }:
            persistence_health = self._components.journal.health()
            fencing_health = self._components.authority_store.health()
            persistence = (
                DeploymentCompositionCapabilityState.AVAILABLE
                if persistence_health.store_available
                and persistence_health.schema_compatible
                and persistence_health.append_integrity
                and persistence_health.replay_available
                and not persistence_health.corruption_detected
                else DeploymentCompositionCapabilityState.UNAVAILABLE
            )
            fencing = (
                DeploymentCompositionCapabilityState.AVAILABLE
                if fencing_health.store_available
                and fencing_health.schema_compatible
                and fencing_health.latest_generation_readable
                and fencing_health.monotonicity_integrity
                and fencing_health.token_validation_available
                and fencing_health.idempotency_store_available
                and fencing_health.contradiction_detection_available
                and not fencing_health.corruption_detected
                else DeploymentCompositionCapabilityState.UNAVAILABLE
            )
        resources = (
            DeploymentCompositionCapabilityState.AVAILABLE
            if self._state is DeploymentCompositionLifecycleState.STARTED
            and all(resource.healthy() for resource in self._opened_resources)
            else DeploymentCompositionCapabilityState.NOT_EVALUATED
            if self._state is DeploymentCompositionLifecycleState.CONSTRUCTED
            else DeploymentCompositionCapabilityState.UNAVAILABLE
        )
        return DeploymentCompositionHealth(
            self._state,
            persistence,
            fencing,
            self._configured(self._components.apply),
            self._configured(self._components.verification),
            self._configured(self._components.rollback),
            resources,
            DeploymentCompositionReconciliationState.REQUIRED
            if self._config.reconciliation_required
            else DeploymentCompositionReconciliationState.NOT_REQUIRED,
        )

    def close(self) -> None:
        if self._state is DeploymentCompositionLifecycleState.CLOSED:
            return
        failures = self._close_resources(self._opened_resources)
        self._opened_resources = ()
        self._state = DeploymentCompositionLifecycleState.CLOSED
        if failures:
            raise DeploymentRuntimeCloseError("deployment runtime close failed")

    @staticmethod
    def _configured(component: object | None) -> DeploymentCompositionCapabilityState:
        return (
            DeploymentCompositionCapabilityState.AVAILABLE
            if component is not None
            else DeploymentCompositionCapabilityState.UNAVAILABLE
        )

    @staticmethod
    def _close_resources(
        resources: tuple[DeploymentRuntimeManagedResource, ...],
    ) -> tuple[DeploymentRuntimeManagedResource, ...]:
        failures: list[DeploymentRuntimeManagedResource] = []
        for resource in reversed(resources):
            try:
                resource.close()
            except Exception:
                failures.append(resource)
        return tuple(failures)

    def _ensure_open(self) -> None:
        if self._state is DeploymentCompositionLifecycleState.CLOSED:
            raise DeploymentRuntimeClosedError("deployment runtime is closed")


def build_deployment_runtime(
    config: DeploymentRuntimeConfig,
    dependencies: DeploymentRuntimeDependencies = DeploymentRuntimeDependencies(),
) -> DeploymentRuntime:
    """Construct configured components without persistence I/O or activation."""

    sqlite_config = DeploymentSQLiteConfig(config.database_path, config.busy_timeout_ms)
    journal = SQLiteDeploymentJournalStore(sqlite_config)
    authority_store = SQLiteDeploymentAuthorityStore(sqlite_config)
    fencing = DeploymentFencingAuthority(authority_store)
    apply_group = (
        dependencies.apply_authorization,
        dependencies.sandbox_apply,
        dependencies.active_state,
    )
    verification_group = (dependencies.observer, dependencies.verifier)
    rollback_group = (
        dependencies.rollback_authorization,
        dependencies.rollback_preparation,
        dependencies.sandbox_rollback,
        dependencies.rollback_state,
    )
    _require_complete("apply", apply_group)
    _require_complete("verification", verification_group)
    _require_complete("rollback", rollback_group)
    apply = (
        LocalApplyOrchestrator(
            fencing,
            cast(CurrentDeploymentApplyAuthorizationPort, dependencies.apply_authorization),
            cast(SandboxLocalApplyPort, dependencies.sandbox_apply),
            cast(LocalActiveStatePort, dependencies.active_state),
            journal,
        )
        if all(item is not None for item in apply_group)
        else None
    )
    verification = (
        LocalIndependentVerificationFlow(
            cast(LocalObservationPort, dependencies.observer),
            cast(LocalVerifierPort, dependencies.verifier),
            journal,
        )
        if all(item is not None for item in verification_group)
        else None
    )
    rollback = (
        LocalRollbackOrchestrator(
            fencing,
            cast(CurrentRollbackAuthorizationPort, dependencies.rollback_authorization),
            cast(LocalRollbackPreparationPort, dependencies.rollback_preparation),
            cast(SandboxRollbackStartPort, dependencies.sandbox_rollback),
            cast(LocalRollbackStatePort, dependencies.rollback_state),
            journal,
        )
        if all(item is not None for item in rollback_group)
        else None
    )
    return DeploymentRuntime(
        config,
        DeploymentRuntimeComponents(
            journal,
            authority_store,
            fencing,
            apply,
            verification,
            rollback,
        ),
    )


def _require_complete(name: str, values: tuple[object | None, ...]) -> None:
    if any(item is not None for item in values) and not all(item is not None for item in values):
        raise DeploymentRuntimeBuildError(f"deployment {name} dependencies are incomplete")
