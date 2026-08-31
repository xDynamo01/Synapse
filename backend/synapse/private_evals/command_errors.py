from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PublicErrorCategory(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED_REFERENCE = "unauthorized_reference"
    NOT_FOUND = "not_found"
    INCOMPLETE = "incomplete"
    CONFLICT = "conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    LIFECYCLE_CONFLICT = "lifecycle_conflict"
    PERSISTENCE_UNAVAILABLE = "persistence_unavailable"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    GOVERNANCE_SUBMISSION_UNAVAILABLE = "governance_submission_unavailable"


_MESSAGES = {
    PublicErrorCategory.INVALID_REQUEST: "Private Evals request is invalid",
    PublicErrorCategory.UNAUTHORIZED_REFERENCE: "Authorization reference is invalid",
    PublicErrorCategory.NOT_FOUND: "Private Evals record was not found",
    PublicErrorCategory.INCOMPLETE: "Private Evals operation is incomplete",
    PublicErrorCategory.CONFLICT: "Private Evals operation conflicts with existing state",
    PublicErrorCategory.IDEMPOTENCY_CONFLICT: "Private Evals idempotency conflict",
    PublicErrorCategory.LIFECYCLE_CONFLICT: "Private Evals lifecycle conflict",
    PublicErrorCategory.PERSISTENCE_UNAVAILABLE: "Private Evals persistence is unavailable",
    PublicErrorCategory.RECONCILIATION_REQUIRED: (
        "Private Evals state requires manual reconciliation"
    ),
    PublicErrorCategory.GOVERNANCE_SUBMISSION_UNAVAILABLE: (
        "Governance Evidence submission is unavailable"
    ),
}


@dataclass(frozen=True)
class PrivateEvalErrorEnvelope:
    code: PublicErrorCategory
    message: str
    correlation_reference: str
    def __repr__(self) -> str:
        return (
            "PrivateEvalErrorEnvelope("
            f"code={self.code!r}, correlation_reference={self.correlation_reference!r})"
        )


class PrivateEvalBoundaryError(Exception):
    def __init__(self, envelope: PrivateEvalErrorEnvelope) -> None:
        self.envelope = envelope
        super().__init__(envelope.message)

    def __repr__(self) -> str:
        return f"PrivateEvalBoundaryError(code={self.envelope.code!r})"


class PrivateEvalInputResolutionError(Exception):
    """Expected failure from a read-only referenced-input capability."""


class ReferencedInputNotFound(PrivateEvalInputResolutionError):
    pass


class ReferencedInputMismatch(PrivateEvalInputResolutionError):
    pass


class ReferencedInputUnavailable(PrivateEvalInputResolutionError):
    pass


def public_error(
    category: PublicErrorCategory,
    correlation_reference: str,
) -> PrivateEvalBoundaryError:
    return PrivateEvalBoundaryError(
        PrivateEvalErrorEnvelope(
            category,
            _MESSAGES[category],
            correlation_reference,
        )
    )
