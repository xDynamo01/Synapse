from __future__ import annotations


class SkillExternalBindingError(RuntimeError):
    SAFE_MESSAGE = "skill external binding operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.SAFE_MESSAGE)


class InvalidSkillExternalReference(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external reference is invalid"


class InvalidSkillExternalBindingRequest(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external binding request is invalid"


class SkillExternalBindingSubjectNotPublished(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external binding subject is not published"


class SkillExternalBindingCorrespondenceMismatch(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external binding correspondence is invalid"


class SkillExternalBindingDivergentDuplicate(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external binding duplicate is divergent"


class IncompleteSkillExternalBindingHistory(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external binding history is incomplete"


class InvalidSkillExternalBindingHistory(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external binding history is invalid"


class SkillExternalBindingStoreUnavailable(SkillExternalBindingError):
    SAFE_MESSAGE = "skill external binding store is unavailable"
