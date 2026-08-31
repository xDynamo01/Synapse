from __future__ import annotations

from .errors import PrivateEvalDomainError


class CaseExecutionError(PrivateEvalDomainError):
    code = "case_execution_error"


class ExecutionRequestInvalid(CaseExecutionError):
    code = "execution_request_invalid"


class ExecutionIdentityMismatch(CaseExecutionError):
    code = "execution_identity_mismatch"


class AttemptSequenceInvalid(CaseExecutionError):
    code = "attempt_sequence_invalid"


class ExecutionResponseMismatch(CaseExecutionError):
    code = "execution_response_mismatch"


class ResponseFingerprintMismatch(CaseExecutionError):
    code = "response_fingerprint_mismatch"


class RequestIdempotencyConflict(CaseExecutionError):
    code = "request_idempotency_conflict"


class ResponseIntegrityConflict(CaseExecutionError):
    code = "response_integrity_conflict"


class OutputReferenceMissing(CaseExecutionError):
    code = "output_reference_missing"


class ExecutionProvenanceMissing(CaseExecutionError):
    code = "execution_provenance_missing"


class RetryNotAllowed(CaseExecutionError):
    code = "retry_not_allowed"


class RetryExhausted(CaseExecutionError):
    code = "retry_exhausted"


class ReauthorizationRequired(CaseExecutionError):
    code = "reauthorization_required"


class ExecutionAccountingIncomplete(CaseExecutionError):
    code = "execution_accounting_incomplete"


class ExecutionRecordInvalid(CaseExecutionError):
    code = "execution_record_invalid"
