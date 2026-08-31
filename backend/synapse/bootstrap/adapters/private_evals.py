"""Deferred global lifecycle binding for the frozen Private Evals composer."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from synapse.bootstrap.lifecycle import LifecycleResource
from synapse.health.contributors.private_evals import (
    PrivateEvalsHealthContributor,
    PrivateEvalsHealthFacts,
)
from synapse.private_evals import (
    ExternalCapabilityName,
    PrivateEvalsExternalBindings,
    PrivateEvalsPersistenceConfig,
    PrivateEvalsRuntimeConfig,
    PrivateEvalsRuntimeHandle,
    UnavailableExternalCapability,
    compose_private_evals,
)
from synapse.private_evals.adapters import ExternalAdapterConfig


class PrivateEvalsSlotState(StrEnum):
    CONSTRUCTED = "constructed"
    STARTED = "started"
    CLOSED = "closed"


class PrivateEvalsSlotUnavailable(RuntimeError):
    """Raised when the runtime handle is requested outside its active lifecycle."""


class DeferredPrivateEvalsRuntime:
    """Hold inert inputs and compose Private Evals only during lifecycle startup."""

    def __init__(
        self,
        config: PrivateEvalsRuntimeConfig,
        bindings: PrivateEvalsExternalBindings,
    ) -> None:
        self._config = config
        self._bindings = bindings
        self._handle: PrivateEvalsRuntimeHandle | None = None
        self._state = PrivateEvalsSlotState.CONSTRUCTED

    @property
    def state(self) -> PrivateEvalsSlotState:
        return self._state

    @property
    def handle(self) -> PrivateEvalsRuntimeHandle:
        if self._handle is None or self._state is not PrivateEvalsSlotState.STARTED:
            raise PrivateEvalsSlotUnavailable("Private Evals runtime is not started")
        return self._handle

    def start(self) -> None:
        if self._state is PrivateEvalsSlotState.STARTED:
            return
        if self._state is PrivateEvalsSlotState.CLOSED:
            raise PrivateEvalsSlotUnavailable("Private Evals runtime is closed")
        self._handle = compose_private_evals(self._config, self._bindings)
        self._state = PrivateEvalsSlotState.STARTED

    def close(self) -> None:
        if self._state is PrivateEvalsSlotState.CLOSED:
            return
        if self._handle is not None:
            self._handle.close()
        self._state = PrivateEvalsSlotState.CLOSED

    def lifecycle_resource(self) -> LifecycleResource:
        return LifecycleResource(
            name="private-evals-runtime",
            feature="global-composition-root",
            reason="Initialize Private Evals persistence with explicit unavailable bindings.",
            start=self.start,
            close=self.close,
            required=True,
            metadata={"failure_behavior": "rollback startup and fail the lifespan"},
        )

    def health_contributor(self) -> PrivateEvalsHealthContributor:
        def facts() -> PrivateEvalsHealthFacts:
            if self._state is not PrivateEvalsSlotState.STARTED:
                return PrivateEvalsHealthFacts(
                    self._state.value, "unavailable", False, False, False,
                    "unavailable", "unavailable", "unavailable", "unavailable",
                    ("runtime:not_started",),
                )
            readiness = self.handle.readiness
            return PrivateEvalsHealthFacts(
                readiness.lifecycle_state.value,
                readiness.persistence_status.value,
                readiness.read_only,
                readiness.commands_available,
                readiness.local_queries_available,
                readiness.intelligence_snapshot.status.value,
                readiness.case_execution.status.value,
                readiness.case_evaluator.status.value,
                readiness.governance_write.status.value,
                readiness.limitations,
            )

        return PrivateEvalsHealthContributor(facts)


def build_deferred_private_evals(database_path: Path) -> DeferredPrivateEvalsRuntime:
    adapter = ExternalAdapterConfig("global-composition-root", "1.0.0", 30.0)
    config = PrivateEvalsRuntimeConfig(
        PrivateEvalsPersistenceConfig(database_path),
        "global-private-evals",
        "1.0.0",
        adapter,
        adapter,
        adapter,
        adapter,
    )

    def unavailable(capability: ExternalCapabilityName) -> UnavailableExternalCapability:
        return UnavailableExternalCapability(
            capability,
            f"{capability.value}-global-binding",
            "1.0.0",
            "not_configured",
        )

    bindings = PrivateEvalsExternalBindings(
        unavailable(ExternalCapabilityName.INTELLIGENCE_SNAPSHOT),
        unavailable(ExternalCapabilityName.CASE_EXECUTION),
        unavailable(ExternalCapabilityName.CASE_EVALUATOR),
        unavailable(ExternalCapabilityName.GOVERNANCE_WRITE),
    )
    return DeferredPrivateEvalsRuntime(config, bindings)
