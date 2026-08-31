"""Consumer-owned persistence contracts for Coding Sessions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .identities import (
    CodingSessionCheckpointIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionPersistenceRecordIdentity,
)

CODING_SESSION_RECORD_VERSION = "coding-session-record-v1"
CODING_SESSION_PERSISTENCE_COMPATIBILITY_POLICY_VERSION = (
    "coding-session-persistence-compatibility-v1"
)


class CodingSessionPersistenceStream(str, Enum):
    CONTRACT_BINDINGS = "contract-bindings"
    LIFECYCLE_COORDINATION = "lifecycle-coordination"
    INTENTS_RECEIPTS = "intents-receipts"
    JOURNAL_CHECKPOINTS = "journal-checkpoints"
    CONTROL_CANCELLATION = "control-cancellation"
    RESTART_RECONCILIATION = "restart-reconciliation"
    RECOVERY_OUTCOME = "recovery-outcome"


class CodingSessionRecordAppendStatus(str, Enum):
    APPENDED = "appended"
    IDEMPOTENT = "idempotent"
    REJECTED = "rejected"


class CodingSessionPersistenceFailureCode(str, Enum):
    DIVERGENT_DUPLICATE_IDENTITY = "divergent-duplicate-identity"
    IDEMPOTENCY_COLLISION = "idempotency-collision"
    CAUSAL_REVISION_CONFLICT = "causal-revision-conflict"
    LINEAGE_GAP = "lineage-gap"
    MISSING_ARTIFACT = "missing-artifact"
    UNSUPPORTED_RECORD_VERSION = "unsupported-record-version"
    CORRUPTED_FINGERPRINT = "corrupted-fingerprint"
    INCOMPLETE_REPLAY = "incomplete-replay"
    UNAVAILABLE_STORE = "unavailable-store"


class CodingSessionStreamCompleteness(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


class CodingSessionCheckpointPersistenceState(str, Enum):
    NOT_PERSISTED = "not-persisted"
    PERSISTED = "persisted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CodingSessionRecordCompatibilityPolicy:
    supported_record_versions: tuple[str, ...] = (CODING_SESSION_RECORD_VERSION,)
    policy_version: str = CODING_SESSION_PERSISTENCE_COMPATIBILITY_POLICY_VERSION

    def supports(self, record_version: str) -> bool:
        return record_version in self.supported_record_versions


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionPersistenceFailure:
    code: CodingSessionPersistenceFailureCode
    subject: str = "coding-session-record"


@dataclass(frozen=True, slots=True)
class CodingSessionRetentionMetadata:
    policy_version: str
    classification: str
    retain_until: int | None = None


@dataclass(frozen=True, slots=True)
class CodingSessionRecordEnvelope:
    record_identity: CodingSessionPersistenceRecordIdentity
    session_identity: CodingSessionIdentity
    stream: CodingSessionPersistenceStream
    category: str
    semantic_artifact_identity: str
    canonical_payload: str
    canonical_payload_fingerprint: CodingSessionFingerprint
    causal_revision: int
    parent_record_fingerprint: CodingSessionFingerprint | None
    lineage: tuple[CodingSessionFingerprint, ...]
    idempotency_key: CodingSessionFingerprint
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    retention_metadata: CodingSessionRetentionMetadata | None = None
    record_version: str = CODING_SESSION_RECORD_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "lineage",
            tuple(sorted(set(self.lineage), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "occurrence_metadata",
            tuple(sorted(set(self.occurrence_metadata))),
        )

    @property
    def semantic_fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            (
                self.session_identity,
                self.stream,
                self.category,
                self.semantic_artifact_identity,
                self.canonical_payload_fingerprint,
                self.record_version,
                self.causal_revision,
                self.parent_record_fingerprint,
                self.lineage,
            )
        )

    @property
    def record_fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionRecordAppendRequest:
    record: CodingSessionRecordEnvelope
    expected_causal_revision: int
    expected_parent_record_fingerprint: CodingSessionFingerprint | None


@dataclass(frozen=True, slots=True)
class CodingSessionRecordAppendAssessment:
    status: CodingSessionRecordAppendStatus
    records: tuple[CodingSessionRecordEnvelope, ...]
    record: CodingSessionRecordEnvelope | None
    failures: tuple[CodingSessionPersistenceFailure, ...]

    @classmethod
    def assess(
        cls,
        existing_records: tuple[CodingSessionRecordEnvelope, ...],
        request: CodingSessionRecordAppendRequest,
    ) -> CodingSessionRecordAppendAssessment:
        ordered = tuple(sorted(existing_records, key=lambda item: item.causal_revision))
        failures: set[CodingSessionPersistenceFailure] = set()
        record = request.record
        if record.record_version != CODING_SESSION_RECORD_VERSION:
            failures.add(_failure(CodingSessionPersistenceFailureCode.UNSUPPORTED_RECORD_VERSION))
        same_identity = next(
            (item for item in ordered if item.record_identity == record.record_identity), None
        )
        same_key = next(
            (item for item in ordered if item.idempotency_key == record.idempotency_key), None
        )
        if same_identity is not None and same_identity.record_fingerprint != record.record_fingerprint:
            failures.add(_failure(CodingSessionPersistenceFailureCode.DIVERGENT_DUPLICATE_IDENTITY))
        if same_key is not None:
            if same_key.semantic_fingerprint == record.semantic_fingerprint:
                return cls(CodingSessionRecordAppendStatus.IDEMPOTENT, ordered, same_key, ())
            failures.add(_failure(CodingSessionPersistenceFailureCode.IDEMPOTENCY_COLLISION))
        expected_revision = len(ordered) + 1
        previous = ordered[-1].record_fingerprint if ordered else None
        if (
            request.expected_causal_revision != expected_revision
            or record.causal_revision != expected_revision
        ):
            failures.add(_failure(CodingSessionPersistenceFailureCode.CAUSAL_REVISION_CONFLICT))
        if (
            request.expected_parent_record_fingerprint != previous
            or record.parent_record_fingerprint != previous
            or record.lineage != ((previous,) if previous else ())
        ):
            failures.add(_failure(CodingSessionPersistenceFailureCode.LINEAGE_GAP))
        if failures:
            return cls(
                CodingSessionRecordAppendStatus.REJECTED,
                ordered,
                None,
                tuple(sorted(failures)),
            )
        return cls(
            CodingSessionRecordAppendStatus.APPENDED,
            (*ordered, record),
            record,
            (),
        )


@dataclass(frozen=True, slots=True)
class CodingSessionExactRecordReadRequest:
    session_identity: CodingSessionIdentity
    stream: CodingSessionPersistenceStream
    record_identity: CodingSessionPersistenceRecordIdentity
    expected_record_fingerprint: CodingSessionFingerprint


@dataclass(frozen=True, slots=True)
class CodingSessionArtifactExistenceRequest:
    session_identity: CodingSessionIdentity
    stream: CodingSessionPersistenceStream
    semantic_artifact_identity: str
    canonical_payload_fingerprint: CodingSessionFingerprint


@dataclass(frozen=True, slots=True)
class CodingSessionExactRecordReadResult:
    record: CodingSessionRecordEnvelope | None
    failures: tuple[CodingSessionPersistenceFailure, ...]

    @classmethod
    def assess(
        cls,
        records: tuple[CodingSessionRecordEnvelope, ...],
        request: CodingSessionExactRecordReadRequest,
    ) -> CodingSessionExactRecordReadResult:
        record = next(
            (
                item
                for item in records
                if item.session_identity == request.session_identity
                and item.stream is request.stream
                and item.record_identity == request.record_identity
            ),
            None,
        )
        if record is None:
            return cls(None, (_failure(CodingSessionPersistenceFailureCode.MISSING_ARTIFACT),))
        if record.record_fingerprint != request.expected_record_fingerprint:
            return cls(None, (_failure(CodingSessionPersistenceFailureCode.CORRUPTED_FINGERPRINT),))
        if record.record_version != CODING_SESSION_RECORD_VERSION:
            return cls(None, (_failure(CodingSessionPersistenceFailureCode.UNSUPPORTED_RECORD_VERSION),))
        return cls(record, ())


@dataclass(frozen=True, slots=True)
class CodingSessionCausalRangeReadRequest:
    session_identity: CodingSessionIdentity
    stream: CodingSessionPersistenceStream
    from_revision: int
    through_revision: int


@dataclass(frozen=True, slots=True)
class CodingSessionReplayRequest:
    session_identity: CodingSessionIdentity
    ranges: tuple[CodingSessionCausalRangeReadRequest, ...]
    required_streams: frozenset[CodingSessionPersistenceStream]


@dataclass(frozen=True, slots=True)
class CodingSessionStreamCompletenessAssessment:
    session_identity: CodingSessionIdentity
    stream: CodingSessionPersistenceStream
    from_revision: int
    through_revision: int
    state: CodingSessionStreamCompleteness
    missing_revisions: tuple[int, ...]
    failures: tuple[CodingSessionPersistenceFailure, ...]

    @classmethod
    def assess(
        cls,
        request: CodingSessionCausalRangeReadRequest,
        records: tuple[CodingSessionRecordEnvelope, ...],
    ) -> CodingSessionStreamCompletenessAssessment:
        present = {
            item.causal_revision
            for item in records
            if item.session_identity == request.session_identity and item.stream is request.stream
        }
        missing = tuple(
            revision
            for revision in range(request.from_revision, request.through_revision + 1)
            if revision not in present
        )
        revisions = [
            item.causal_revision
            for item in records
            if item.session_identity == request.session_identity and item.stream is request.stream
        ]
        failures: set[CodingSessionPersistenceFailure] = set()
        if missing:
            failures.add(_failure(CodingSessionPersistenceFailureCode.INCOMPLETE_REPLAY))
        if len(revisions) != len(set(revisions)):
            failures.add(_failure(CodingSessionPersistenceFailureCode.CAUSAL_REVISION_CONFLICT))
        return cls(
            request.session_identity,
            request.stream,
            request.from_revision,
            request.through_revision,
            CodingSessionStreamCompleteness.INCOMPLETE
            if failures
            else CodingSessionStreamCompleteness.COMPLETE,
            missing,
            tuple(sorted(failures)),
        )


@dataclass(frozen=True, slots=True)
class CodingSessionReplayResult:
    session_identity: CodingSessionIdentity
    records: tuple[CodingSessionRecordEnvelope, ...]
    stream_assessments: tuple[CodingSessionStreamCompletenessAssessment, ...]
    completeness: CodingSessionStreamCompleteness
    failures: tuple[CodingSessionPersistenceFailure, ...]
    fingerprint: CodingSessionFingerprint

    @classmethod
    def project(
        cls,
        request: CodingSessionReplayRequest,
        records: tuple[CodingSessionRecordEnvelope, ...],
    ) -> CodingSessionReplayResult:
        selected: list[CodingSessionRecordEnvelope] = []
        assessments: list[CodingSessionStreamCompletenessAssessment] = []
        for range_request in sorted(request.ranges, key=lambda item: item.stream.value):
            range_records = tuple(
                item
                for item in records
                if item.session_identity == request.session_identity
                and item.stream is range_request.stream
                and range_request.from_revision
                <= item.causal_revision
                <= range_request.through_revision
            )
            selected.extend(range_records)
            assessments.append(
                CodingSessionStreamCompletenessAssessment.assess(
                    range_request, range_records
                )
            )
        represented = {item.stream for item in assessments}
        missing_streams = request.required_streams - represented
        failures = {
            failure for assessment in assessments for failure in assessment.failures
        }
        if missing_streams:
            failures.add(_failure(CodingSessionPersistenceFailureCode.INCOMPLETE_REPLAY))
        ordered = tuple(
            sorted(selected, key=lambda item: (item.stream.value, item.causal_revision))
        )
        assessment_tuple = tuple(assessments)
        failure_tuple = tuple(sorted(failures))
        completeness = (
            CodingSessionStreamCompleteness.INCOMPLETE
            if failure_tuple
            else CodingSessionStreamCompleteness.COMPLETE
        )
        fingerprint = CodingSessionFingerprint.from_content(
            (
                request.session_identity,
                tuple(item.record_fingerprint for item in ordered),
                assessment_tuple,
                completeness,
                failure_tuple,
            )
        )
        return cls(
            request.session_identity,
            ordered,
            assessment_tuple,
            completeness,
            failure_tuple,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class CodingSessionCheckpointPersistenceEvidence:
    session_identity: CodingSessionIdentity
    checkpoint_identity: CodingSessionCheckpointIdentity
    checkpoint_fingerprint: CodingSessionFingerprint
    record_identity: CodingSessionPersistenceRecordIdentity | None
    record_fingerprint: CodingSessionFingerprint | None
    structural_complete: bool
    durable_ready: bool
    persistence_state: CodingSessionCheckpointPersistenceState
    record_version: str = CODING_SESSION_RECORD_VERSION

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionRestartReplayInput:
    session_identity: CodingSessionIdentity
    replay_fingerprint: CodingSessionFingerprint
    record_fingerprints: tuple[CodingSessionFingerprint, ...]
    completeness: CodingSessionStreamCompleteness
    checkpoint_persistence_evidence: CodingSessionCheckpointPersistenceEvidence | None
    external_reconciliation_required: bool = True

    @classmethod
    def from_replay(
        cls,
        replay: CodingSessionReplayResult,
        checkpoint_persistence_evidence: CodingSessionCheckpointPersistenceEvidence | None,
    ) -> CodingSessionRestartReplayInput:
        return cls(
            replay.session_identity,
            replay.fingerprint,
            tuple(item.record_fingerprint for item in replay.records),
            replay.completeness,
            checkpoint_persistence_evidence,
            True,
        )


class CodingSessionContractBindingsPersistencePort(Protocol):
    def append_contract_record(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment: ...
    def read_contract_record_exact(self, request: CodingSessionExactRecordReadRequest) -> CodingSessionExactRecordReadResult: ...
    def contract_artifact_exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool: ...


class CodingSessionLifecycleCoordinationPersistencePort(Protocol):
    def append_lifecycle_record(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment: ...
    def read_lifecycle_range(self, request: CodingSessionCausalRangeReadRequest) -> tuple[CodingSessionRecordEnvelope, ...]: ...
    def assess_lifecycle_completeness(self, request: CodingSessionCausalRangeReadRequest) -> CodingSessionStreamCompletenessAssessment: ...
    def lifecycle_artifact_exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool: ...


class CodingSessionIntentsReceiptsPersistencePort(Protocol):
    def append_intent_receipt_record(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment: ...
    def read_intent_receipt_range(self, request: CodingSessionCausalRangeReadRequest) -> tuple[CodingSessionRecordEnvelope, ...]: ...
    def read_intent_receipt_exact(self, request: CodingSessionExactRecordReadRequest) -> CodingSessionExactRecordReadResult: ...
    def intent_receipt_artifact_exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool: ...


class CodingSessionJournalCheckpointsPersistencePort(Protocol):
    def append_journal_checkpoint_record(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment: ...
    def read_journal_checkpoint_range(self, request: CodingSessionCausalRangeReadRequest) -> tuple[CodingSessionRecordEnvelope, ...]: ...
    def read_checkpoint_exact(self, request: CodingSessionExactRecordReadRequest) -> CodingSessionExactRecordReadResult: ...
    def checkpoint_artifact_exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool: ...


class CodingSessionControlCancellationPersistencePort(Protocol):
    def append_control_record(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment: ...
    def read_control_range(self, request: CodingSessionCausalRangeReadRequest) -> tuple[CodingSessionRecordEnvelope, ...]: ...
    def control_artifact_exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool: ...


class CodingSessionRestartReconciliationPersistencePort(Protocol):
    def append_restart_record(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment: ...
    def read_restart_range(self, request: CodingSessionCausalRangeReadRequest) -> tuple[CodingSessionRecordEnvelope, ...]: ...
    def replay_session(self, request: CodingSessionReplayRequest) -> CodingSessionReplayResult: ...
    def restart_artifact_exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool: ...


class CodingSessionRecoveryOutcomePersistencePort(Protocol):
    def append_recovery_record(self, request: CodingSessionRecordAppendRequest) -> CodingSessionRecordAppendAssessment: ...
    def read_recovery_range(self, request: CodingSessionCausalRangeReadRequest) -> tuple[CodingSessionRecordEnvelope, ...]: ...
    def read_recovery_record_exact(self, request: CodingSessionExactRecordReadRequest) -> CodingSessionExactRecordReadResult: ...
    def recovery_artifact_exists_exact(self, request: CodingSessionArtifactExistenceRequest) -> bool: ...


def _failure(code: CodingSessionPersistenceFailureCode) -> CodingSessionPersistenceFailure:
    return CodingSessionPersistenceFailure(code)
