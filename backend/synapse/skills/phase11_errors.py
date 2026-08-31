from __future__ import annotations


class SkillPrivateEvalBindingError(RuntimeError):
    SAFE_MESSAGE = "skill private eval binding operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.SAFE_MESSAGE)


class InvalidSkillPrivateEvalReference(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval reference is invalid"


class InvalidSkillPrivateEvalBindingRequest(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding request is invalid"


class InvalidSkillPrivateEvalGranularity(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding granularity is invalid"


class InvalidSkillPrivateEvalTemporalRelation(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding time relation is invalid"


class SkillPrivateEvalBindingSubjectNotPublished(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding subject is not published"


class SkillPrivateEvalBindingCorrespondenceMismatch(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding correspondence is invalid"


class SkillPrivateEvalBindingDivergentDuplicate(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding duplicate is divergent"


class IncompleteSkillPrivateEvalBindingHistory(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding history is incomplete"


class InvalidSkillPrivateEvalBindingHistory(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding history is invalid"


class SkillPrivateEvalBindingStoreUnavailable(SkillPrivateEvalBindingError):
    SAFE_MESSAGE = "skill private eval binding store is unavailable"
