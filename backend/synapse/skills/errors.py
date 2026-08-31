from __future__ import annotations

from typing import Any

from synapse.core.exceptions import SynapseError


class SkillError(SynapseError):
    code = "skill_error"
    status_code = 400

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


def _error(name: str, code: str, status: int = 400) -> type[SkillError]:
    return type(name, (SkillError,), {"code": code, "status_code": status})


SkillNotFound = _error("SkillNotFound", "skill_not_found", 404)
SkillIdConflict = _error("SkillIdConflict", "skill_id_conflict", 409)
SkillVersionNotFound = _error("SkillVersionNotFound", "skill_version_not_found", 404)
SkillVersionConflict = _error("SkillVersionConflict", "skill_version_conflict", 409)
SkillManifestInvalid = _error("SkillManifestInvalid", "skill_manifest_invalid", 422)
SkillPackageInvalid = _error("SkillPackageInvalid", "skill_package_invalid", 422)
SkillDependencyMissing = _error("SkillDependencyMissing", "skill_dependency_missing", 409)
SkillDependencyCycle = _error("SkillDependencyCycle", "skill_dependency_cycle", 409)
SkillConflict = _error("SkillConflict", "skill_conflict", 409)
SkillIncompatible = _error("SkillIncompatible", "skill_incompatible", 409)
SkillScopeInvalid = _error("SkillScopeInvalid", "skill_scope_invalid", 422)
SkillAssignmentInvalid = _error("SkillAssignmentInvalid", "skill_assignment_invalid", 422)
SkillLeaseInvalid = _error("SkillLeaseInvalid", "skill_lease_invalid", 422)
SkillLeaseExpired = _error("SkillLeaseExpired", "skill_lease_expired", 409)
SkillResourceNotFound = _error("SkillResourceNotFound", "skill_resource_not_found", 404)
SkillResourceInvalid = _error("SkillResourceInvalid", "skill_resource_invalid", 422)
SkillScriptNotAllowed = _error("SkillScriptNotAllowed", "skill_script_not_allowed", 403)
SkillScriptFailed = _error("SkillScriptFailed", "skill_script_failed", 400)
SkillContextBudgetExceeded = _error(
    "SkillContextBudgetExceeded", "skill_context_budget_exceeded", 422
)
SkillInUse = _error("SkillInUse", "skill_in_use", 409)
SkillInstallationFailed = _error("SkillInstallationFailed", "skill_installation_failed", 422)
SkillUninstallBlocked = _error("SkillUninstallBlocked", "skill_uninstall_blocked", 409)
