from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .canonical import content_checksum, fingerprint
from .run_finalization_errors import (
    FinalizationReproducibilityMismatch,
    TerminalFailureMismatch,
)
from .run_scoring import ExpectedResultSlot, ScoringResultReference, scoring_result_set_fingerprint
from .states import RunStatus
from .values import (
    ContentChecksum,
    EvalRunFinalizationId,
    EvalRunId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    UtcTimestamp,
)

_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{0,255}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


def safe_finalization_reference(value: str) -> bool:
    return bool(
        isinstance(value, str)
        and _SAFE_REFERENCE.fullmatch(value)
        and not _SENSITIVE.search(value)
        and "/" not in value
        and "\\" not in value
        and "://" not in value
    )


def finalization_slot_key(slot: ExpectedResultSlot) -> tuple[str, str, int]:
    return slot.case_reference.case_id.value, slot.case_reference.version.value, slot.repetition


class RunFinalizationPath(StrEnum):
    SCORABLE = "scorable"
    TERMINALLY_UNSCORABLE = "terminally_unscorable"


class RunFinalizationReadinessStatus(StrEnum):
    READY_SCORABLE = "ready_scorable"
    READY_TERMINALLY_UNSCORABLE = "ready_terminally_unscorable"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class TerminalFailureStage(StrEnum):
    EXECUTION = "execution"
    EVALUATION = "evaluation"


class TerminalFailureStatus(StrEnum):
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    TIMED_OUT = "timed_out"
    POLICY_DENIED = "policy_denied"
    CANCELLED = "cancelled"
    INVALID = "invalid"


class RetryTerminalityKind(StrEnum):
    RETRY_EXHAUSTED = "retry_exhausted"
    NON_RETRYABLE = "non_retryable"


class RunFinalizationReasonCode(StrEnum):
    SCORING_COMPLETED = "scoring_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_TIMED_OUT = "execution_timed_out"
    EVALUATION_FAILED = "evaluation_failed"
    EVALUATION_TIMED_OUT = "evaluation_timed_out"
    POLICY_DENIED = "policy_denied"
    CANCELLED = "cancelled"
    INVALID = "invalid"


class RunFinalizationDisposition(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    POLICY_DENIED = "policy_denied"
    CANCELLED = "cancelled"
    INVALID = "invalid"


class RunFinalizationCoverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NONE = "none"


class RunTerminalCause(StrEnum):
    EXECUTION_FAILURE = "execution_failure"
    EVALUATION_FAILURE = "evaluation_failure"
    POLICY_DENIAL = "policy_denial"
    CANCELLATION = "cancellation"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True)
class RetryTerminalityProof:
    """Immutable conclusion under one frozen retry-policy identity."""

    kind: RetryTerminalityKind
    evaluated_status: TerminalFailureStatus
    policy_reference: str
    policy_fingerprint: Fingerprint
    maximum_attempts: int
    final_attempt: int
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, RetryTerminalityKind)
            or not isinstance(self.evaluated_status, TerminalFailureStatus)
            or not safe_finalization_reference(self.policy_reference)
            or not isinstance(self.policy_fingerprint, Fingerprint)
            or isinstance(self.maximum_attempts, bool)
            or not isinstance(self.maximum_attempts, int)
            or self.maximum_attempts < 1
            or isinstance(self.final_attempt, bool)
            or not isinstance(self.final_attempt, int)
            or not 1 <= self.final_attempt <= self.maximum_attempts
            or (
                self.kind is RetryTerminalityKind.RETRY_EXHAUSTED
                and self.final_attempt != self.maximum_attempts
            )
        ):
            raise TerminalFailureMismatch()
        expected = retry_terminality_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise TerminalFailureMismatch()


def retry_terminality_fingerprint(proof: RetryTerminalityProof) -> Fingerprint:
    return fingerprint(
        {
            "kind": proof.kind,
            "evaluated_status": proof.evaluated_status,
            "policy_reference": proof.policy_reference,
            "policy_fingerprint": proof.policy_fingerprint,
            "maximum_attempts": proof.maximum_attempts,
            "final_attempt": proof.final_attempt,
        }
    )


