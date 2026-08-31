from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .case_evaluation import CaseEvaluationResponse
from .command_errors import PrivateEvalBoundaryError, PublicErrorCategory, public_error
from .evidence_submission_models import GovernanceEvidenceIdentity
from .store_models import IdempotencyKey
from .values import Fingerprint, Revision, UtcTimestamp

_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{0,255}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


def validate_public_reference(value: str, correlation_reference: str = "request") -> None:
    if (
        not isinstance(value, str)
        or not _SAFE_REFERENCE.fullmatch(value)
        or _SENSITIVE.search(value)
        or "/" in value
        or "\\" in value
        or "://" in value
    ):
        raise public_error(PublicErrorCategory.INVALID_REQUEST, correlation_reference)


def _validate_authorization_reference(value: str, correlation_reference: str) -> None:
    try:
        validate_public_reference(value, correlation_reference)
    except PrivateEvalBoundaryError as exc:
        raise public_error(
            PublicErrorCategory.UNAUTHORIZED_REFERENCE, correlation_reference
        ) from exc


@dataclass(frozen=True)
class PrivateEvalCommandContext:
    actor_reference: str
    authorization_decision_reference: str
    authorization_policy_fingerprint: str
    implementation_binding_reference: str
    correlation_reference: str
    request_reference: str
    idempotency_key: str
    requested_at: str

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
            self.idempotency_key,
        ):
            validate_public_reference(value, self.correlation_reference)
        try:
            Fingerprint(self.authorization_policy_fingerprint)
            IdempotencyKey(self.idempotency_key)
            UtcTimestamp(self.requested_at)
        except (TypeError, ValueError) as exc:
            raise public_error(
                PublicErrorCategory.UNAUTHORIZED_REFERENCE,
                self.correlation_reference,
            ) from exc

    @property
    def internal_idempotency_key(self) -> IdempotencyKey:
        return IdempotencyKey(self.idempotency_key)

    @property
    def timestamp(self) -> UtcTimestamp:
        return UtcTimestamp(self.requested_at)

    def __repr__(self) -> str:
        return (
            "PrivateEvalCommandContext("
            f"actor_reference={self.actor_reference!r}, "
            f"authorization_decision_reference={self.authorization_decision_reference!r}, "
            f"correlation_reference={self.correlation_reference!r}, "
            f"request_reference={self.request_reference!r})"
        )


@dataclass(frozen=True)
class CreateRunCommand:
    context: PrivateEvalCommandContext
    run_id: str
    manifest_reference: str

    def __post_init__(self) -> None:
        validate_public_reference(self.run_id, self.context.correlation_reference)
        validate_public_reference(self.manifest_reference, self.context.correlation_reference)


@dataclass(frozen=True)
class StartRunCommand:
    context: PrivateEvalCommandContext
    run_id: str
    expected_revision: int

    def __post_init__(self) -> None:
        validate_public_reference(self.run_id, self.context.correlation_reference)
        try:
            Revision(self.expected_revision)
        except (TypeError, ValueError) as exc:
            raise public_error(
                PublicErrorCategory.INVALID_REQUEST, self.context.correlation_reference
            ) from exc


@dataclass(frozen=True)
class RecordMaterializedOutputCommand:
    context: PrivateEvalCommandContext
    run_id: str
    execution_request_reference: str
    execution_attempt_reference: str
    logical_projection_reference: str
    manifest_reference: str
    case_reference: str
    output_reference: str
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        _validate_command_references(self)


@dataclass(frozen=True)
class CreateEvalResultCommand:
    context: PrivateEvalCommandContext
    run_id: str
    materialized_output_reference: str
    evaluation_request_reference: str
    evaluation_response: CaseEvaluationResponse
    manifest_reference: str
    case_reference: str
    scoring_protocol_reference: str
    result_reference: str
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        _validate_command_references(self, excluded={"evaluation_response"})
        if not isinstance(self.evaluation_response, CaseEvaluationResponse):
            raise public_error(
                PublicErrorCategory.INVALID_REQUEST, self.context.correlation_reference
            )


@dataclass(frozen=True)
class CreateScoringDecisionCommand:
    context: PrivateEvalCommandContext
    run_id: str
    manifest_reference: str
    manifest_fingerprint: str
    scoring_protocol_reference: str
    scoring_protocol_fingerprint: str
    expected_matrix_reference: str
    result_references: tuple[str, ...]
    decision_reference: str
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        _validate_command_references(
            self,
            tuple_fields={"result_references"},
            excluded={"manifest_fingerprint", "scoring_protocol_fingerprint"},
        )
        if not self.result_references:
            raise public_error(
                PublicErrorCategory.INVALID_REQUEST, self.context.correlation_reference
            )
        try:
            Fingerprint(self.manifest_fingerprint)
            Fingerprint(self.scoring_protocol_fingerprint)
        except (TypeError, ValueError) as exc:
            raise public_error(
                PublicErrorCategory.INVALID_REQUEST, self.context.correlation_reference
            ) from exc


