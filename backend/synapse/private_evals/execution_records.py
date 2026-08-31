from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import content_checksum, fingerprint
from .execution import (
    CaseExecutionRequest,
    CaseExecutionResponse,
    CaseExecutionStatus,
    ExecutionAttemptIdentity,
    ExecutionReasonCode,
    LogicalExecutionIdentity,
    _safe_reference,
    validate_execution_response,
)
from .execution_errors import (
    AttemptSequenceInvalid,
    ExecutionAccountingIncomplete,
    ExecutionRecordInvalid,
)
from .execution_policy import RetryDecision, RetryDisposition
from .runs import ResourceUsage
from .values import ContentChecksum, Fingerprint, UtcTimestamp


class LogicalExecutionProjectionStatus(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    UNSUCCESSFUL = "unsuccessful"


class ExecutionAccountingStatus(StrEnum):
    INCOMPLETE = "incomplete"
    EXECUTIONS_ACCOUNTED_FOR = "executions_accounted_for"


@dataclass(frozen=True)
class ExecutionAttemptRecord:
    """Immutable historical fact; retry policy is deliberately absent."""

    logical_execution: LogicalExecutionIdentity
    attempt_identity: ExecutionAttemptIdentity
    request_fingerprint: Fingerprint
    response_fingerprint: Fingerprint
    status: CaseExecutionStatus
    started_at: UtcTimestamp
    finished_at: UtcTimestamp
    reason_codes: tuple[ExecutionReasonCode, ...]
    output_asset_reference: str | None
    result_checksum: ContentChecksum | None
    evaluator_artifact_reference: str | None
    provenance_reference: str
    resource_usage: ResourceUsage
    checksum: ContentChecksum | None = None

    def __post_init__(self) -> None:
        if self.attempt_identity.logical_execution_fingerprint != self.logical_execution.fingerprint:
            raise ExecutionRecordInvalid("attempt record identity is inconsistent")
        if self.finished_at.instant < self.started_at.instant:
            raise ExecutionRecordInvalid("attempt record timestamps are inconsistent")
        if not self.provenance_reference:
            raise ExecutionRecordInvalid("attempt record requires provenance")
        _safe_reference(self.provenance_reference, "attempt provenance reference")
        successful = self.status is CaseExecutionStatus.SUCCEEDED
        output_fields = (
            self.output_asset_reference,
            self.result_checksum,
            self.evaluator_artifact_reference,
        )
        if successful and any(value is None for value in output_fields):
            raise ExecutionRecordInvalid("successful attempt record requires final output")
        if not successful and any(value is not None for value in output_fields):
            raise ExecutionRecordInvalid("failed attempt record cannot contain final output")
        expected = attempt_record_checksum(self)
        if self.checksum is None:
            object.__setattr__(self, "checksum", expected)
        elif self.checksum != expected:
            raise ExecutionRecordInvalid("attempt record checksum is inconsistent")

    def __repr__(self) -> str:
        return (
            "ExecutionAttemptRecord("
            f"attempt={self.attempt_identity.attempt!r}, status={self.status!r}, "
            f"checksum={self.checksum!r})"
        )


def attempt_record_checksum(record: ExecutionAttemptRecord) -> ContentChecksum:
    return content_checksum(
        {
            "logical_execution": record.logical_execution,
            "attempt_identity": record.attempt_identity,
            "request_fingerprint": record.request_fingerprint,
            "response_fingerprint": record.response_fingerprint,
            "status": record.status,
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "reason_codes": tuple(sorted(record.reason_codes, key=lambda item: item.value)),
            "output_asset_reference": record.output_asset_reference,
            "result_checksum": record.result_checksum,
            "evaluator_artifact_reference": record.evaluator_artifact_reference,
            "provenance_reference": record.provenance_reference,
            "resource_usage": record.resource_usage,
        }
    )


def attempt_record(
    request: CaseExecutionRequest,
    response: CaseExecutionResponse,
) -> ExecutionAttemptRecord:
    validate_execution_response(request, response)
    assert request.fingerprint is not None and response.fingerprint is not None
    return ExecutionAttemptRecord(
        logical_execution=request.logical_execution,
        attempt_identity=request.attempt_identity,
        request_fingerprint=request.fingerprint,
        response_fingerprint=response.fingerprint,
        status=response.status,
        started_at=response.started_at,
        finished_at=response.finished_at,
        reason_codes=response.reason_codes,
        output_asset_reference=response.output_asset_reference,
        result_checksum=response.result_checksum,
        evaluator_artifact_reference=response.evaluator_artifact_reference,
        provenance_reference=response.provenance_reference,
        resource_usage=response.usage_summary,
    )


@dataclass(frozen=True)
class LogicalExecutionProjection:
    """Rebuildable view over immutable attempts; never an appendable aggregate."""

    logical_execution: LogicalExecutionIdentity
    attempts: tuple[ExecutionAttemptRecord, ...]
    status: LogicalExecutionProjectionStatus
    successful_attempt_reference: Fingerprint | None
    latest_status: CaseExecutionStatus | None
    fingerprint: Fingerprint
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        expected_fingerprint = logical_projection_fingerprint(self)
        if self.fingerprint != expected_fingerprint:
            raise ExecutionRecordInvalid("logical projection fingerprint is inconsistent")
        expected_checksum = logical_projection_checksum(self)
        if self.checksum != expected_checksum:
            raise ExecutionRecordInvalid("logical projection checksum is inconsistent")

    def __repr__(self) -> str:
        return (
            "LogicalExecutionProjection("
            f"logical_execution={self.logical_execution.fingerprint!r}, "
            f"attempt_count={len(self.attempts)!r}, status={self.status!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def _logical_projection_semantic(
    projection: LogicalExecutionProjection,
) -> dict[str, object]:
    return {
        "logical_execution": projection.logical_execution,
        "attempt_checksums": tuple(item.checksum for item in projection.attempts),
        "status": projection.status,
        "successful_attempt_reference": projection.successful_attempt_reference,
        "latest_status": projection.latest_status,
    }


def logical_projection_fingerprint(
    projection: LogicalExecutionProjection,
) -> Fingerprint:
    return fingerprint(_logical_projection_semantic(projection))


def logical_projection_checksum(
    projection: LogicalExecutionProjection,
) -> ContentChecksum:
    return content_checksum(
        {**_logical_projection_semantic(projection), "fingerprint": projection.fingerprint}
    )


def logical_execution_projection(
    logical_execution: LogicalExecutionIdentity,
    attempts: tuple[ExecutionAttemptRecord, ...],
) -> LogicalExecutionProjection:
    numbers = tuple(item.attempt_identity.attempt for item in attempts)
    if numbers != tuple(range(1, len(numbers) + 1)):
        raise AttemptSequenceInvalid("logical execution attempts must be sequential")
    if any(item.logical_execution.fingerprint != logical_execution.fingerprint for item in attempts):
        raise ExecutionRecordInvalid("logical projection contains another execution")
    successes = tuple(item for item in attempts if item.status is CaseExecutionStatus.SUCCEEDED)
    if len(successes) > 1:
        raise ExecutionRecordInvalid("logical execution cannot contain multiple successes")
    if successes and attempts[-1] is not successes[0]:
        raise ExecutionRecordInvalid("logical execution cannot continue after success")
    if successes:
        status = LogicalExecutionProjectionStatus.SUCCEEDED
        successful_reference = successes[0].attempt_identity.fingerprint
    elif attempts:
        status = LogicalExecutionProjectionStatus.UNSUCCESSFUL
        successful_reference = None
    else:
        status = LogicalExecutionProjectionStatus.NOT_ATTEMPTED
        successful_reference = None
    latest_status = attempts[-1].status if attempts else None
    semantic = {
        "logical_execution": logical_execution,
        "attempt_checksums": tuple(item.checksum for item in attempts),
        "status": status,
        "successful_attempt_reference": successful_reference,
        "latest_status": latest_status,
    }
    projection_fingerprint = fingerprint(semantic)
    projection_checksum = content_checksum(
        {**semantic, "fingerprint": projection_fingerprint}
    )
    return LogicalExecutionProjection(
        logical_execution=logical_execution,
        attempts=attempts,
        status=status,
        successful_attempt_reference=successful_reference,
        latest_status=latest_status,
        fingerprint=projection_fingerprint,
        checksum=projection_checksum,
    )


@dataclass(frozen=True)
class PartialFailureSummary:
    total_expected: int
    succeeded: int
    infrastructure_failed: int
    timed_out: int
    cancelled: int
    policy_denied: int
    invalid: int
    pending: int
    retryable: int
    exhausted: int

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field) for field in self.__dataclass_fields__)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ExecutionAccountingIncomplete("partial failure counts must be non-negative")
        classified = (
            self.succeeded
            + self.infrastructure_failed
            + self.timed_out
            + self.cancelled
            + self.policy_denied
            + self.invalid
            + self.pending
        )
        if classified != self.total_expected:
            raise ExecutionAccountingIncomplete(
                "partial failure counts do not match expected total"
            )
        if self.retryable + self.exhausted > self.total_expected:
            raise ExecutionAccountingIncomplete("retry counts exceed expected total")


