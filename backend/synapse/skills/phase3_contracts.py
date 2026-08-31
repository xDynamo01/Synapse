from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId, SkillSemanticReference
from synapse.skills.phase3_errors import InvalidSkillStoreRecord
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillActivationRecord,
    SkillAssignmentRecord,
    SkillAssignmentTerminationRecord,
    SkillEvaluationBindingRecord,
    SkillGovernanceBindingRecord,
    SkillInstallationRecord,
    SkillInstallationTerminationRecord,
    SkillLeaseRecord,
    SkillLeaseTerminationRecord,
    SkillLifecycleRecord,
    SkillRevocationRecord,
)
from synapse.skills.phase3_values import SkillStoreQueryLimit


class SkillStoreWriteOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"


LifecycleStoredRecord = (
    SkillLifecycleRecord | SkillActivationRecord | SkillRevocationRecord
)


@dataclass(frozen=True)
class SkillLifecycleHistory:
    """Bounded lifecycle history with an explicit completeness assertion."""

    records: tuple[LifecycleStoredRecord, ...]
    complete: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.records, tuple)
            or not all(
                isinstance(
                    record,
                    (
                        SkillLifecycleRecord,
                        SkillActivationRecord,
                        SkillRevocationRecord,
                    ),
                )
                for record in self.records
            )
            or not isinstance(self.complete, bool)
        ):
            raise InvalidSkillStoreRecord()


InstallationStoredRecord = (
    SkillInstallationRecord | SkillInstallationTerminationRecord
)


@dataclass(frozen=True)
class SkillInstallationHistory:
    """Bounded installation history with an explicit completeness assertion."""

    records: tuple[InstallationStoredRecord, ...]
    complete: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.records, tuple)
            or not all(
                isinstance(
                    record,
                    (SkillInstallationRecord, SkillInstallationTerminationRecord),
                )
                for record in self.records
            )
            or not isinstance(self.complete, bool)
        ):
            raise InvalidSkillStoreRecord()


class SkillCatalogStore(Protocol):
    """Create-only catalog with one immutable record per (SkillId, SkillVersion).

    The same exact published identity is an idempotent replay and returns the
    initially stored publication fact. Divergent fingerprints for the same
    structural version are a divergent duplicate. List order is ascending SemVer
    precedence, concrete version text, then exact identity.
    """

    def save_version(
        self, record: PublishedSkillVersionRecord
    ) -> SkillStoreWriteOutcome: ...
    def get_version(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord: ...
    def list_versions(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> tuple[PublishedSkillVersionRecord, ...]: ...


class SkillLifecycleStore(Protocol):
    """Append-only facts ordered by time; external parent existence is a service concern."""

    def append_lifecycle(self, record: SkillLifecycleRecord) -> SkillStoreWriteOutcome: ...
    def append_activation(self, record: SkillActivationRecord) -> SkillStoreWriteOutcome: ...
    def append_revocation(self, record: SkillRevocationRecord) -> SkillStoreWriteOutcome: ...
    def history(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillLifecycleHistory: ...


class SkillInstallationStore(Protocol):
    """Append-only facts; termination requires a parent owned by this same store."""

    def append_installation(
        self, record: SkillInstallationRecord
    ) -> SkillStoreWriteOutcome: ...
    def append_termination(
        self, record: SkillInstallationTerminationRecord
    ) -> SkillStoreWriteOutcome: ...
    def history(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillInstallationHistory: ...


class SkillAssignmentStore(Protocol):
    """Subject history by time; termination requires a locally owned assignment."""

    def append_assignment(
        self, record: SkillAssignmentRecord
    ) -> SkillStoreWriteOutcome: ...
    def append_termination(
        self, record: SkillAssignmentTerminationRecord
    ) -> SkillStoreWriteOutcome: ...
    def history_for_subject(
        self, subject_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillAssignmentRecord | SkillAssignmentTerminationRecord, ...]: ...


class SkillLeaseStore(Protocol):
    """Histories by time; termination requires a locally owned lease."""

    def append_lease(self, record: SkillLeaseRecord) -> SkillStoreWriteOutcome: ...
    def append_termination(
        self, record: SkillLeaseTerminationRecord
    ) -> SkillStoreWriteOutcome: ...
    def history_for_agent(
        self, agent_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]: ...
    def history_for_task(
        self, task_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]: ...
    def history_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]: ...


class SkillBindingStore(Protocol):
    """Typed refs by bound time; external decision/version existence is not validated."""

    def append_governance(
        self, record: SkillGovernanceBindingRecord
    ) -> SkillStoreWriteOutcome: ...
    def append_evaluation(
        self, record: SkillEvaluationBindingRecord
    ) -> SkillStoreWriteOutcome: ...
    def list_governance_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillGovernanceBindingRecord, ...]: ...
    def list_evaluations_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillEvaluationBindingRecord, ...]: ...
