"""Consumer-owned persistence ports for exact append-only artifact access."""

from typing import Protocol

from .persistence import (
    RepositoryPersistedRecord,
    RepositoryRecordDraft,
    RepositoryReplay,
    RepositoryRestartState,
    RepositoryWriteResult,
)


class RepositoryArtifactStore(Protocol):
    def append(self, draft: RepositoryRecordDraft) -> RepositoryWriteResult: ...

    def get_exact(self, semantic_identity: str, fingerprint: str) -> RepositoryPersistedRecord: ...

    def replay(self, stream_identity: str) -> RepositoryReplay: ...

    def restart_state(self, stream_identity: str) -> RepositoryRestartState: ...


class RepositoryObservationSnapshotStore(RepositoryArtifactStore, Protocol):
    """Identity, observation, catalog and snapshot records."""


class RepositoryPlanningAuthorizationStore(RepositoryArtifactStore, Protocol):
    """Change, plan, authorization and restore-point records."""


class RepositoryMutationLifecycleStore(RepositoryArtifactStore, Protocol):
    """Immutable mutation attempt, journal and result records."""


class RepositoryRecoveryEvidenceStore(RepositoryArtifactStore, Protocol):
    """Verification, reconciliation and recovery evidence records."""
