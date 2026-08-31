from __future__ import annotations

from .errors import PrivateEvalDomainError


class CaseEvaluationError(PrivateEvalDomainError):
    code = "case_evaluation_error"
    safe_message = "Case evaluation failed"

    def __init__(self, _unsafe_message: str | None = None) -> None:
        super().__init__(self.safe_message)


class EvaluationRequestInvalid(CaseEvaluationError):
    code = "evaluation_request_invalid"
    safe_message = "Case evaluation request is invalid"


class EvaluationNotSuccessful(CaseEvaluationError):
    code = "evaluation_not_successful"
    safe_message = "Case evaluation did not succeed"


class EvaluationCorrespondenceMismatch(CaseEvaluationError):
    code = "evaluation_correspondence_mismatch"
    safe_message = "Case evaluation correspondence is inconsistent"


class CaseEvaluatorMismatch(CaseEvaluationError):
    code = "case_evaluator_mismatch"
    safe_message = "Case evaluator identity is inconsistent"


class EvaluationMetricMissing(CaseEvaluationError):
    code = "evaluation_metric_missing"
    safe_message = "A required evaluation metric is missing"


class UnexpectedEvaluationMetric(CaseEvaluationError):
    code = "unexpected_evaluation_metric"
    safe_message = "Evaluation contains an unexpected metric"


class DuplicateEvaluationMetric(CaseEvaluationError):
    code = "duplicate_evaluation_metric"
    safe_message = "Evaluation contains a duplicate metric"


class ScoreKindMismatch(CaseEvaluationError):
    code = "score_kind_mismatch"
    safe_message = "Evaluation score kind is inconsistent"


class ScoreScaleMismatch(CaseEvaluationError):
    code = "score_scale_mismatch"
    safe_message = "Evaluation score scale is inconsistent"


class EvaluationScoreInvalid(CaseEvaluationError):
    code = "evaluation_score_invalid"
    safe_message = "Evaluation score is invalid"


class CaseVerdictMismatch(CaseEvaluationError):
    code = "case_verdict_mismatch"
    safe_message = "Case verdict is inconsistent"


class CaseResultFingerprintMismatch(CaseEvaluationError):
    code = "case_result_fingerprint_mismatch"
    safe_message = "Case result fingerprint is inconsistent"


class CaseResultAlreadyExists(CaseEvaluationError):
    code = "case_result_already_exists"
    safe_message = "Logical case result already exists with a different evaluation"


class CaseResultIdempotencyConflict(CaseEvaluationError):
    code = "case_result_idempotency_conflict"
    safe_message = "Case result idempotency conflict"


class CaseResultPersistenceUnavailable(CaseEvaluationError):
    code = "case_result_persistence_unavailable"
    safe_message = "Case result persistence is unavailable"


class CaseResultPersistenceInvalid(CaseEvaluationError):
    code = "case_result_persistence_invalid"
    safe_message = "Case result persistence request is invalid"


class CaseResultPersistenceNotFound(CaseEvaluationError):
    code = "case_result_persistence_not_found"
    safe_message = "Persisted case result was not found"
