from __future__ import annotations


class IntelligenceBoundaryError(RuntimeError):
    code = "intelligence_boundary_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.code


class BoundaryValidationError(IntelligenceBoundaryError):
    code = "boundary_validation_failed"


class EgressDenied(IntelligenceBoundaryError):
    code = "egress_denied"


class EgressApprovalRequired(IntelligenceBoundaryError):
    code = "egress_approval_required"


class StaleEgressManifest(IntelligenceBoundaryError):
    code = "stale_egress_manifest"


class BoundaryNotFound(IntelligenceBoundaryError):
    code = "boundary_record_not_found"


class BoundaryConflict(IntelligenceBoundaryError):
    code = "boundary_conflict"
