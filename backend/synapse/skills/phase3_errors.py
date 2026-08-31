from __future__ import annotations


class SkillStoreError(RuntimeError):
    """Base error for Phase 2 persistence contracts."""

    SAFE_MESSAGE = "skill store operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.SAFE_MESSAGE)


class InvalidSkillStoreRecord(SkillStoreError):
    """A typed record violates its structural invariants."""

    SAFE_MESSAGE = "skill store record is invalid"


class SkillStoreNotFound(SkillStoreError):
    """An exact requested record does not exist."""

    SAFE_MESSAGE = "skill store record was not found"


class SkillStoreSemanticConflict(SkillStoreError):
    """Stored facts conflict semantically."""

    SAFE_MESSAGE = "skill store semantic conflict"


class SkillStoreDivergentDuplicate(SkillStoreSemanticConflict):
    """A semantic identity already exists with different content."""

    SAFE_MESSAGE = "skill store divergent duplicate"


class SkillStoreInvalidParentReference(SkillStoreError):
    """A record references a missing or mismatched local parent."""

    SAFE_MESSAGE = "skill store parent reference is invalid"


class SkillStoreUnavailable(SkillStoreError):
    """The persistence boundary is temporarily unavailable."""

    SAFE_MESSAGE = "skill store is unavailable"
