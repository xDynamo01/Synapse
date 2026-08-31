from __future__ import annotations

from typing import Any

from .errors import PrivateEvalDomainError


class ScoringError(PrivateEvalDomainError):
    code = "eval_scoring_error"
    safe_message = "Private Evals scoring operation failed"

    def __init__(
        self,
        _unsafe_message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(self.safe_message, details=details)


class InvalidScoringInput(ScoringError):
    code = "eval_scoring_input_invalid"
    safe_message = "Eval scoring input is invalid"


class DuplicateRepetition(ScoringError):
    code = "eval_scoring_duplicate_repetition"
    safe_message = "Eval scoring repetition is duplicated"


class IncompatibleMetric(ScoringError):
    code = "eval_scoring_incompatible_metric"
    safe_message = "Eval scoring metric is incompatible"


class IncompatibleScale(ScoringError):
    code = "eval_scoring_incompatible_scale"
    safe_message = "Eval scoring scale is incompatible"


class EvaluatorMismatch(ScoringError):
    code = "eval_scoring_evaluator_mismatch"
    safe_message = "Eval scoring evaluator is incompatible"


class IncompatibleConfidenceMethod(ScoringError):
    code = "eval_scoring_confidence_method_incompatible"
    safe_message = "Eval scoring confidence method is incompatible"


class ThresholdMismatch(ScoringError):
    code = "eval_scoring_threshold_mismatch"
    safe_message = "Eval scoring threshold is incompatible"


class InvalidScoringWeight(ScoringError):
    code = "eval_scoring_weight_invalid"
    safe_message = "Eval scoring weight is invalid"


class InvalidFailureBudget(ScoringError):
    code = "eval_scoring_failure_budget_invalid"
    safe_message = "Eval scoring failure budget is invalid"


class DecisionFingerprintMismatch(ScoringError):
    code = "eval_scoring_fingerprint_mismatch"
    safe_message = "Eval scoring decision fingerprint is inconsistent"
