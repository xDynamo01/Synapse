from __future__ import annotations

from typing import Any

from .errors import PrivateEvalDomainError


class RunScoringError(PrivateEvalDomainError):
    code = "run_scoring_error"
    safe_message = "Private Evals run scoring failed"

    def __init__(
        self,
        _unsafe_message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(self.safe_message, details=details)


class RunScoringInputInvalid(RunScoringError):
    code = "run_scoring_input_invalid"
    safe_message = "Run scoring input is invalid"


class ExpectedResultMissing(RunScoringError):
    code = "run_scoring_result_missing"
    safe_message = "An expected run result is missing"


class UnexpectedRunResult(RunScoringError):
    code = "run_scoring_result_unexpected"
    safe_message = "Run scoring received an unexpected result"


class DuplicateLogicalResult(RunScoringError):
    code = "run_scoring_result_duplicate"
    safe_message = "Run scoring received a duplicate logical result"


class RunResultCorrespondenceMismatch(RunScoringError):
    code = "run_scoring_result_correspondence_mismatch"
    safe_message = "Run result correspondence is inconsistent"


class RunResultFingerprintMismatch(RunScoringError):
    code = "run_scoring_result_fingerprint_mismatch"
    safe_message = "Run result integrity is inconsistent"


class RunScoringProtocolMismatch(RunScoringError):
    code = "run_scoring_protocol_mismatch"
    safe_message = "Run scoring protocol is inconsistent"


class RunScoringTargetMismatch(RunScoringError):
    code = "run_scoring_target_mismatch"
    safe_message = "Run scoring target is inconsistent"


class RunScoringObservationMismatch(RunScoringError):
    code = "run_scoring_observation_mismatch"
    safe_message = "Run scoring observation is inconsistent"


class RunScoringDecisionMismatch(RunScoringError):
    code = "run_scoring_decision_mismatch"
    safe_message = "Run scoring decision is inconsistent"


class ScoringDecisionAlreadyExists(RunScoringError):
    code = "run_scoring_decision_exists"
    safe_message = "A different scoring decision already exists for the run"


class RunScoringIdempotencyConflict(RunScoringError):
    code = "run_scoring_idempotency_conflict"
    safe_message = "Run scoring idempotency key conflicts with existing content"


class RunScoringPersistenceUnavailable(RunScoringError):
    code = "run_scoring_persistence_unavailable"
    safe_message = "Run scoring persistence is unavailable"
