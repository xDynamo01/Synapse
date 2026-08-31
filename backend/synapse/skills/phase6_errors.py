from __future__ import annotations


class SkillLifecycleError(RuntimeError):
    """Base application error for published-version lifecycle operations."""

    SAFE_MESSAGE = "skill lifecycle operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.SAFE_MESSAGE)


class SkillVersionNotPublished(SkillLifecycleError):
    SAFE_MESSAGE = "skill version is not published"


class InvalidSkillLifecycleRequest(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle request is invalid"


class InvalidSkillLifecycleTransition(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle transition is invalid"


class SkillLifecycleConflict(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle conflict"


class MissingLifecycleDecisionReference(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle decision reference is required"


class RevokedSkillVersion(SkillLifecycleError):
    SAFE_MESSAGE = "skill version is revoked"


class InvalidSkillSupersessionTarget(SkillLifecycleError):
    SAFE_MESSAGE = "skill supersession target is invalid"


class InvalidSkillRollbackTarget(SkillLifecycleError):
    SAFE_MESSAGE = "skill rollback target is invalid"


class InvalidSkillActivationParent(SkillLifecycleError):
    SAFE_MESSAGE = "skill activation parent is invalid"


class SkillLifecycleStoreUnavailable(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle store is unavailable"


class CorruptedSkillLifecycleHistory(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle history is inconsistent"


class IncompleteSkillLifecycleHistory(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle history is incomplete"


class AmbiguousSkillLifecycleOrdering(SkillLifecycleError):
    SAFE_MESSAGE = "skill lifecycle history ordering is ambiguous"
