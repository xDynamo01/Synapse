from __future__ import annotations

from typing import Any

from .errors import PrivateEvalDomainError


class EvalRunLifecycleError(PrivateEvalDomainError):
    code = "eval_run_lifecycle_error"
    safe_message = "Private Evals run lifecycle operation failed"

    def __init__(
        self,
        _unsafe_message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(self.safe_message, details=details)


class RunNotFound(EvalRunLifecycleError):
    code = "eval_run_not_found"
    safe_message = "Eval run was not found"


class RunAlreadyExists(EvalRunLifecycleError):
    code = "eval_run_already_exists"
    safe_message = "Eval run already exists with incompatible content"


class ManifestAlreadyExists(EvalRunLifecycleError):
    code = "eval_manifest_already_exists"
    safe_message = "Eval run manifest already exists with incompatible content"


class ManifestNotFound(EvalRunLifecycleError):
    code = "eval_manifest_not_found"
    safe_message = "Eval run manifest was not found"


class ManifestMismatch(EvalRunLifecycleError):
    code = "eval_manifest_mismatch"
    safe_message = "Eval run manifest is inconsistent"


class UnresolvedRunReference(EvalRunLifecycleError):
    code = "eval_run_unresolved_reference"
    safe_message = "Eval run reference cannot be resolved"


class InvalidRunTransition(EvalRunLifecycleError):
    code = "eval_run_invalid_transition"
    safe_message = "Eval run transition is not allowed"


class TerminalRunMutation(EvalRunLifecycleError):
    code = "eval_run_terminal_mutation"
    safe_message = "Terminal eval run is immutable"


class RunRevisionConflict(EvalRunLifecycleError):
    code = "eval_run_revision_conflict"
    safe_message = "Eval run revision conflict"


class RunNotReady(EvalRunLifecycleError):
    code = "eval_run_not_ready"
    safe_message = "Eval run is not ready"


class RunCancellationNotAllowed(EvalRunLifecycleError):
    code = "eval_run_cancellation_not_allowed"
    safe_message = "Eval run cancellation is not allowed"


class RunCompletionNotAllowed(EvalRunLifecycleError):
    code = "eval_run_completion_not_allowed"
    safe_message = "Eval run completion requires execution evidence"


class RunLifecycleIdempotencyConflict(EvalRunLifecycleError):
    code = "eval_run_lifecycle_idempotency_conflict"
    safe_message = "Eval run lifecycle idempotency conflict"


class RunLifecycleIntegrityConflict(EvalRunLifecycleError):
    code = "eval_run_lifecycle_integrity_conflict"
    safe_message = "Eval run lifecycle integrity conflict"


class RunLifecycleQueryInvalid(EvalRunLifecycleError):
    code = "eval_run_lifecycle_query_invalid"
    safe_message = "Eval run lifecycle query is invalid"


class RunLifecycleUnavailable(EvalRunLifecycleError):
    code = "eval_run_lifecycle_unavailable"
    safe_message = "Eval run lifecycle store is unavailable"
