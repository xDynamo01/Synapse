from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from synapse.project_governance.models import RFCImplementationBinding

from .canonical import content_checksum, fingerprint
from .evidence import EvidenceProjectionKind, validate_evidence_reference
from .evidence_submission_errors import (
    EvidencePlanInvalid,
    EvidenceProjectionFingerprintMismatch,
    GovernanceReferenceMismatch,
    PartialEvidenceRecoveryConflict,
)
from .store_models import IdempotencyKey
from .values import ContentChecksum, EvalRunId, Fingerprint, UtcTimestamp


class EvidenceSubmissionOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    PARTIAL_RECOVERY = "partial_recovery"
    NOT_APPLICABLE = "not_applicable"


class EvidenceSubmissionAttemptStatus(StrEnum):
    GOVERNANCE_WRITE_STARTED = "governance_write_started"


@dataclass(frozen=True)
class EvidenceProjectionSpecification:
    projection_kind: EvidenceProjectionKind
    source_record_reference: str
    source_fingerprint: Fingerprint
    finalization_reference: str
    finalization_fingerprint: Fingerprint
    scoring_decision_reference: Fingerprint | None
    terminal_failure_set_reference: Fingerprint | None
    reproducibility_fingerprint: Fingerprint
    security_snapshot_reference: str
    security_snapshot_fingerprint: Fingerprint
    implementation_binding_reference: str
    expected_projection_fingerprint: Fingerprint

    def __post_init__(self) -> None:
        if not isinstance(self.projection_kind, EvidenceProjectionKind):
            raise EvidencePlanInvalid()
        for reference in (
            self.source_record_reference,
            self.finalization_reference,
            self.security_snapshot_reference,
            self.implementation_binding_reference,
        ):
            try:
                validate_evidence_reference(reference, "Evidence submission reference")
            except Exception as exc:
                raise EvidencePlanInvalid() from exc
        for digest in (
            self.source_fingerprint,
            self.finalization_fingerprint,
            self.reproducibility_fingerprint,
            self.security_snapshot_fingerprint,
            self.expected_projection_fingerprint,
        ):
            if not isinstance(digest, Fingerprint):
                raise EvidencePlanInvalid()
        for optional_digest in (
            self.scoring_decision_reference,
            self.terminal_failure_set_reference,
        ):
            if optional_digest is not None and not isinstance(optional_digest, Fingerprint):
                raise EvidencePlanInvalid()


@dataclass(frozen=True)
class EvalEvidenceSubmissionPlan:
    run_id: EvalRunId
    finalization_reference: str
    finalization_fingerprint: Fingerprint
    implementation: RFCImplementationBinding
    implementation_binding_reference: str
    specifications: tuple[EvidenceProjectionSpecification, ...]
    idempotency_key: IdempotencyKey
    correlation_reference: str
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    plan_fingerprint: Fingerprint | None = None
    semantic_fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        try:
            for value in (
                self.finalization_reference,
                self.implementation_binding_reference,
                self.correlation_reference,
                self.producer_id,
                self.producer_version,
                *(item.source_record_reference for item in self.specifications),
            ):
                validate_evidence_reference(value, "Evidence plan reference")
        except Exception as exc:
            raise EvidencePlanInvalid() from exc
        ordered = tuple(sorted(self.specifications, key=lambda item: item.projection_kind.value))
        kinds = tuple(item.projection_kind for item in ordered)
        if (
            not isinstance(self.run_id, EvalRunId)
            or not isinstance(self.finalization_fingerprint, Fingerprint)
            or not isinstance(self.implementation, RFCImplementationBinding)
            or not isinstance(self.idempotency_key, IdempotencyKey)
            or not isinstance(self.created_at, UtcTimestamp)
            or self.specifications != ordered
            or len(kinds) != len(set(kinds))
        ):
            raise EvidencePlanInvalid()
        expected_plan = evidence_submission_plan_fingerprint(self)
        if self.plan_fingerprint is None:
            object.__setattr__(self, "plan_fingerprint", expected_plan)
        elif self.plan_fingerprint != expected_plan:
            raise EvidencePlanInvalid()
        expected = evidence_submission_semantic_fingerprint(self)
        if self.semantic_fingerprint is None:
            object.__setattr__(self, "semantic_fingerprint", expected)
        elif self.semantic_fingerprint != expected:
            raise EvidencePlanInvalid()

    @property
    def projection_kinds(self) -> tuple[EvidenceProjectionKind, ...]:
        return tuple(item.projection_kind for item in self.specifications)

    @property
    def expected_projection_fingerprints(self) -> tuple[Fingerprint, ...]:
        return tuple(item.expected_projection_fingerprint for item in self.specifications)

    @property
    def source_references(self) -> tuple[str, ...]:
        return tuple(item.source_record_reference for item in self.specifications)

    def __repr__(self) -> str:
        return (
            "EvalEvidenceSubmissionPlan("
            f"run_id={self.run_id!r}, projection_kinds={self.projection_kinds!r}, "
            f"plan_fingerprint={self.plan_fingerprint!r}, "
            f"semantic_fingerprint={self.semantic_fingerprint!r})"
        )


