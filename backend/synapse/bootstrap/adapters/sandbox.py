"""Deferred global lifecycle binding for the frozen Sandbox composition."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from synapse.bootstrap.adapters.sandbox_policy import (
    build_local_windows_sandbox_admission_policy,
)
from synapse.bootstrap.lifecycle import LifecycleResource
from synapse.health.contributors.sandbox import SandboxHealthContributor, SandboxHealthFacts
from synapse.sandbox_composition import SandboxRuntime, SandboxRuntimeBuilder, SandboxRuntimeConfig


class SandboxSlotState(StrEnum):
    CONSTRUCTED = "constructed"
    STARTED = "started"
    CLOSED = "closed"


class SandboxSlotUnavailable(RuntimeError):
    pass


class DeferredSandboxRuntime:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._runtime: SandboxRuntime | None = None
        self._state = SandboxSlotState.CONSTRUCTED

    @property
    def state(self) -> SandboxSlotState:
        return self._state

    @property
    def runtime(self) -> SandboxRuntime:
        if self._runtime is None or self._state is not SandboxSlotState.STARTED:
            raise SandboxSlotUnavailable("Sandbox runtime is not started")
        return self._runtime

    def start(self) -> None:
        if self._state is SandboxSlotState.STARTED:
            return
        if self._state is SandboxSlotState.CLOSED:
            raise SandboxSlotUnavailable("Sandbox runtime is closed")
        self._runtime = SandboxRuntimeBuilder().build(
            SandboxRuntimeConfig(
                database_path=self._database_path,
                database_reference="persistence:sandbox-runtime",
                migration_applied_at=datetime.now(UTC),
                admission_policy=build_local_windows_sandbox_admission_policy(),
            )
        )
        self._state = SandboxSlotState.STARTED

    def close(self) -> None:
        if self._state is SandboxSlotState.CLOSED:
            return
        if self._runtime is not None:
            self._runtime.close()
        self._state = SandboxSlotState.CLOSED

    def lifecycle_resource(self) -> LifecycleResource:
        return LifecycleResource(
            name="sandbox-runtime",
            feature="sandbox-operational-policy",
            reason="Initialize the fail-closed Sandbox boundary without execution ports.",
            start=self.start,
            close=self.close,
            required=True,
            metadata={
                "failure_behavior": "rollback startup and fail the lifespan",
                "execution_activation": "unavailable",
            },
        )

    def health_contributor(self) -> SandboxHealthContributor:
        def facts() -> SandboxHealthFacts:
            if self._state is not SandboxSlotState.STARTED:
                return SandboxHealthFacts(
                    self._state.value, False, False, "", (), False, False, False, False,
                    False, 0,
                )
            health = self.runtime.health()
            return SandboxHealthFacts(
                self._state.value,
                health.persistence_available,
                health.schema_valid,
                self.runtime.policy.version.value,
                health.configured_adapters,
                health.materialization_ports_available,
                health.supervision_ports_available,
                health.isolation_driver_available,
                health.real_execution_available,
                health.managed_resources_healthy,
                health.recovery_finding_count,
            )

        return SandboxHealthContributor(facts)
