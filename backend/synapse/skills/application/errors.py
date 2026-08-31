from __future__ import annotations


class SkillApplicationError(RuntimeError):
    message = "skill application operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.message)


class SkillApplicationInvalidInput(SkillApplicationError):
    message = "skill application input is invalid"


class SkillApplicationNotFound(SkillApplicationError):
    message = "skill application resource was not found"


class SkillApplicationConflict(SkillApplicationError):
    message = "skill application operation conflicts with current facts"


class SkillApplicationDependencyUnavailable(SkillApplicationError):
    message = "skill application dependency is unavailable"


class SkillApplicationIncomplete(SkillApplicationError):
    message = "skill application facts are incomplete"