@dataclass(frozen=True)
class ExecutionAccountingProjection:
    status: ExecutionAccountingStatus
    all_logical_executions_present: bool
    no_retryable_failures: bool
    summary: PartialFailureSummary


def assess_execution_accounting(
    expected: tuple[LogicalExecutionIdentity, ...],
    projections: tuple[LogicalExecutionProjection, ...],
    retry_decisions: tuple[RetryDecision, ...],
) -> ExecutionAccountingProjection:
    expected_ids = tuple(item.fingerprint for item in expected)
    projection_ids = tuple(item.logical_execution.fingerprint for item in projections)
    if len(expected_ids) != len(set(expected_ids)) or len(projection_ids) != len(
        set(projection_ids)
    ):
        raise ExecutionAccountingIncomplete("execution accounting contains duplicate identity")
    if set(projection_ids) - set(expected_ids):
        raise ExecutionAccountingIncomplete("execution accounting contains unexpected identity")
    decisions = {item.attempt_reference: item for item in retry_decisions}
    if len(decisions) != len(retry_decisions):
        raise ExecutionAccountingIncomplete(
            "execution accounting contains duplicate retry decision"
        )
    by_id = {item.logical_execution.fingerprint: item for item in projections}
    selected = [by_id.get(identity) for identity in expected_ids]
    latest_attempts = [
        item.attempts[-1] for item in selected if item is not None and item.attempts
    ]
    latest_statuses = [item.status for item in latest_attempts]
    succeeded = sum(
        item is not None and item.status is LogicalExecutionProjectionStatus.SUCCEEDED
        for item in selected
    )
    pending = sum(
        item is None or item.status is LogicalExecutionProjectionStatus.NOT_ATTEMPTED
        for item in selected
    )
    retryable = 0
    exhausted = 0
    for attempt in latest_attempts:
        attempt_fingerprint = attempt.attempt_identity.fingerprint
        assert attempt_fingerprint is not None
        decision = decisions.get(attempt_fingerprint)
        if decision is not None and decision.response_fingerprint != attempt.response_fingerprint:
            raise ExecutionAccountingIncomplete(
                "retry decision does not match latest response"
            )
        if decision is not None and decision.disposition is RetryDisposition.RETRY_ALLOWED:
            retryable += 1
        if decision is not None and decision.disposition is RetryDisposition.RETRY_EXHAUSTED:
            exhausted += 1
    summary = PartialFailureSummary(
        total_expected=len(expected),
        succeeded=succeeded,
        infrastructure_failed=latest_statuses.count(CaseExecutionStatus.INFRASTRUCTURE_FAILED),
        timed_out=latest_statuses.count(CaseExecutionStatus.TIMED_OUT),
        cancelled=latest_statuses.count(CaseExecutionStatus.CANCELLED),
        policy_denied=latest_statuses.count(CaseExecutionStatus.POLICY_DENIED),
        invalid=latest_statuses.count(CaseExecutionStatus.INVALID),
        pending=pending,
        retryable=retryable,
        exhausted=exhausted,
    )
    all_present = len(projections) == len(expected) and pending == 0
    no_retryable = retryable == 0
    status = (
        ExecutionAccountingStatus.EXECUTIONS_ACCOUNTED_FOR
        if all_present and no_retryable
        else ExecutionAccountingStatus.INCOMPLETE
    )
    return ExecutionAccountingProjection(status, all_present, no_retryable, summary)
