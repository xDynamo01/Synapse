from __future__ import annotations


class SkillDependencyAnalysisError(RuntimeError):
    SAFE_MESSAGE = "skill dependency analysis failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.SAFE_MESSAGE)


class SkillDependencySubjectNotPublished(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill dependency analysis subject is not published"


class InvalidSkillDependencyDeclaration(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill dependency declaration is invalid"


class SkillDependencyCatalogUnavailable(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill dependency catalog is unavailable"


class InconsistentSkillDependencyCatalog(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill dependency catalog result is inconsistent"


class InvalidSkillCompatibilityObservation(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill compatibility observation is invalid"


class InvalidSkillDependencyGraphInput(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill dependency graph input is invalid"


class InvalidSkillDependencyAnalysisProfile(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill dependency analysis profile is invalid"


class InconsistentSkillDependencyGraph(SkillDependencyAnalysisError):
    SAFE_MESSAGE = "skill dependency graph is inconsistent"
