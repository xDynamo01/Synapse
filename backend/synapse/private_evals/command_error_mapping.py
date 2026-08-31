from __future__ import annotations

from .case_evaluation_errors import (
    CaseEvaluationError,
    CaseResultIdempotencyConflict,
    CaseResultPersistenceNotFound,
    CaseResultPersistenceUnavailable,
)
from .command_errors import (
    PrivateEvalBoundaryError,
    PrivateEvalInputResolutionError,
    PublicErrorCategory,
    ReferencedInputMismatch,
    ReferencedInputNotFound,
    ReferencedInputUnavailable,
    public_error,
)
from .errors import PrivateEvalDomainError
from .evidence_submission_errors import (
    EvidencePersistenceUnavailable,
    EvidencePlanIncomplete,
    EvidenceReconciliationRequired,
    EvidenceSubmissionContentConflict,
    EvidenceSubmissionError,
    EvidenceSubmissionIdempotencyConflict,
    GovernanceSubmissionUnavailable,
    PartialEvidenceRecoveryConflict,
)
from .result_errors import (
    OutputMaterializationError,
    ResultAlreadyExistsWithDifferentContent,
    ResultIdempotencyConflict,
    ResultPersistenceNotFound,
    ResultPersistenceUnavailable,
)
from .run_errors import (
    EvalRunLifecycleError,
    InvalidRunTransition,
    ManifestNotFound,
    RunLifecycleIdempotencyConflict,
    RunLifecycleUnavailable,
    RunNotFound,
    RunRevisionConflict,
)
from .run_finalization_errors import (
    FinalizationAlreadyExists,
    FinalizationIncomplete,
    FinalizationLifecycleConflict,
    FinalizationPersistenceUnavailable,
    FinalizationRecoveryRequired,
    FinalizationScoringDecisionMissing,
    RunFinalizationError,
    TerminalFailureMissing,
)
from .run_scoring_errors import (
    ExpectedResultMissing,
    RunScoringError,
    RunScoringIdempotencyConflict,
    RunScoringPersistenceUnavailable,
    ScoringDecisionAlreadyExists,
)
from .store_errors import (
    EvalIdempotencyConflict,
    EvalRecordNotFound,
    EvalStoreError,
    EvalStoreUnavailable,
)

EXPECTED_BOUNDARY_ERRORS = (
    PrivateEvalBoundaryError,
    PrivateEvalInputResolutionError,
    EvalRunLifecycleError,
    OutputMaterializationError,
    CaseEvaluationError,
    RunScoringError,
    RunFinalizationError,
    EvidenceSubmissionError,
    EvalStoreError,
)


def translate_expected_error(
    exc: Exception, correlation_reference: str
) -> PrivateEvalBoundaryError:
    """Translate only declared boundary/domain failures; programming errors escape."""
    if isinstance(exc, PrivateEvalBoundaryError):
        return exc
    if isinstance(exc, (ReferencedInputNotFound, EvalRecordNotFound, RunNotFound, ManifestNotFound,
                        ResultPersistenceNotFound, CaseResultPersistenceNotFound)):
        category = PublicErrorCategory.NOT_FOUND
    elif isinstance(exc, ReferencedInputMismatch):
        category = PublicErrorCategory.CONFLICT
    elif isinstance(exc, ReferencedInputUnavailable):
        category = PublicErrorCategory.PERSISTENCE_UNAVAILABLE
    elif isinstance(exc, (EvidenceReconciliationRequired, FinalizationRecoveryRequired)):
        category = PublicErrorCategory.RECONCILIATION_REQUIRED
    elif isinstance(exc, GovernanceSubmissionUnavailable):
        category = PublicErrorCategory.GOVERNANCE_SUBMISSION_UNAVAILABLE
    elif isinstance(exc, (EvidencePlanIncomplete, FinalizationIncomplete,
                          FinalizationScoringDecisionMissing, TerminalFailureMissing,
                          ExpectedResultMissing)):
        category = PublicErrorCategory.INCOMPLETE
    elif isinstance(exc, (EvidenceSubmissionIdempotencyConflict,
                          RunLifecycleIdempotencyConflict, ResultIdempotencyConflict,
                          CaseResultIdempotencyConflict, RunScoringIdempotencyConflict,
                          EvalIdempotencyConflict)):
        category = PublicErrorCategory.IDEMPOTENCY_CONFLICT
    elif isinstance(exc, (InvalidRunTransition, RunRevisionConflict,
                          FinalizationLifecycleConflict)):
        category = PublicErrorCategory.LIFECYCLE_CONFLICT
    elif isinstance(exc, (EvidencePersistenceUnavailable, FinalizationPersistenceUnavailable,
                          RunScoringPersistenceUnavailable, ResultPersistenceUnavailable,
                          CaseResultPersistenceUnavailable, RunLifecycleUnavailable,
                          EvalStoreUnavailable)):
        category = PublicErrorCategory.PERSISTENCE_UNAVAILABLE
    elif isinstance(exc, (EvidenceSubmissionContentConflict, PartialEvidenceRecoveryConflict,
                          FinalizationAlreadyExists, ScoringDecisionAlreadyExists,
                          ResultAlreadyExistsWithDifferentContent)):
        category = PublicErrorCategory.CONFLICT
    elif isinstance(exc, EXPECTED_BOUNDARY_ERRORS) or type(exc) is PrivateEvalDomainError:
        category = PublicErrorCategory.INVALID_REQUEST
    elif isinstance(exc, PrivateEvalInputResolutionError):
        category = PublicErrorCategory.INVALID_REQUEST
    else:
        raise exc
    return public_error(category, correlation_reference)