def evidence_submission_plan_fingerprint(plan: EvalEvidenceSubmissionPlan) -> Fingerprint:
    return fingerprint(
        {
            "run_id": plan.run_id,
            "finalization_reference": plan.finalization_reference,
            "finalization_fingerprint": plan.finalization_fingerprint,
            "implementation": plan.implementation,
            "implementation_binding_reference": plan.implementation_binding_reference,
            "specifications": plan.specifications,
            "producer": (plan.producer_id, plan.producer_version),
        }
    )


def evidence_submission_semantic_fingerprint(plan: EvalEvidenceSubmissionPlan) -> Fingerprint:
    return fingerprint(
        {
            "run_id": plan.run_id,
            "finalization_fingerprint": plan.finalization_fingerprint,
            "implementation": plan.implementation,
            "projection_kinds": plan.projection_kinds,
            "projection_fingerprints": plan.expected_projection_fingerprints,
            "producer_version": plan.producer_version,
        }
    )


@dataclass(frozen=True)
class GovernanceEvidenceIdentity:
    projection_kind: EvidenceProjectionKind
    projection_fingerprint: Fingerprint
    evidence_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.projection_kind, EvidenceProjectionKind) or not isinstance(
            self.projection_fingerprint, Fingerprint
        ):
            raise GovernanceReferenceMismatch()
        try:
            validate_evidence_reference(self.evidence_id, "institutional Evidence ID")
        except Exception as exc:
            raise GovernanceReferenceMismatch() from exc


@dataclass(frozen=True)
class GovernanceEvidenceReceipt:
    projection_kind: EvidenceProjectionKind
    projection_fingerprint: Fingerprint
    evidence_id: str
    evidence_checksum: ContentChecksum

    def __post_init__(self) -> None:
        if (
            not isinstance(self.projection_kind, EvidenceProjectionKind)
            or not isinstance(self.projection_fingerprint, Fingerprint)
            or not isinstance(self.evidence_checksum, ContentChecksum)
        ):
            raise GovernanceReferenceMismatch()
        try:
            validate_evidence_reference(self.evidence_id, "institutional Evidence reference")
        except Exception as exc:
            raise GovernanceReferenceMismatch() from exc


