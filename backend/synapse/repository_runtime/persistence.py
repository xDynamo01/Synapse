"""Versioned append-only record contracts for Repository Runtime artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .canonical import CANONICAL_FORMAT, canonical_bytes, content_fingerprint
from .errors import InvalidRepositoryPersistenceModel
from .identities import RepositoryFingerprint

REPOSITORY_RECORD_FORMAT = "repository-record-v1"
REPOSITORY_SCHEMA_VERSION = 1
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,511}$")


class RepositoryStoreResponsibility(StrEnum):
    OBSERVATION_SNAPSHOT = "observation_snapshot"
    PLANNING_AUTHORIZATION = "planning_authorization"
    MUTATION_LIFECYCLE = "mutation_lifecycle"
    RECOVERY_EVIDENCE = "recovery_evidence"


class RepositoryArtifactKind(StrEnum):
    IDENTITY = "identity"
    PLATFORM_PROFILE = "platform_profile"
    OBSERVATION = "observation"
    OBSERVATION_ASSESSMENT = "observation_assessment"
    PATH_CATALOG = "path_catalog"
    SNAPSHOT = "snapshot"
    CHANGE_SET = "change_set"
    MUTATION_PLAN = "mutation_plan"
    AUTHORIZATION_FACT = "authorization_fact"
    AUTHORIZATION_ASSESSMENT = "authorization_assessment"
    RESTORE_POINT_MANIFEST = "restore_point_manifest"
    RESTORE_POINT_VERIFICATION = "restore_point_verification"
    MUTATION_ATTEMPT = "mutation_attempt"
    MUTATION_JOURNAL = "mutation_journal"
    MUTATION_RESULT = "mutation_result"
    REPOSITORY_VERIFICATION = "repository_verification"
    RECONCILIATION = "reconciliation"
    RECOVERY_PLAN = "recovery_plan"
    RECOVERY_ATTEMPT = "recovery_attempt"
    RECOVERY_JOURNAL = "recovery_journal"
    RECOVERY_RESULT = "recovery_result"


class RepositoryRecordCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


class RepositoryPersistedLifecycleState(StrEnum):
    NONE = "none"
    OBSERVATION_PARTIAL = "observation_partial"
    PLAN_AWAITING_AUTHORIZATION = "plan_awaiting_authorization"
    APPLICATION_PARTIAL = "application_partial"
    VERIFICATION_DIVERGENT = "verification_divergent"
    RECOVERY_REQUIRED = "recovery_required"
    RECOVERY_PARTIAL = "recovery_partial"
    ROLLBACK_FAILED = "rollback_failed"
    VERIFICATION_FAILED = "verification_failed"
    MANUAL_INTERVENTION = "manual_intervention"


class RepositoryWriteDisposition(StrEnum):
    APPENDED = "appended"
    REPLAYED = "replayed"


@dataclass(frozen=True, slots=True)
class RepositoryOccurrenceMetadata:
    occurred_at: datetime
    observed_at: datetime
    source_reference: str
    correlation_reference: str | None = None

    def __post_init__(self) -> None:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.occurred_at, self.observed_at)
        ):
            raise InvalidRepositoryPersistenceModel("occurrence timestamps must be timezone-aware")
        if not _IDENTITY.fullmatch(self.source_reference) or (
            self.correlation_reference is not None
            and not _IDENTITY.fullmatch(self.correlation_reference)
        ):
            raise InvalidRepositoryPersistenceModel("occurrence reference is invalid")


@dataclass(frozen=True, slots=True)
class RepositoryRetentionMetadata:
    policy_reference: str
    retain_until: datetime | None = None
    legal_hold: bool = False
    purge_eligible: bool = False

    def __post_init__(self) -> None:
        if not _IDENTITY.fullmatch(self.policy_reference):
            raise InvalidRepositoryPersistenceModel("retention policy reference is invalid")
        if self.retain_until is not None and (
            self.retain_until.tzinfo is None or self.retain_until.utcoffset() is None
        ):
            raise InvalidRepositoryPersistenceModel("retention timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RepositoryRecordDraft:
    responsibility: RepositoryStoreResponsibility
    artifact_kind: RepositoryArtifactKind
    semantic_identity: str
    stream_identity: str
    causal_revision: int
    expected_causal_revision: int
    idempotency_key: str
    payload: object
    lineage_fingerprints: tuple[RepositoryFingerprint, ...]
    occurrence: RepositoryOccurrenceMetadata
    retention: RepositoryRetentionMetadata
    completeness: RepositoryRecordCompleteness = RepositoryRecordCompleteness.COMPLETE
    lifecycle_state: RepositoryPersistedLifecycleState = RepositoryPersistedLifecycleState.NONE
    record_format: str = REPOSITORY_RECORD_FORMAT
    schema_version: int = REPOSITORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if any(
            not _IDENTITY.fullmatch(value)
            for value in (self.semantic_identity, self.stream_identity, self.idempotency_key)
        ):
            raise InvalidRepositoryPersistenceModel("persistence identity is invalid")
        if (
            self.causal_revision < 1
            or self.expected_causal_revision < 0
            or self.causal_revision != self.expected_causal_revision + 1
        ):
            raise InvalidRepositoryPersistenceModel("causal revision is invalid")
        if (
            self.record_format != REPOSITORY_RECORD_FORMAT
            or self.schema_version != REPOSITORY_SCHEMA_VERSION
        ):
            raise InvalidRepositoryPersistenceModel("record format is unsupported")
        if len(set(self.lineage_fingerprints)) != len(self.lineage_fingerprints):
            raise InvalidRepositoryPersistenceModel("lineage fingerprints must be unique")
        canonical_bytes(self.payload)
        object.__setattr__(
            self,
            "lineage_fingerprints",
            tuple(sorted(self.lineage_fingerprints, key=lambda item: item.value)),
        )

    @property
    def payload_fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint(content_fingerprint(self.payload))

    @property
    def semantic_fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (
                self.record_format,
                self.schema_version,
                self.responsibility,
                self.artifact_kind,
                self.semantic_identity,
                self.payload_fingerprint,
                self.lineage_fingerprints,
                self.completeness,
                self.lifecycle_state,
                self.retention,
                CANONICAL_FORMAT,
            )
        )


@dataclass(frozen=True, slots=True)
class RepositoryPersistedRecord:
    responsibility: RepositoryStoreResponsibility
    artifact_kind: RepositoryArtifactKind
    semantic_identity: str
    semantic_fingerprint: RepositoryFingerprint
    stream_identity: str
    causal_revision: int
    idempotency_key: str
    payload_json: str
    payload_fingerprint: RepositoryFingerprint
    payload_checksum: RepositoryFingerprint
    lineage_fingerprints: tuple[RepositoryFingerprint, ...]
    missing_lineage_fingerprints: tuple[RepositoryFingerprint, ...]
    occurrence: RepositoryOccurrenceMetadata
    retention: RepositoryRetentionMetadata
    completeness: RepositoryRecordCompleteness
    lifecycle_state: RepositoryPersistedLifecycleState
    record_format: str
    schema_version: int


@dataclass(frozen=True, slots=True)
class RepositoryWriteResult:
    disposition: RepositoryWriteDisposition
    record: RepositoryPersistedRecord


@dataclass(frozen=True, slots=True)
class RepositoryReplay:
    stream_identity: str
    records: tuple[RepositoryPersistedRecord, ...]
    missing_revisions: tuple[int, ...]
    missing_lineage_fingerprints: tuple[RepositoryFingerprint, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class RepositoryRestartState:
    stream_identity: str
    records: tuple[RepositoryPersistedRecord, ...]
    lifecycle_states: tuple[RepositoryPersistedLifecycleState, ...]
    completeness: RepositoryRecordCompleteness
    replay_complete: bool
