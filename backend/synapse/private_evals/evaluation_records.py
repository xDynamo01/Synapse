from __future__ import annotations

from dataclasses import dataclass

from .canonical import content_checksum, fingerprint
from .case_evaluation import (
    CaseEvaluationReasonCode,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    CaseEvaluationStatus,
    EvaluationEventIdentity,
    _safe_reference,
    evaluation_request_fingerprint,
    evaluation_response_fingerprint,
)
from .case_evaluation_errors import EvaluationCorrespondenceMismatch
from .runs import ResourceUsage
from .values import ContentChecksum, Fingerprint, UtcTimestamp


@dataclass(frozen=True)
class EvaluationAttemptRecord:
    event_identity: EvaluationEventIdentity
    attempt: int
    request_fingerprint: Fingerprint
    response_fingerprint: Fingerprint
    status: CaseEvaluationStatus
    started_at: UtcTimestamp
    finished_at: UtcTimestamp
    reason_code: CaseEvaluationReasonCode
    evaluator_artifact_reference: str | None
    provenance_reference: str | None
    resource_usage: ResourceUsage
    fingerprint: Fingerprint | None = None
    checksum: ContentChecksum | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
            or not isinstance(self.request_fingerprint, Fingerprint)
            or not isinstance(self.response_fingerprint, Fingerprint)
            or not isinstance(self.status, CaseEvaluationStatus)
            or not isinstance(self.started_at, UtcTimestamp)
            or not isinstance(self.finished_at, UtcTimestamp)
            or self.finished_at.instant < self.started_at.instant
            or not isinstance(self.reason_code, CaseEvaluationReasonCode)
            or not isinstance(self.resource_usage, ResourceUsage)
        ):
            raise EvaluationCorrespondenceMismatch()
        expected_reason = {
            CaseEvaluationStatus.SUCCEEDED: CaseEvaluationReasonCode.COMPLETED,
            CaseEvaluationStatus.INFRASTRUCTURE_FAILED:
                CaseEvaluationReasonCode.INFRASTRUCTURE_UNAVAILABLE,
            CaseEvaluationStatus.TIMED_OUT: CaseEvaluationReasonCode.EVALUATION_TIMEOUT,
            CaseEvaluationStatus.CANCELLED: CaseEvaluationReasonCode.CANCELLED_BY_REQUEST,
            CaseEvaluationStatus.POLICY_DENIED:
                CaseEvaluationReasonCode.POLICY_NOT_AUTHORIZED,
            CaseEvaluationStatus.INVALID: CaseEvaluationReasonCode.RESPONSE_INVALID,
        }[self.status]
        if self.reason_code is not expected_reason:
            raise EvaluationCorrespondenceMismatch()
        succeeded = self.status is CaseEvaluationStatus.SUCCEEDED
        if succeeded:
            if (
                not _safe_reference(self.evaluator_artifact_reference or "")
                or not _safe_reference(self.provenance_reference or "")
            ):
                raise EvaluationCorrespondenceMismatch()
        elif (
            self.evaluator_artifact_reference is not None
            or self.provenance_reference is not None
        ):
            raise EvaluationCorrespondenceMismatch()
        expected_fingerprint = evaluation_attempt_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected_fingerprint)
        elif self.fingerprint != expected_fingerprint:
            raise EvaluationCorrespondenceMismatch()
        expected_checksum = evaluation_attempt_checksum(self)
        if self.checksum is None:
            object.__setattr__(self, "checksum", expected_checksum)
        elif self.checksum != expected_checksum:
            raise EvaluationCorrespondenceMismatch()

    def __repr__(self) -> str:
        return (
            "EvaluationAttemptRecord("
            f"event={self.event_identity.fingerprint!r}, attempt={self.attempt!r}, "
            f"status={self.status!r}, fingerprint={self.fingerprint!r})"
        )


def evaluation_attempt_fingerprint(record: EvaluationAttemptRecord) -> Fingerprint:
    return fingerprint(
        {
            "event_identity": record.event_identity,
            "attempt": record.attempt,
            "request_fingerprint": record.request_fingerprint,
            "response_fingerprint": record.response_fingerprint,
            "status": record.status,
            "reason_code": record.reason_code,
        }
    )


def evaluation_attempt_checksum(record: EvaluationAttemptRecord) -> ContentChecksum:
    return content_checksum(
        {
            "event_identity": record.event_identity,
            "attempt": record.attempt,
            "request_fingerprint": record.request_fingerprint,
            "response_fingerprint": record.response_fingerprint,
            "status": record.status,
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "reason_code": record.reason_code,
            "evaluator_artifact_reference": record.evaluator_artifact_reference,
            "provenance_reference": record.provenance_reference,
            "resource_usage": record.resource_usage,
            "fingerprint": record.fingerprint,
        }
    )


def evaluation_attempt_record(
    request: CaseEvaluationRequest,
    response: CaseEvaluationResponse,
    *,
    attempt: int,
) -> EvaluationAttemptRecord:
    if (
        response.event_identity != request.event_identity
        or request.fingerprint != evaluation_request_fingerprint(request)
        or response.fingerprint != evaluation_response_fingerprint(response)
    ):
        raise EvaluationCorrespondenceMismatch()
    assert request.fingerprint is not None and response.fingerprint is not None
    return EvaluationAttemptRecord(
        request.event_identity,
        attempt,
        request.fingerprint,
        response.fingerprint,
        response.status,
        response.started_at,
        response.finished_at,
        response.reason_codes[0],
        response.evaluator_artifact_reference,
        response.provenance_reference,
        response.resource_usage,
    )
