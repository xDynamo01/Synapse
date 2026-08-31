"""Deferred lifecycle binding for the frozen Skills Phase 2 composition."""

from enum import StrEnum
from pathlib import Path

from synapse.bootstrap.lifecycle import LifecycleResource
from synapse.health.contributors.skills_phase2 import (
    SkillsPhase2HealthContributor,
    SkillsPhase2HealthFacts,
)
from synapse.skills.composition import (
    SkillsCompatibilityMode,
    SkillsIntegrityPolicy,
    SkillsMigrationPolicy,
    SkillsRuntimeComposition,
    SkillsRuntimeConfiguration,
    build_skills_runtime,
)
from synapse.skills.persistence import SkillSQLiteConfig
from synapse.skills.phase3_values import SkillStoreQueryLimit


class SkillsPhase2SlotState(StrEnum):
    CONSTRUCTED = "constructed"
    STARTED = "started"
    CLOSED = "closed"


class SkillsPhase2SlotUnavailable(RuntimeError):
    pass


class DeferredSkillsPhase2Runtime:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._runtime: SkillsRuntimeComposition | None = None
        self._state = SkillsPhase2SlotState.CONSTRUCTED

    @property
    def state(self) -> SkillsPhase2SlotState:
        return self._state

    @property
    def runtime(self) -> SkillsRuntimeComposition:
        if self._runtime is None or self._state is not SkillsPhase2SlotState.STARTED:
            raise SkillsPhase2SlotUnavailable("Skills Phase 2 runtime is not started")
        return self._runtime

    def start(self) -> None:
        if self._state is SkillsPhase2SlotState.STARTED:
            return
        if self._state is SkillsPhase2SlotState.CLOSED:
            raise SkillsPhase2SlotUnavailable("Skills Phase 2 runtime is closed")
        self._runtime = build_skills_runtime(
            SkillsRuntimeConfiguration(
                SkillSQLiteConfig(self._database_path),
                SkillsMigrationPolicy.MIGRATE_IF_NEEDED,
                SkillsIntegrityPolicy.EXPLICIT_ONLY,
                SkillsCompatibilityMode.DISABLED,
                SkillStoreQueryLimit(100),
            )
        )
        self._state = SkillsPhase2SlotState.STARTED

    def close(self) -> None:
        if self._state is SkillsPhase2SlotState.CLOSED:
            return
        if self._runtime is not None:
            self._runtime.close()
        self._state = SkillsPhase2SlotState.CLOSED

    def lifecycle_resource(self) -> LifecycleResource:
        return LifecycleResource(
            "skills-phase2-runtime", "global-composition-root",
            "Initialize frozen Skills Phase 2 persistence with compatibility disabled.",
            self.start, self.close, True,
            metadata={"failure_behavior": "rollback startup and fail the lifespan"},
        )

    def health_contributor(self) -> SkillsPhase2HealthContributor:
        def facts() -> SkillsPhase2HealthFacts:
            if self._state is not SkillsPhase2SlotState.STARTED:
                return SkillsPhase2HealthFacts(
                    self._state.value, "unavailable", False, False,
                    "not_checked", "not_checked", "not_checked", False,
                )
            health = self.runtime.health()
            return SkillsPhase2HealthFacts(
                self._state.value,
                health.status.value,
                health.schema_current,
                health.database_reachable,
                health.migration.value,
                health.integrity.value,
                health.foreign_keys.value,
                health.compatibility_enabled,
            )

        return SkillsPhase2HealthContributor(facts)