@dataclass(frozen=True)
class TerminalFailureProjection:
    run_id: EvalRunId
    slot: ExpectedResultSlot
    stage: TerminalFailureStage
    status: TerminalFailureStatus
    final_attempt_reference: Fingerprint
    source_record_checksum: ContentChecksum
    retry_terminality: RetryTerminalityProof
    reason_code: RunFinalizationReasonCode
    provenance_reference: str | None = None
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        typed = (
            (self.run_id, EvalRunId),
            (self.slot, ExpectedResultSlot),
            (self.stage, TerminalFailureStage),
            (self.status, TerminalFailureStatus),
            (self.final_attempt_reference, Fingerprint),
            (self.source_record_checksum, ContentChecksum),
            (self.retry_terminality, RetryTerminalityProof),
            (self.reason_code, RunFinalizationReasonCode),
        )
        non_retryable = {
            TerminalFailureStatus.POLICY_DENIED,
            TerminalFailureStatus.CANCELLED,
            TerminalFailureStatus.INVALID,
        }
        if (
            any(not isinstance(value, expected) for value, expected in typed)
            or (
                self.provenance_reference is not None
                and not safe_finalization_reference(self.provenance_reference)
            )
            or self.retry_terminality.evaluated_status is not self.status
            or (
                self.status in non_retryable
                and self.retry_terminality.kind is not RetryTerminalityKind.NON_RETRYABLE
            )
            or not _reason_matches_failure(self)
        ):
            raise TerminalFailureMismatch()
        expected = terminal_failure_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise TerminalFailureMismatch()

    def __repr__(self) -> str:
        return (
            "TerminalFailureProjection("
            f"slot={self.slot!r}, stage={self.stage!r}, status={self.status!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def _reason_matches_failure(item: TerminalFailureProjection) -> bool:
    if item.status is TerminalFailureStatus.POLICY_DENIED:
        return item.reason_code is RunFinalizationReasonCode.POLICY_DENIED
    if item.status is TerminalFailureStatus.CANCELLED:
        return item.reason_code is RunFinalizationReasonCode.CANCELLED
    if item.status is TerminalFailureStatus.INVALID:
        return item.reason_code is RunFinalizationReasonCode.INVALID
    expected = {
        (TerminalFailureStage.EXECUTION, TerminalFailureStatus.INFRASTRUCTURE_FAILED):
            RunFinalizationReasonCode.EXECUTION_FAILED,
        (TerminalFailureStage.EXECUTION, TerminalFailureStatus.TIMED_OUT):
            RunFinalizationReasonCode.EXECUTION_TIMED_OUT,
        (TerminalFailureStage.EVALUATION, TerminalFailureStatus.INFRASTRUCTURE_FAILED):
            RunFinalizationReasonCode.EVALUATION_FAILED,
        (TerminalFailureStage.EVALUATION, TerminalFailureStatus.TIMED_OUT):
            RunFinalizationReasonCode.EVALUATION_TIMED_OUT,
    }
    return expected.get((item.stage, item.status)) is item.reason_code


def terminal_failure_fingerprint(item: TerminalFailureProjection) -> Fingerprint:
    return fingerprint(
        {
            "run_id": item.run_id,
            "slot": item.slot,
            "stage": item.stage,
            "status": item.status,
            "final_attempt_reference": item.final_attempt_reference,
            "source_record_checksum": item.source_record_checksum,
            "retry_terminality": item.retry_terminality,
            "reason_code": item.reason_code,
            "provenance_reference": item.provenance_reference,
        }
    )


@dataclass(frozen=True)
class EvalRunFinalizationRecord:
    finalization_id: EvalRunFinalizationId
    run_id: EvalRunId
    manifest_fingerprint: Fingerprint
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    path: RunFinalizationPath
    scoring_decision_reference: Fingerprint | None
    result_set_fingerprint: Fingerprint
    partial_result_references: tuple[ScoringResultReference, ...]
    expected_matrix_fingerprint: Fingerprint
    expected_result_count: int
    accepted_result_count: int
    terminal_failures: tuple[TerminalFailureProjection, ...]
    terminal_failure_set_fingerprint: Fingerprint | None
    security_snapshot_reference: str
    security_snapshot_fingerprint: Fingerprint
    reproducibility_fingerprint: Fingerprint
    disposition: RunFinalizationDisposition
    coverage: RunFinalizationCoverage
    terminal_causes: tuple[RunTerminalCause, ...]
    lifecycle_status: RunStatus
    reason_codes: tuple[RunFinalizationReasonCode, ...]
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    fingerprint: Fingerprint | None = None
    checksum: ContentChecksum | None = None

    def __post_init__(self) -> None:
        ordered_results = tuple(
            sorted(
                self.partial_result_references,
                key=lambda item: finalization_slot_key(
                    ExpectedResultSlot(item.case_reference, item.repetition)
                ),
            )
        )
        ordered_failures = tuple(
            sorted(self.terminal_failures, key=lambda item: finalization_slot_key(item.slot))
        )
        expected_failure_set = (
            fingerprint(tuple(item.fingerprint for item in self.terminal_failures))
            if self.terminal_failures
            else None
        )
        expected_coverage = (
            RunFinalizationCoverage.COMPLETE
            if self.accepted_result_count == self.expected_result_count
            else RunFinalizationCoverage.PARTIAL
            if self.accepted_result_count
            else RunFinalizationCoverage.NONE
        )
        scorable_valid = (
            self.scoring_decision_reference is not None
            and not self.partial_result_references
            and not self.terminal_failures
            and self.terminal_failure_set_fingerprint is None
            and self.accepted_result_count == self.expected_result_count
            and self.disposition is RunFinalizationDisposition.COMPLETED
            and not self.terminal_causes
            and self.lifecycle_status is RunStatus.COMPLETED
        )
        terminal_valid = (
            self.scoring_decision_reference is None
            and bool(self.terminal_failures)
            and self.terminal_failure_set_fingerprint == expected_failure_set
            and self.accepted_result_count < self.expected_result_count
            and bool(self.terminal_causes)
        )
        if (
            not isinstance(self.finalization_id, EvalRunFinalizationId)
            or not isinstance(self.run_id, EvalRunId)
            or not isinstance(self.manifest_fingerprint, Fingerprint)
            or not isinstance(self.suite_id, EvalSuiteId)
            or not isinstance(self.suite_version, EvalVersion)
            or not isinstance(self.path, RunFinalizationPath)
            or not isinstance(self.result_set_fingerprint, Fingerprint)
            or not isinstance(self.expected_matrix_fingerprint, Fingerprint)
            or not isinstance(self.security_snapshot_fingerprint, Fingerprint)
            or not isinstance(self.reproducibility_fingerprint, Fingerprint)
            or not isinstance(self.disposition, RunFinalizationDisposition)
            or not isinstance(self.coverage, RunFinalizationCoverage)
            or not isinstance(self.lifecycle_status, RunStatus)
            or not isinstance(self.created_at, UtcTimestamp)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (self.expected_result_count, self.accepted_result_count)
            )
            or self.expected_result_count < 1
            or self.accepted_result_count > self.expected_result_count
            or self.coverage is not expected_coverage
            or self.partial_result_references != ordered_results
            or len(self.partial_result_references)
            != len(
                {
                    (item.case_reference, item.repetition)
                    for item in self.partial_result_references
                }
            )
            or (
                self.partial_result_references
                and self.result_set_fingerprint
                != scoring_result_set_fingerprint(self.partial_result_references)
            )
            or self.terminal_failures != ordered_failures
            or self.reason_codes
            != tuple(sorted(set(self.reason_codes), key=lambda item: item.value))
            or self.terminal_causes
            != tuple(sorted(set(self.terminal_causes), key=lambda item: item.value))
            or not self.reason_codes
            or not all(
                safe_finalization_reference(item)
                for item in (
                    self.security_snapshot_reference,
                    self.producer_id,
                    self.producer_version,
                )
            )
            or (self.path is RunFinalizationPath.SCORABLE and not scorable_valid)
            or (
                self.path is RunFinalizationPath.TERMINALLY_UNSCORABLE
                and not terminal_valid
            )
        ):
            raise FinalizationReproducibilityMismatch()
        expected_fingerprint = finalization_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected_fingerprint)
        elif self.fingerprint != expected_fingerprint:
            raise FinalizationReproducibilityMismatch()
        expected_checksum = finalization_checksum(self)
        if self.checksum is None:
            object.__setattr__(self, "checksum", expected_checksum)
        elif self.checksum != expected_checksum:
            raise FinalizationReproducibilityMismatch()

    @property
    def record_reference(self) -> str:
        assert self.fingerprint is not None
        return (
            f"private-evals-finalization:{self.run_id.value}"
            f"?id={self.finalization_id.value}&fingerprint={self.fingerprint.value}"
        )

    def __repr__(self) -> str:
        return (
            "EvalRunFinalizationRecord("
            f"finalization_id={self.finalization_id!r}, run_id={self.run_id!r}, "
            f"path={self.path!r}, disposition={self.disposition!r}, "
            f"coverage={self.coverage!r}, fingerprint={self.fingerprint!r})"
        )


