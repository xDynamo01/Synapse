from __future__ import annotations

from .errors import PrivateEvalDomainError


class EvidenceSubmissionError(PrivateEvalDomainError):
    safe_message = "Evidence submission failed"

    def __init__(self, _unsafe_message: str | None = None) -> None:
        super().__init__(self.safe_message)


class EvidencePlanInvalid(EvidenceSubmissionError):
    safe_message = "Evidence submission plan is invalid"


class EvidencePlanIncomplete(EvidenceSubmissionError):
    safe_message = "Evidence submission plan is incomplete"


class EvidenceSourceMismatch(EvidenceSubmissionError):
    safe_message = "Evidence source does not match finalization"


class EvidenceProjectionKindInvalid(EvidenceSubmissionError):
    safe_message = "Evidence projection kind is invalid"


class EvidenceProjectionFingerprintMismatch(EvidenceSubmissionError):
    safe_message = "Evidence projection fingerprint does not match"


class EvidenceImplementationBindingMismatch(EvidenceSubmissionError):
    safe_message = "Evidence implementation binding does not match"


class GovernanceSubmissionUnavailable(EvidenceSubmissionError):
    safe_message = "Governance Evidence submission is unavailable"


class GovernanceReferenceMismatch(EvidenceSubmissionError):
    safe_message = "Governance Evidence reference does not match"


class EvidenceSubmissionContentConflict(EvidenceSubmissionError):
    safe_message = "Evidence submission already exists with different content"


class EvidenceSubmissionIdempotencyConflict(EvidenceSubmissionError):
    safe_message = "Evidence submission idempotency conflict"


class PartialEvidenceRecoveryConflict(EvidenceSubmissionError):
    safe_message = "Partial Evidence submission recovery conflict"


class EvidenceReconciliationRequired(EvidenceSubmissionError):
    safe_message = "Evidence submission requires manual reconciliation"


class EvidencePersistenceUnavailable(EvidenceSubmissionError):
    safe_message = "Evidence submission persistence is unavailable"
