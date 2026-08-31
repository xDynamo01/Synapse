from __future__ import annotations

from typing import Any


class ProjectGovernanceError(Exception):
    code = "project_governance_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ProjectConflict(ProjectGovernanceError):
    code = "project_conflict"


class ProjectNotFound(ProjectGovernanceError):
    code = "project_not_found"


class RFCNotFound(ProjectGovernanceError):
    code = "rfc_not_found"


class RFCInvalid(ProjectGovernanceError):
    code = "rfc_invalid"


class RFCTransitionInvalid(ProjectGovernanceError):
    code = "rfc_transition_invalid"


class RFCApprovalDenied(ProjectGovernanceError):
    code = "rfc_approval_denied"


class RFCGateBlocked(ProjectGovernanceError):
    code = "rfc_gate_blocked"


class RFCRevisionConflict(ProjectGovernanceError):
    code = "rfc_revision_conflict"


class ImplementationPlanInvalid(ProjectGovernanceError):
    code = "implementation_plan_invalid"


class EvidenceInvalid(ProjectGovernanceError):
    code = "evidence_invalid"
