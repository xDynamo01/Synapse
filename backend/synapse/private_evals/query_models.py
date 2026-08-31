from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .command_errors import PublicErrorCategory, public_error
from .command_models import _validate_authorization_reference, validate_public_reference
from .values import Fingerprint


@dataclass(frozen=True)
class PrivateEvalQueryContext:
    actor_reference: str
    authorization_decision_reference: str
    authorization_policy_fingerprint: str
    implementation_binding_reference: str
    correlation_reference: str
    request_reference: str

    def __post_init__(self) -> None:
        for value in (
            self.actor_reference,
            self.authorization_decision_reference,
            self.implementation_binding_reference,
        ):
            _validate_authorization_reference(value, self.correlation_reference)
        for value in (
            self.correlation_reference,
            self.request_reference,
        ):
            validate_public_reference(value, self.correlation_reference)
        try:
            Fingerprint(self.authorization_policy_fingerprint)
        except (TypeError, ValueError) as exc:
            raise public_error(
                PublicErrorCategory.UNAUTHORIZED_REFERENCE,
                self.correlation_reference,
            ) from exc

    def __repr__(self) -> str:
        return (
            "PrivateEvalQueryContext("
            f"actor_reference={self.actor_reference!r}, "
            f"correlation_reference={self.correlation_reference!r}, "
            f"request_reference={self.request_reference!r})"
        )


@dataclass(frozen=True)
class RunSummaryRequest:
    context: PrivateEvalQueryContext
    run_id: str

    def __post_init__(self) -> None:
        validate_public_reference(self.run_id, self.context.correlation_reference)


class EvidenceLocalState(StrEnum):
    ABSENT = "absent"
    ATTEMPT_STARTED = "attempt_started"
    RECEIPT_RECORDED = "receipt_recorded"
    RECEIPTS_COMPLETE = "receipts_complete"
    SUBMITTED = "submitted"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True)
class EvidenceLocalStateProjection:
    run_id: str
    finalization_reference: str | None
    submission_reference: str | None
    receipt_count: int
    state: EvidenceLocalState
    chain_complete: bool
    integrity_valid: bool

    def __post_init__(self) -> None:
        validate_public_reference(self.run_id)
        for value in (self.finalization_reference, self.submission_reference):
            if value is not None:
                validate_public_reference(value)
        if (
            isinstance(self.receipt_count, bool)
            or not isinstance(self.receipt_count, int)
            or self.receipt_count < 0
            or not isinstance(self.state, EvidenceLocalState)
        ):
            raise public_error(PublicErrorCategory.INVALID_REQUEST, "query-projection")


@dataclass(frozen=True)
class RunSummaryResponse:
    run_id: str
    suite_id: str
    suite_version: str
    run_status: str
    revision: int
    manifest_reference: str | None
    accepted_result_count: int
    failed_execution_count: int
    scoring_verdict: str | None
    finalization_reference: str | None
    finalization_disposition: str | None
    finalization_coverage: str | None
    finalization_path: str | None
    finalization_lifecycle_status: str | None
    terminal_causes: tuple[str, ...]
    evidence_submission_reference: str | None
    evidence_receipt_count: int
    evidence_local_state: str
    reconciliation_state: str
    correlation_reference: str
