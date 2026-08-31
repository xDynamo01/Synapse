from __future__ import annotations

from typing import Any

from .errors import PrivateEvalDomainError


class RunFinalizationError(PrivateEvalDomainError):
    code = "run_finalization_error"
    safe_message = "Private Evals run finalization failed"

    def __init__(
        self,
        _unsafe_message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(self.safe_message, details=details)


class FinalizationInputInvalid(RunFinalizationError):
    code = "run_finalization_input_invalid"
    safe_message = "Run finalization input is invalid"


class FinalizationIncomplete(RunFinalizationError):
    code = "run_finalization_incomplete"
    safe_message = "Run finalization is incomplete"


class FinalizationPathConflict(RunFinalizationError):
    code = "run_finalization_path_conflict"
    safe_message = "Run finalization paths conflict"


class FinalizationScoringDecisionMissing(RunFinalizationError):
    code = "run_finalization_scoring_decision_missing"
    safe_message = "Run finalization requires a scoring decision"


class FinalizationScoringDecisionMismatch(RunFinalizationError):
    code = "run_finalization_scoring_decision_mismatch"
    safe_message = "Run finalization scoring decision is inconsistent"


class TerminalFailureMissing(RunFinalizationError):
    code = "run_finalization_terminal_failure_missing"
    safe_message = "Run finalization requires a terminal failure"


class TerminalFailureMismatch(RunFinalizationError):
    code = "run_finalization_terminal_failure_mismatch"
    safe_message = "Run finalization terminal failure is inconsistent"


class FinalizationRetryStillAvailable(RunFinalizationError):
    code = "run_finalization_retry_available"
    safe_message = "Run finalization cannot proceed while retry remains available"


class FinalizationAlreadyExists(RunFinalizationError):
    code = "run_finalization_already_exists"
    safe_message = "A different finalization already exists for the run"


class FinalizationLifecycleConflict(RunFinalizationError):
    code = "run_finalization_lifecycle_conflict"
    safe_message = "Run finalization lifecycle transition conflicts"


class FinalizationPersistenceUnavailable(RunFinalizationError):
    code = "run_finalization_persistence_unavailable"
    safe_message = "Run finalization persistence is unavailable"


class FinalizationRecoveryRequired(RunFinalizationError):
    code = "run_finalization_recovery_required"
    safe_message = "Run finalization lifecycle recovery is required"


class FinalizationReproducibilityMismatch(RunFinalizationError):
    code = "run_finalization_reproducibility_mismatch"
    safe_message = "Run finalization reproducibility identity is inconsistent"