@dataclass(frozen=True)
class EvidenceSubmissionAttemptRecord:
    logical_submission_fingerprint: Fingerprint
    attempt_number: int
    projection_fingerprint: Fingerprint
    projection_kind: EvidenceProjectionKind
    request_fingerprint: Fingerprint
    started_at: UtcTimestamp
    retry_policy_reference: str
    status: EvidenceSubmissionAttemptStatus = (
        EvidenceSubmissionAttemptStatus.GOVERNANCE_WRITE_STARTED
    )
    fingerprint: Fingerprint | None = None
    checksum: ContentChecksum | None = None

    def __post_init__(self) -> None:
        try:
            validate_evidence_reference(
                self.retry_policy_reference, "Evidence retry policy reference"
            )
        except Exception as exc:
            raise PartialEvidenceRecoveryConflict() from exc
        if (
            not isinstance(self.logical_submission_fingerprint, Fingerprint)
            or not isinstance(self.projection_fingerprint, Fingerprint)
            or not isinstance(self.projection_kind, EvidenceProjectionKind)
            or not isinstance(self.request_fingerprint, Fingerprint)
            or not isinstance(self.started_at, UtcTimestamp)
            or not isinstance(self.status, EvidenceSubmissionAttemptStatus)
            or isinstance(self.attempt_number, bool)
            or not isinstance(self.attempt_number, int)
            or self.attempt_number < 1
        ):
            raise PartialEvidenceRecoveryConflict()
        expected_fingerprint = evidence_submission_attempt_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected_fingerprint)
        elif self.fingerprint != expected_fingerprint:
            raise PartialEvidenceRecoveryConflict()
        expected = evidence_submission_attempt_checksum(self)
        if self.checksum is None:
            object.__setattr__(self, "checksum", expected)
        elif self.checksum != expected:
            raise PartialEvidenceRecoveryConflict()

    def __repr__(self) -> str:
        return (
            "EvidenceSubmissionAttemptRecord("
            f"attempt_number={self.attempt_number!r}, projection_kind={self.projection_kind!r}, "
            f"projection_fingerprint={self.projection_fingerprint!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def evidence_submission_attempt_fingerprint(
    record: EvidenceSubmissionAttemptRecord,
) -> Fingerprint:
    return fingerprint(
        {
            "logical_submission_fingerprint": record.logical_submission_fingerprint,
            "attempt_number": record.attempt_number,
            "projection_fingerprint": record.projection_fingerprint,
            "projection_kind": record.projection_kind,
            "request_fingerprint": record.request_fingerprint,
            "retry_policy_reference": record.retry_policy_reference,
            "status": record.status,
        }
    )


def evidence_submission_attempt_checksum(
    record: EvidenceSubmissionAttemptRecord,
) -> ContentChecksum:
    return content_checksum(
        {
            "logical_submission_fingerprint": record.logical_submission_fingerprint,
            "attempt_number": record.attempt_number,
            "projection_fingerprint": record.projection_fingerprint,
            "projection_kind": record.projection_kind,
            "request_fingerprint": record.request_fingerprint,
            "started_at": record.started_at,
            "retry_policy_reference": record.retry_policy_reference,
            "status": record.status,
            "fingerprint": record.fingerprint,
        }
    )


@dataclass(frozen=True)
class EvidenceSubmissionReceiptRecord:
    logical_submission_fingerprint: Fingerprint
    attempt_fingerprint: Fingerprint
    attempt_number: int
    projection_fingerprint: Fingerprint
    projection_kind: EvidenceProjectionKind
    governance_receipt: GovernanceEvidenceReceipt
    received_at: UtcTimestamp
    checksum: ContentChecksum | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.logical_submission_fingerprint, Fingerprint)
            or not isinstance(self.attempt_fingerprint, Fingerprint)
            or isinstance(self.attempt_number, bool)
            or not isinstance(self.attempt_number, int)
            or self.attempt_number < 1
            or not isinstance(self.projection_fingerprint, Fingerprint)
            or not isinstance(self.projection_kind, EvidenceProjectionKind)
            or not isinstance(self.governance_receipt, GovernanceEvidenceReceipt)
            or not isinstance(self.received_at, UtcTimestamp)
            or self.governance_receipt.projection_kind is not self.projection_kind
            or self.governance_receipt.projection_fingerprint != self.projection_fingerprint
        ):
            raise PartialEvidenceRecoveryConflict()
        expected = evidence_submission_receipt_checksum(self)
        if self.checksum is None:
            object.__setattr__(self, "checksum", expected)
        elif self.checksum != expected:
            raise PartialEvidenceRecoveryConflict()

    def __repr__(self) -> str:
        return (
            "EvidenceSubmissionReceiptRecord("
            f"attempt_number={self.attempt_number!r}, "
            f"projection_kind={self.projection_kind!r}, "
            f"projection_fingerprint={self.projection_fingerprint!r})"
        )


