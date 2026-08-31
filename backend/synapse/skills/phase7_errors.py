from __future__ import annotations


class SkillInstallationError(RuntimeError):
    SAFE_MESSAGE = "skill installation operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.SAFE_MESSAGE)


class InvalidSkillInstallationRequest(SkillInstallationError):
    SAFE_MESSAGE = "skill installation request is invalid"


class SkillInstallationVersionNotPublished(SkillInstallationError):
    SAFE_MESSAGE = "skill installation version is not published"


class SkillInstallationSnapshotMismatch(SkillInstallationError):
    SAFE_MESSAGE = "skill installation snapshot does not match"


class SkillInstallationConflict(SkillInstallationError):
    SAFE_MESSAGE = "skill installation conflict"


class SkillInstallationNotFound(SkillInstallationError):
    SAFE_MESSAGE = "skill installation was not found"


class SkillInstallationTerminated(SkillInstallationError):
    SAFE_MESSAGE = "skill installation is terminated"


class SkillInstallationCorrupted(SkillInstallationError):
    SAFE_MESSAGE = "skill installation is marked unusable by integrity observation"


class IncompleteSkillInstallationHistory(SkillInstallationError):
    SAFE_MESSAGE = "skill installation history is incomplete"


class AmbiguousSkillInstallationOrdering(SkillInstallationError):
    SAFE_MESSAGE = "skill installation history ordering is ambiguous"


class ActiveSkillInstallationTerminationForbidden(SkillInstallationError):
    SAFE_MESSAGE = "active skill installation cannot be terminated"


class InvalidOperationalActivationParent(SkillInstallationError):
    SAFE_MESSAGE = "operational activation parent is invalid"


class InvalidOperationalActivationTransition(SkillInstallationError):
    SAFE_MESSAGE = "operational activation transition is invalid"


class SkillInstallationStoreUnavailable(SkillInstallationError):
    SAFE_MESSAGE = "skill installation store is unavailable"


class CorruptedSkillInstallationHistory(SkillInstallationError):
    SAFE_MESSAGE = "skill installation history is inconsistent"
