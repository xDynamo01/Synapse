"""Consumer-owned durable record contracts for Sandbox Slice 16."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .canonical import CANONICAL_FORMAT, canonical_bytes, content_fingerprint
from .errors import InvalidSandboxModel

SANDBOX_RECORD_FORMAT = "sandbox-record-v1"
SANDBOX_SCHEMA_VERSION = 1


class SandboxStoreResponsibility(StrEnum):
    CATALOG = "catalog_configuration"
    ADMISSION = "admission_planning"
    LIFECYCLE = "execution_lifecycle"
    RESULT = "result_evidence"


class SandboxArtifactKind(StrEnum):
    ADMISSION_REQUEST = "admission_request"
    ADMISSION_SNAPSHOT = "admission_snapshot"
    ADMISSION_ASSESSMENT = "admission_assessment"
    ADMISSION_POLICY = "admission_policy"
    ADMISSION_DECISION = "admission_decision"
    EXECUTION_PLAN = "execution_plan"
    CAPABILITY_GRANT_SET = "capability_grant_set"
    FILESYSTEM_GRANT_SET = "filesystem_grant_set"
    FILESYSTEM_SPECIFICATION = "filesystem_specification"
    NETWORK_GRANT_SET = "network_grant_set"
    NETWORK_SPECIFICATION = "network_specification"
    PROCESS_GRANT_SET = "process_grant_set"
    PROCESS_SPECIFICATION = "process_specification"
    RESOURCE_GRANT_SET = "resource_grant_set"
    RESOURCE_SPECIFICATION = "resource_specification"
    SECRET_GRANT_SET = "secret_grant_set"
    SECRET_SPECIFICATION = "secret_specification"
    MATERIALIZATION_PLAN = "materialization_plan"
    MATERIALIZATION_RECORD = "materialization_record"
    MATERIALIZATION_VERIFICATION = "materialization_verification"
    MATERIALIZATION_OUTCOME = "materialization_outcome"
    EXECUTION_ATTEMPT = "execution_attempt"
    RUNTIME_EVENT = "runtime_event"
    RUNTIME_OBSERVATION = "runtime_observation"
    TERMINATION_PROOF = "termination_proof"
    CANCELLATION_REQUEST = "cancellation_request"
    DEADLINE_SET = "deadline_set"
    DEADLINE_EVALUATION = "deadline_evaluation"
    CANCELLATION_DECISION = "cancellation_decision"
    CANCELLATION_EVENT = "cancellation_event"
    CANCELLATION_RESULT = "cancellation_result"
    EXECUTION_RESULT = "execution_result"
    EVIDENCE_POLICY = "evidence_policy"
    EVIDENCE_ITEM = "evidence_item"
    EVIDENCE_BUNDLE = "evidence_bundle"


class SandboxCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INVALID = "invalid"


class SandboxRecoveryState(StrEnum):
    NONE = "none"
    ATTEMPT_INCOMPLETE = "attempt_incomplete"
    MATERIALIZATION_PARTIAL = "materialization_partial"
    CANCELLATION_IN_PROGRESS = "cancellation_in_progress"
    TERMINATION_UNVERIFIED = "termination_unverified"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    CLEANUP_REQUIRED = "cleanup_required"
    MANUAL_INTERVENTION = "manual_intervention"


class SandboxWriteDisposition(StrEnum):
    APPENDED = "appended"
    REPLAYED = "replayed"


@dataclass(frozen=True, slots=True)
class SandboxOccurrenceMetadata:
    occurred_at: datetime
    observed_at: datetime
    source_ref: str
    correlation_ref: str | None = None

    def __post_init__(self) -> None:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.occurred_at, self.observed_at)
        ):
            raise InvalidSandboxModel("occurrence timestamps must be timezone-aware")
        if not self.source_ref or len(self.source_ref) > 255:
            raise InvalidSandboxModel("occurrence source is invalid")


@dataclass(frozen=True, slots=True)
class SandboxRetentionMetadata:
    policy_ref: str
    retain_until: datetime | None = None
    legal_hold: bool = False
    purge_eligible: bool = False

    def __post_init__(self) -> None:
        if not self.policy_ref or len(self.policy_ref) > 255:
            raise InvalidSandboxModel("retention policy reference is invalid")
        if self.retain_until is not None and (
            self.retain_until.tzinfo is None or self.retain_until.utcoffset() is None
        ):
            raise InvalidSandboxModel("retention timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SandboxRecordDraft:
    responsibility: SandboxStoreResponsibility
    artifact_kind: SandboxArtifactKind
    semantic_identity: str
    stream_identity: str
    sequence: int
    idempotency_key: str
    payload: object
    lineage_fingerprints: tuple[str, ...]
    occurrence: SandboxOccurrenceMetadata
    retention: SandboxRetentionMetadata
    completeness: SandboxCompleteness = SandboxCompleteness.COMPLETE
    recovery_state: SandboxRecoveryState = SandboxRecoveryState.NONE
    expected_stream_version: int = 0
    record_format: str = SANDBOX_RECORD_FORMAT
    schema_version: int = SANDBOX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        tokens = (self.semantic_identity, self.stream_identity, self.idempotency_key)
        if any(not value or len(value) > 512 for value in tokens):
            raise InvalidSandboxModel("persistence identity is invalid")
        if self.sequence < 1 or self.expected_stream_version < 0:
            raise InvalidSandboxModel("persistence sequence is invalid")
        if (
            self.record_format != SANDBOX_RECORD_FORMAT
            or self.schema_version != SANDBOX_SCHEMA_VERSION
        ):
            raise InvalidSandboxModel("unsupported persistence record format")
        if len(set(self.lineage_fingerprints)) != len(self.lineage_fingerprints):
            raise InvalidSandboxModel("duplicate lineage fingerprint")
        canonical_bytes(self.payload)

    @property
    def payload_fingerprint(self) -> str:
        return content_fingerprint(self.payload)

    @property
    def semantic_fingerprint(self) -> str:
        return content_fingerprint(
            (
                self.record_format,
                self.schema_version,
                self.responsibility,
                self.artifact_kind,
                self.semantic_identity,
                self.payload_fingerprint,
                self.lineage_fingerprints,
                self.completeness,
                self.recovery_state,
                self.retention,
                CANONICAL_FORMAT,
            )
        )


@dataclass(frozen=True, slots=True)
class SandboxPersistedRecord:
    responsibility: SandboxStoreResponsibility
    artifact_kind: SandboxArtifactKind
    semantic_identity: str
    semantic_fingerprint: str
    stream_identity: str
    sequence: int
    payload_json: str
    payload_fingerprint: str
    lineage_fingerprints: tuple[str, ...]
    missing_lineage_fingerprints: tuple[str, ...]
    occurrence: SandboxOccurrenceMetadata
    retention: SandboxRetentionMetadata
    completeness: SandboxCompleteness
    recovery_state: SandboxRecoveryState
    record_format: str
    schema_version: int


@dataclass(frozen=True, slots=True)
class SandboxWriteResult:
    disposition: SandboxWriteDisposition
    record: SandboxPersistedRecord


@dataclass(frozen=True, slots=True)
class SandboxReplay:
    stream_identity: str
    records: tuple[SandboxPersistedRecord, ...]
    missing_sequences: tuple[int, ...]
    missing_lineage_fingerprints: tuple[str, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class SandboxRecoveryFinding:
    stream_identity: str
    semantic_identity: str
    state: SandboxRecoveryState
    completeness: SandboxCompleteness
    fact_fingerprint: str