@dataclass(frozen=True)
class FinalizeRunCommand:
    context: PrivateEvalCommandContext
    run_id: str
    finalization_reference: str
    run_reference: str
    manifest_reference: str
    expected_matrix_reference: str
    result_references: tuple[str, ...]
    scoring_decision_reference: str | None
    terminal_failure_references: tuple[str, ...]
    execution_accounting_reference: str
    execution_projection_references: tuple[str, ...]
    evaluation_attempt_references: tuple[str, ...]
    security_snapshot_reference: str
    security_snapshot_fingerprint: str
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        _validate_finalization_command(self)


@dataclass(frozen=True)
class RecoverFinalizationCommand:
    context: PrivateEvalCommandContext
    run_id: str
    persisted_finalization_reference: str
    run_reference: str
    manifest_reference: str
    expected_matrix_reference: str
    result_references: tuple[str, ...]
    scoring_decision_reference: str | None
    terminal_failure_references: tuple[str, ...]
    execution_accounting_reference: str
    execution_projection_references: tuple[str, ...]
    evaluation_attempt_references: tuple[str, ...]
    security_snapshot_reference: str
    security_snapshot_fingerprint: str
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        _validate_finalization_command(self)


@dataclass(frozen=True)
class SubmitEvidenceCommand:
    context: PrivateEvalCommandContext
    run_id: str
    submission_id: str
    finalization_reference: str
    implementation_reference: str
    projection_candidate_references: tuple[str, ...]
    scoring_decision_reference: str | None
    governance_identities: tuple[GovernanceEvidenceIdentity, ...]
    producer_id: str
    producer_version: str

    def __post_init__(self) -> None:
        _validate_command_references(
            self,
            tuple_fields={"projection_candidate_references"},
            excluded={"governance_identities"},
        )
        if any(
            not isinstance(item, GovernanceEvidenceIdentity)
            for item in self.governance_identities
        ):
            raise public_error(
                PublicErrorCategory.INVALID_REQUEST, self.context.correlation_reference
            )


def _validate_command_references(
    command: object,
    *,
    tuple_fields: set[str] | None = None,
    excluded: set[str] | None = None,
) -> None:
    tuple_fields = tuple_fields or set()
    excluded = excluded or set()
    correlation = command.context.correlation_reference  # type: ignore[attr-defined]
    for name, value in vars(command).items():
        if name == "context" or name in excluded:
            continue
        if name in tuple_fields:
            if not isinstance(value, tuple) or len(value) != len(set(value)):
                raise public_error(PublicErrorCategory.INVALID_REQUEST, correlation)
            for item in value:
                validate_public_reference(item, correlation)
        elif value is not None:
            validate_public_reference(value, correlation)


def _validate_finalization_command(
    command: FinalizeRunCommand | RecoverFinalizationCommand,
) -> None:
    _validate_command_references(
        command,
        tuple_fields={
            "result_references",
            "terminal_failure_references",
            "execution_projection_references",
            "evaluation_attempt_references",
        },
        excluded={"security_snapshot_fingerprint"},
    )
    try:
        Fingerprint(command.security_snapshot_fingerprint)
    except (TypeError, ValueError) as exc:
        raise public_error(
            PublicErrorCategory.INVALID_REQUEST,
            command.context.correlation_reference,
        ) from exc


class PublicWriteOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    RECOVERED = "recovered"
    SUBMITTED = "submitted"
    RECEIPT_RECORDED = "receipt_recorded"
    LOCAL_REPLAY = "local_replay"
    NOT_APPLICABLE = "not_applicable"
    APPLIED = "applied"


@dataclass(frozen=True)
class RunMutationResponse:
    run_id: str
    run_status: str
    revision: int
    manifest_reference: str | None
    outcome: PublicWriteOutcome
    correlation_reference: str


@dataclass(frozen=True)
class RecordWriteResponse:
    record_reference: str
    fingerprint: str
    checksum: str
    outcome: PublicWriteOutcome
    correlation_reference: str


@dataclass(frozen=True)
class ScoringDecisionResponse:
    decision_reference: str
    run_id: str
    scoring_verdict: str
    decision_fingerprint: str
    checksum: str
    outcome: PublicWriteOutcome
    correlation_reference: str


@dataclass(frozen=True)
class FinalizationResponse:
    finalization_reference: str
    run_id: str
    run_status: str
    scoring_verdict: str | None
    finalization_disposition: str
    coverage: str
    path: str
    outcome: PublicWriteOutcome
    correlation_reference: str


@dataclass(frozen=True)
class EvidenceSubmissionResponse:
    submission_reference: str | None
    run_id: str
    projection_kinds: tuple[str, ...]
    receipt_references: tuple[str, ...]
    local_outcome: PublicWriteOutcome
    correlation_reference: str

    def __repr__(self) -> str:
        return (
            "EvidenceSubmissionResponse("
            f"submission_reference={self.submission_reference!r}, run_id={self.run_id!r}, "
            f"projection_kinds={self.projection_kinds!r}, "
            f"local_outcome={self.local_outcome!r})"
        )
