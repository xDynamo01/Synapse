"""Deferred lifecycle binding for the frozen Repository Runtime composition."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from synapse.bootstrap.lifecycle import LifecycleResource
from synapse.health.contributors.repository_runtime import (
    RepositoryRuntimeHealthContributor,
    RepositoryRuntimeHealthFacts,
)
from synapse.repository_runtime import (
    RepositoryAdapterFeature,
    RepositoryCaseSensitivity,
    RepositoryCheckoutIdentity,
    RepositoryIdentity,
    RepositoryPlatformKind,
    RepositoryPlatformProfile,
    RepositoryUnicodeNormalization,
    RepositoryWorktreeIdentity,
)
from synapse.repository_runtime_composition import (
    RepositoryRuntime,
    RepositoryRuntimeBuilder,
    RepositoryRuntimeConfig,
)


class RepositoryRuntimeSlotState(StrEnum):
    CONSTRUCTED = "constructed"
    STARTED = "started"
    CLOSED = "closed"


class RepositoryRuntimeSlotUnavailable(RuntimeError):
    pass


class DeferredRepositoryRuntime:
    def __init__(self, project_root: Path, data_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._data_root = data_root.resolve()
        self._runtime: RepositoryRuntime | None = None
        self._state = RepositoryRuntimeSlotState.CONSTRUCTED

    @property
    def state(self) -> RepositoryRuntimeSlotState:
        return self._state

    @property
    def runtime(self) -> RepositoryRuntime:
        if self._runtime is None or self._state is not RepositoryRuntimeSlotState.STARTED:
            raise RepositoryRuntimeSlotUnavailable("Repository Runtime is not started")
        return self._runtime

    def start(self) -> None:
        if self._state is RepositoryRuntimeSlotState.STARTED:
            return
        if self._state is RepositoryRuntimeSlotState.CLOSED:
            raise RepositoryRuntimeSlotUnavailable("Repository Runtime is closed")
        repository_id = RepositoryIdentity.from_stable_key("synapse-local-repository")
        checkout_id = RepositoryCheckoutIdentity.derive(repository_id, "canonical-checkout")
        worktree_id = RepositoryWorktreeIdentity.derive(checkout_id, "canonical-worktree")
        config = RepositoryRuntimeConfig(
            repository_root=self._project_root,
            repository_reference="repository:synapse-local",
            restore_root=self._data_root / "repository-runtime-restore",
            repository_id=repository_id,
            checkout_id=checkout_id,
            worktree_id=worktree_id,
            platform_profile=RepositoryPlatformProfile(
                RepositoryPlatformKind.WINDOWS,
                RepositoryCaseSensitivity.INSENSITIVE,
                RepositoryUnicodeNormalization.PRESERVE,
            ),
            persistence_path=self._data_root / "repository-runtime.sqlite3",
            persistence_reference="persistence:repository-runtime",
            migration_applied_at=datetime.now(UTC),
        )
        self._runtime = RepositoryRuntimeBuilder().build(config)
        self._state = RepositoryRuntimeSlotState.STARTED

    def close(self) -> None:
        if self._state is RepositoryRuntimeSlotState.CLOSED:
            return
        if self._runtime is not None:
            self._runtime.close()
        self._state = RepositoryRuntimeSlotState.CLOSED

    def lifecycle_resource(self) -> LifecycleResource:
        return LifecycleResource(
            "repository-runtime", "global-composition-root",
            "Initialize local Repository Runtime without mutation artifacts.",
            self.start, self.close, False,
            metadata={"failure_behavior": "report degraded when the project root is not Git"},
        )

    def health_contributor(self) -> RepositoryRuntimeHealthContributor:
        def facts() -> RepositoryRuntimeHealthFacts:
            if self._state is not RepositoryRuntimeSlotState.STARTED:
                return RepositoryRuntimeHealthFacts(
                    self._state.value, False, False, False, False, "windows",
                    (), (), (), (), False, False,
                )
            health = self.runtime.health()
            def values(items: tuple[RepositoryAdapterFeature, ...]) -> tuple[str, ...]:
                return tuple(item.value for item in items)
            return RepositoryRuntimeHealthFacts(
                self._state.value,
                health.persistence_available,
                health.schema_valid,
                health.local_adapter_available,
                health.git_available,
                health.platform_profile.platform.value,
                values(health.supported_features),
                values(health.degraded_features),
                values(health.unsupported_features),
                values(health.unavailable_features),
                health.coding_sessions_configured,
                health.managed_resources_healthy,
            )

        return RepositoryRuntimeHealthContributor(facts)
