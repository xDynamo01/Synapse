from __future__ import annotations

from typing import Any

from .errors import PrivateEvalDomainError


class EvalCatalogError(PrivateEvalDomainError):
    code = "eval_catalog_error"
    safe_message = "Private Evals catalog operation failed"

    def __init__(
        self,
        _unsafe_message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(self.safe_message, details=details)


class SuiteNotFound(EvalCatalogError):
    code = "eval_catalog_suite_not_found"
    safe_message = "Eval suite was not found"


class SuiteAlreadyExists(EvalCatalogError):
    code = "eval_catalog_suite_already_exists"
    safe_message = "Eval suite already exists with incompatible content"


class SuiteRevisionConflict(EvalCatalogError):
    code = "eval_catalog_suite_revision_conflict"
    safe_message = "Eval suite revision conflict"


class SuiteVersionNotFound(EvalCatalogError):
    code = "eval_catalog_suite_version_not_found"
    safe_message = "Eval suite version was not found"


class SuiteVersionAlreadyExists(EvalCatalogError):
    code = "eval_catalog_suite_version_already_exists"
    safe_message = "Eval suite version already exists with incompatible content"


class SuiteVersionRevisionConflict(EvalCatalogError):
    code = "eval_catalog_suite_version_revision_conflict"
    safe_message = "Eval suite version revision conflict"


class InvalidSuiteTransition(EvalCatalogError):
    code = "eval_catalog_invalid_suite_transition"
    safe_message = "Eval suite transition is not allowed"


class ImmutableSuiteVersion(EvalCatalogError):
    code = "eval_catalog_immutable_suite_version"
    safe_message = "Frozen eval suite version is immutable"


class CaseVersionNotFound(EvalCatalogError):
    code = "eval_catalog_case_version_not_found"
    safe_message = "Eval case version was not found"


class CaseVersionAlreadyExists(EvalCatalogError):
    code = "eval_catalog_case_version_already_exists"
    safe_message = "Eval case version already exists with incompatible content"


class CaseVersionRevisionConflict(EvalCatalogError):
    code = "eval_catalog_case_version_revision_conflict"
    safe_message = "Eval case version revision conflict"


class InvalidCaseTransition(EvalCatalogError):
    code = "eval_catalog_invalid_case_transition"
    safe_message = "Eval case version transition is not allowed"


class UnresolvedCaseReference(EvalCatalogError):
    code = "eval_catalog_unresolved_case_reference"
    safe_message = "Eval case reference cannot be resolved"


class IncompatibleCaseReference(EvalCatalogError):
    code = "eval_catalog_incompatible_case_reference"
    safe_message = "Eval case reference is incompatible"


class DatasetBindingNotFound(EvalCatalogError):
    code = "eval_catalog_dataset_binding_not_found"
    safe_message = "Eval dataset binding was not found"


class DatasetBindingAlreadyExists(EvalCatalogError):
    code = "eval_catalog_dataset_binding_already_exists"
    safe_message = "Eval dataset binding already exists with incompatible content"


class IncompatibleDatasetBinding(EvalCatalogError):
    code = "eval_catalog_incompatible_dataset_binding"
    safe_message = "Eval dataset binding is incompatible"


class CatalogIdempotencyConflict(EvalCatalogError):
    code = "eval_catalog_idempotency_conflict"
    safe_message = "Eval catalog idempotency conflict"


class CatalogIntegrityConflict(EvalCatalogError):
    code = "eval_catalog_integrity_conflict"
    safe_message = "Eval catalog integrity conflict"


class CatalogQueryInvalid(EvalCatalogError):
    code = "eval_catalog_query_invalid"
    safe_message = "Eval catalog query is invalid"


class CatalogUnavailable(EvalCatalogError):
    code = "eval_catalog_unavailable"
    safe_message = "Eval catalog is unavailable"
