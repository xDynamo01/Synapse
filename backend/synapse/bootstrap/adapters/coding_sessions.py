"""Deferred lifecycle binding for frozen Coding Sessions composition."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from synapse.bootstrap.lifecycle import LifecycleResource
from synapse.coding_sessions_composition import (
    CodingSessionsRuntime,
    CodingSessionsRuntimeBuilder,
    CodingSessionsRuntimeConfig,
)
from synapse.health.contributors.coding_sessions import (
    CodingSessionsHealthContributor,
    CodingSessionsHealthFacts,
)


class CodingSessionsSlotState(StrEnum):
    CONSTRUCTED = "constructed"
    STARTED = "started"
    CLOSED = "closed"


class CodingSessionsSlotUnavailable(RuntimeError):
    pass


class DeferredCodingSessionsRuntime:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._runtime: CodingSessionsRuntime | None = None
        self._state = CodingSessionsSlotState.CONSTRUCTED

    @property
    def state(self) -> CodingSessionsSlotState:
        return self._state

    @property
    def runtime(self) -> CodingSessionsRuntime:
        if self._runtime is None or self._state is not CodingSessionsSlotState.STARTED:
            raise CodingSessionsSlotUnavailable("Coding Sessions runtime is not started")
        return self._runtime

    def start(self) -> None:
        if self._state is CodingSessionsSlotState.STARTED:
            return
        if self._state is CodingSessionsSlotState.CLOSED:
            raise CodingSessionsSlotUnavailable("Coding Sessions runtime is closed")
        config = CodingSessionsRuntimeConfig(
            persistence_path=self._database_path,
            persistence_reference="global-coding-sessions",
            migration_applied_at=datetime.now(UTC).isoformat(),
        )
        self._runtime = CodingSessionsRuntimeBuilder().build(config)
        self._state = CodingSessionsSlotState.STARTED

    def close(self) -> None:
        if self._state is CodingSessionsSlotState.CLOSED:
            return
        if self._runtime is not None:
            self._runtime.close()
        self._state = CodingSessionsSlotState.CLOSED

    def lifecycle_resource(self) -> LifecycleResource:
        return LifecycleResource(
            "coding-sessions-runtime", "global-composition-root",
            "Initialize Coding Sessions persistence without external integrations.",
            self.start, self.close, True,
            metadata={"failure_behavior": "rollback startup and fail the lifespan"},
        )

    def health_contributor(self) -> CodingSessionsHealthContributor:
        def facts() -> CodingSessionsHealthFacts:
            if self._state is not CodingSessionsSlotState.STARTED:
                return CodingSessionsHealthFacts(self._state.value, False, False, False, ())
            health = self.runtime.health()
            return CodingSessionsHealthFacts(
                self._state.value,
                health.persistence_available,
                health.schema_valid,
                health.managed_resources_healthy,
                tuple((item.capability.value, item.state.value) for item in health.integrations),
            )

        return CodingSessionsHealthContributor(facts)
