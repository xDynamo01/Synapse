from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .execution import (
    CaseExecutionRequest,
    CaseExecutionResponse,
    CaseExecutionStatus,
    ExecutionReasonCode,
    _positive,
    _safe_reference,
    _unique,
    validate_execution_response,
)
from .execution_errors import ReauthorizationRequired, RetryExhausted, RetryNotAllowed
from .values import Fingerprint


class RetryDisposition(StrEnum):
    RETRY_ALLOWED = "retry_allowed"
    RETRY_EXHAUSTED = "retry_exhausted"
    TERMINAL = "terminal"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    PROVIDER_CHANGE_PROHIBITED = "provider_change_prohibited"
    INVALID_RETRY_REQUEST = "invalid_retry_request"


@dataclass(frozen=True)
class RetryPolicy:
    maximum_attempts: int
    retryable_statuses: tuple[CaseExecutionStatus, ...]
    retryable_reason_codes: tuple[ExecutionReasonCode, ...]
    retry_timed_out: bool
    retry_cancelled: bool
    backoff_reference: str | None
    preserve_deterministic_seed: bool
    provider_switch_allowed: bool
    security_reauthorization_required: bool

    def __post_init__(self) -> None:
        _positive(self.maximum_attempts, "maximum attempts")
        _unique(self.retryable_statuses, "retryable status")
        _unique(self.retryable_reason_codes, "retryable reason")
        if self.backoff_reference is not None:
            _safe_reference(self.backoff_reference, "backoff reference")


@dataclass(frozen=True)
class RetryDecision:
    attempt_reference: Fingerprint
    response_fingerprint: Fingerprint
    disposition: RetryDisposition
    retry_allowed: bool
    next_attempt: int | None


def _decision(
    response: CaseExecutionResponse,
    disposition: RetryDisposition,
    *,
    retry_allowed: bool = False,
    next_attempt: int | None = None,
) -> RetryDecision:
    assert response.fingerprint is not None
    return RetryDecision(
        attempt_reference=response.attempt_reference,
        response_fingerprint=response.fingerprint,
        disposition=disposition,
        retry_allowed=retry_allowed,
        next_attempt=next_attempt,
    )


def assess_retry(
    previous_request: CaseExecutionRequest,
    previous_response: CaseExecutionResponse,
    next_request: CaseExecutionRequest | None,
    policy: RetryPolicy,
) -> RetryDecision:
    """Evaluate eligibility only; it performs no scheduling or delay."""
    validate_execution_response(previous_request, previous_response)
    status = previous_response.status
    if status in {
        CaseExecutionStatus.SUCCEEDED,
        CaseExecutionStatus.POLICY_DENIED,
        CaseExecutionStatus.INVALID,
    }:
        return _decision(previous_response, RetryDisposition.TERMINAL)
    if previous_request.attempt_identity.attempt >= policy.maximum_attempts:
        return _decision(previous_response, RetryDisposition.RETRY_EXHAUSTED)

    if status is CaseExecutionStatus.TIMED_OUT:
        status_allowed = policy.retry_timed_out
    elif status is CaseExecutionStatus.CANCELLED:
        status_allowed = policy.retry_cancelled
    else:
        status_allowed = status in policy.retryable_statuses
    reason_allowed = bool(
        set(previous_response.reason_codes) & set(policy.retryable_reason_codes)
    )
    if not status_allowed or not reason_allowed:
        return _decision(previous_response, RetryDisposition.TERMINAL)

    expected_attempt = previous_request.attempt_identity.attempt + 1
    if next_request is None:
        return _decision(
            previous_response,
            RetryDisposition.RETRY_ALLOWED,
            retry_allowed=True,
            next_attempt=expected_attempt,
        )
    if next_request.attempt_identity.attempt != expected_attempt:
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)
    if previous_request.logical_execution.fingerprint != next_request.logical_execution.fingerprint:
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)

    # A semantic snapshot change belongs to a new immutable run manifest, never a retry.
    if previous_request.manifest_fingerprint != next_request.manifest_fingerprint:
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)
    if (
        previous_request.security_snapshot_fingerprint
        != next_request.security_snapshot_fingerprint
    ):
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)
    if (
        previous_request.canonical_egress_manifest_fingerprint
        != next_request.canonical_egress_manifest_fingerprint
    ):
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)
    if (
        previous_request.model_provider_snapshot_fingerprint
        != next_request.model_provider_snapshot_fingerprint
    ):
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)

    security_reference_changed = (
        previous_request.security_snapshot_reference
        != next_request.security_snapshot_reference
        or previous_request.canonical_egress_manifest_reference
        != next_request.canonical_egress_manifest_reference
    )
    if (
        security_reference_changed
        and policy.security_reauthorization_required
        and next_request.reauthorization_reference is None
    ):
        return _decision(previous_response, RetryDisposition.REAUTHORIZATION_REQUIRED)
    if (
        previous_request.model_provider_snapshot_reference
        != next_request.model_provider_snapshot_reference
        and not policy.provider_switch_allowed
    ):
        return _decision(previous_response, RetryDisposition.PROVIDER_CHANGE_PROHIBITED)
    if policy.preserve_deterministic_seed and previous_request.seed != next_request.seed:
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)

    immutable_fields = (
        "manifest_id",
        "suite_id",
        "suite_version",
        "dataset_binding",
        "expected_evaluator",
        "operating_profile",
        "timeout_seconds",
        "execution_protocol",
    )
    if any(
        getattr(previous_request, field) != getattr(next_request, field)
        for field in immutable_fields
    ):
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)
    if any(
        set(getattr(previous_request, field)) != set(getattr(next_request, field))
        for field in ("input_asset_references", "skill_references", "tool_references")
    ):
        return _decision(previous_response, RetryDisposition.INVALID_RETRY_REQUEST)
    return _decision(
        previous_response,
        RetryDisposition.RETRY_ALLOWED,
        retry_allowed=True,
        next_attempt=expected_attempt,
    )


def require_retry(decision: RetryDecision) -> int:
    if decision.disposition is RetryDisposition.RETRY_EXHAUSTED:
        raise RetryExhausted("execution retry attempts are exhausted")
    if decision.disposition is RetryDisposition.REAUTHORIZATION_REQUIRED:
        raise ReauthorizationRequired("execution retry requires security reauthorization")
    if not decision.retry_allowed or decision.next_attempt is None:
        raise RetryNotAllowed("execution retry is not allowed")
    return decision.next_attempt
