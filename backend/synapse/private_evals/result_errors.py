from __future__ import annotations

from .errors import PrivateEvalDomainError


class OutputMaterializationError(PrivateEvalDomainError):
    code = "output_materialization_error"
    safe_message = "Execution output materialization failed"

    def __init__(self, _unsafe_message: str | None = None) -> None:
        super().__init__(self.safe_message)


class ResultMaterializationInvalid(OutputMaterializationError):
    code = "result_materialization_invalid"
    safe_message = "Eval result materialization input is invalid"


class ExecutionNotSuccessful(OutputMaterializationError):
    code = "execution_not_successful"
    safe_message = "Execution is not eligible for result materialization"


class ResultCorrespondenceMismatch(OutputMaterializationError):
    code = "result_correspondence_mismatch"
    safe_message = "Eval result correspondence is inconsistent"


class ResultFingerprintMismatch(OutputMaterializationError):
    code = "result_fingerprint_mismatch"
    safe_message = "Eval result fingerprint is inconsistent"


class ResultAlreadyExistsWithDifferentContent(OutputMaterializationError):
    code = "result_already_exists_with_different_content"
    safe_message = "Logical eval result already exists with different content"


class ResultIdempotencyConflict(OutputMaterializationError):
    code = "result_idempotency_conflict"
    safe_message = "Eval result idempotency conflict"


class ResultPersistenceUnavailable(OutputMaterializationError):
    code = "result_persistence_unavailable"
    safe_message = "Eval result persistence is unavailable"


class ResultPersistenceInvalid(OutputMaterializationError):
    code = "result_persistence_invalid"
    safe_message = "Eval result persistence request is invalid"


class ResultPersistenceNotFound(OutputMaterializationError):
    code = "result_persistence_not_found"
    safe_message = "Persisted eval result was not found"
