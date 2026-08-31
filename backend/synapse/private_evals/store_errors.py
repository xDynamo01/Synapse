from __future__ import annotations

from typing import Any

from .errors import PrivateEvalDomainError


class EvalStoreError(PrivateEvalDomainError):
    code = "eval_store_error"
    safe_message = "Private Evals store operation failed"

    def __init__(
        self,
        _unsafe_message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(self.safe_message, details=details)


class EvalRecordNotFound(EvalStoreError):
    code = "eval_record_not_found"
    safe_message = "Private Evals record was not found"


class EvalRevisionConflict(EvalStoreError):
    code = "eval_revision_conflict"
    safe_message = "Private Evals record revision conflict"


class EvalDuplicateRecord(EvalStoreError):
    code = "eval_duplicate_record"
    safe_message = "Private Evals record already exists"


class EvalIntegrityConflict(EvalStoreError):
    code = "eval_integrity_conflict"
    safe_message = "Private Evals record integrity conflict"


class EvalIdempotencyConflict(EvalStoreError):
    code = "eval_idempotency_conflict"
    safe_message = "Private Evals idempotency conflict"


class EvalInvalidCursor(EvalStoreError):
    code = "eval_invalid_cursor"
    safe_message = "Private Evals store cursor is invalid"


class EvalInvalidStoreQuery(EvalStoreError):
    code = "eval_invalid_store_query"
    safe_message = "Private Evals store query is invalid"


class EvalStoreUnavailable(EvalStoreError):
    code = "eval_store_unavailable"
    safe_message = "Private Evals store is unavailable"


class EvalSchemaVersionMismatch(EvalStoreError):
    code = "eval_schema_version_mismatch"
    safe_message = "Private Evals store schema version is incompatible"


class EvalPersistenceConfigError(EvalStoreError):
    code = "eval_persistence_config_error"
    safe_message = "Private Evals persistence configuration is invalid"