def evidence_submission_receipt_checksum(
    record: EvidenceSubmissionReceiptRecord,
) -> ContentChecksum:
    return content_checksum(
        {
            "logical_submission_fingerprint": record.logical_submission_fingerprint,
            "attempt_fingerprint": record.attempt_fingerprint,
            "attempt_number": record.attempt_number,
            "projection_fingerprint": record.projection_fingerprint,
            "projection_kind": record.projection_kind,
            "governance_receipt": record.governance_receipt,
            "received_at": record.received_at,
        }
    )


@dataclass(frozen=True)
class EvalEvidenceSubmissionRecord:
    submission_id: str
    run_id: EvalRunId
    finalization_reference: str
    finalization_fingerprint: Fingerprint
    implementation: RFCImplementationBinding
    implementation_binding_reference: str
    projection_fingerprints: tuple[Fingerprint, ...]
    governance_receipts: tuple[GovernanceEvidenceReceipt, ...]
    submitted_at: UtcTimestamp
    producer_id: str
    producer_version: str
    semantic_fingerprint: Fingerprint
    checksum: ContentChecksum | None = None

    def __post_init__(self) -> None:
        try:
            for value in (
                self.submission_id,
                self.finalization_reference,
                self.implementation_binding_reference,
                self.producer_id,
                self.producer_version,
            ):
                validate_evidence_reference(value, "Evidence submission reference")
        except Exception as exc:
            raise EvidencePlanInvalid() from exc
        if (
            not isinstance(self.run_id, EvalRunId)
            or not isinstance(self.finalization_fingerprint, Fingerprint)
            or not isinstance(self.implementation, RFCImplementationBinding)
            or not isinstance(self.submitted_at, UtcTimestamp)
            or not isinstance(self.semantic_fingerprint, Fingerprint)
            or any(not isinstance(item, Fingerprint) for item in self.projection_fingerprints)
            or any(
                not isinstance(item, GovernanceEvidenceReceipt) for item in self.governance_receipts
            )
            or len(self.projection_fingerprints) != len(self.governance_receipts)
            or self.projection_fingerprints
            != tuple(item.projection_fingerprint for item in self.governance_receipts)
            or len(self.projection_fingerprints) != len(set(self.projection_fingerprints))
        ):
            raise EvidenceProjectionFingerprintMismatch()
        expected = evidence_submission_record_checksum(self)
        if self.checksum is None:
            object.__setattr__(self, "checksum", expected)
        elif self.checksum != expected:
            raise EvidenceProjectionFingerprintMismatch()

    def __repr__(self) -> str:
        return (
            "EvalEvidenceSubmissionRecord("
            f"submission_id={self.submission_id!r}, run_id={self.run_id!r}, "
            f"semantic_fingerprint={self.semantic_fingerprint!r})"
        )


def evidence_submission_record_checksum(
    record: EvalEvidenceSubmissionRecord,
) -> ContentChecksum:
    return content_checksum(
        {
            "submission_id": record.submission_id,
            "run_id": record.run_id,
            "finalization_reference": record.finalization_reference,
            "finalization_fingerprint": record.finalization_fingerprint,
            "implementation": record.implementation,
            "implementation_binding_reference": record.implementation_binding_reference,
            "projection_fingerprints": record.projection_fingerprints,
            "governance_receipts": record.governance_receipts,
            "submitted_at": record.submitted_at,
            "producer_id": record.producer_id,
            "producer_version": record.producer_version,
            "semantic_fingerprint": record.semantic_fingerprint,
        }
    )


@dataclass(frozen=True)
class EvidenceSubmissionResult:
    outcome: EvidenceSubmissionOutcome
    plan: EvalEvidenceSubmissionPlan
    record: EvalEvidenceSubmissionRecord | None
