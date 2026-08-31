from __future__ import annotations


class SkillLegacyCompatibilityError(RuntimeError):
    message = "legacy skill compatibility operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.message)


class SkillLegacyCompatibilityIncomplete(SkillLegacyCompatibilityError):
    message = "legacy skill compatibility facts are incomplete"


class SkillLegacyCompatibilityInvalidMapping(SkillLegacyCompatibilityError):
    message = "legacy skill mapping is invalid"


class SkillLegacyCompatibilityNotFound(SkillLegacyCompatibilityError):
    message = "legacy skill was not found"


class SkillLegacyCompatibilityUnavailable(SkillLegacyCompatibilityError):
    message = "legacy skill compatibility dependency is unavailable"


class SkillLegacyCompatibilityConflict(SkillLegacyCompatibilityError):
    message = "legacy skill compatibility operation conflicts with current facts"