def finalization_fingerprint(record: EvalRunFinalizationRecord) -> Fingerprint:
    return fingerprint(
        {
            "run_id": record.run_id,
            "manifest_fingerprint": record.manifest_fingerprint,
            "suite": (record.suite_id, record.suite_version),
            "path": record.path,
            "scoring_decision_reference": record.scoring_decision_reference,
            "result_set_fingerprint": record.result_set_fingerprint,
            "expected_matrix_fingerprint": record.expected_matrix_fingerprint,
            "terminal_failure_set_fingerprint": record.terminal_failure_set_fingerprint,
            "security_snapshot_fingerprint": record.security_snapshot_fingerprint,
            "reproducibility_fingerprint": record.reproducibility_fingerprint,
            "disposition": record.disposition,
            "coverage": record.coverage,
            "terminal_causes": record.terminal_causes,
            "lifecycle_status": record.lifecycle_status,
            "reason_codes": record.reason_codes,
            "producer_version": record.producer_version,
        }
    )


def finalization_checksum(record: EvalRunFinalizationRecord) -> ContentChecksum:
    return content_checksum(
        {
            "finalization_id": record.finalization_id,
            "run_id": record.run_id,
            "manifest_fingerprint": record.manifest_fingerprint,
            "suite": (record.suite_id, record.suite_version),
            "path": record.path,
            "scoring_decision_reference": record.scoring_decision_reference,
            "result_set_fingerprint": record.result_set_fingerprint,
            "partial_result_references": record.partial_result_references,
            "expected_matrix_fingerprint": record.expected_matrix_fingerprint,
            "expected_result_count": record.expected_result_count,
            "accepted_result_count": record.accepted_result_count,
            "terminal_failures": record.terminal_failures,
            "terminal_failure_set_fingerprint": record.terminal_failure_set_fingerprint,
            "security_snapshot_reference": record.security_snapshot_reference,
            "security_snapshot_fingerprint": record.security_snapshot_fingerprint,
            "reproducibility_fingerprint": record.reproducibility_fingerprint,
            "disposition": record.disposition,
            "coverage": record.coverage,
            "terminal_causes": record.terminal_causes,
            "lifecycle_status": record.lifecycle_status,
            "reason_codes": record.reason_codes,
            "producer_id": record.producer_id,
            "producer_version": record.producer_version,
            "created_at": record.created_at,
            "fingerprint": record.fingerprint,
        }
    )


def validate_finalization_record(record: EvalRunFinalizationRecord) -> None:
    if (
        not isinstance(record, EvalRunFinalizationRecord)
        or record.fingerprint != finalization_fingerprint(record)
        or record.checksum != finalization_checksum(record)
    ):
        raise FinalizationReproducibilityMismatch()
