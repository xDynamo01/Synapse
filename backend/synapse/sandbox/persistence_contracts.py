"""Consumer-owned ports; persistence adapters implement storage only."""

from typing import Protocol

from .persistence_models import (
    SandboxPersistedRecord,
    SandboxRecordDraft,
    SandboxReplay,
    SandboxWriteResult,
)


class SandboxArtifactStore(Protocol):
    def append(self, draft: SandboxRecordDraft) -> SandboxWriteResult: ...

    def get_exact(self, semantic_identity: str, fingerprint: str) -> SandboxPersistedRecord: ...

    def replay(self, stream_identity: str) -> SandboxReplay: ...


class SandboxCatalogStore(SandboxArtifactStore, Protocol):
    """Port for configuration and policy catalog artifacts."""


class SandboxAdmissionPlanningStore(SandboxArtifactStore, Protocol):
    """Port for admission, plan, grant and specification artifacts."""


class SandboxExecutionLifecycleStore(SandboxArtifactStore, Protocol):
    """Port for materialization, attempt, runtime and cancellation facts."""


class SandboxResultEvidenceStore(SandboxArtifactStore, Protocol):
    """Port for immutable results and evidence artifacts."""
