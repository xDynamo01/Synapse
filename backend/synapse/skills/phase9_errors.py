from __future__ import annotations


class SkillDependencyResolutionError(RuntimeError):
    SAFE_MESSAGE = "skill dependency resolution failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.SAFE_MESSAGE)


class InvalidSkillDependencyResolutionRequest(SkillDependencyResolutionError):
    SAFE_MESSAGE = "skill dependency resolution request is invalid"


class InvalidSkillDependencyResolutionPolicy(SkillDependencyResolutionError):
    SAFE_MESSAGE = "skill dependency resolution policy is invalid"


class InconsistentSkillDependencyAnalysis(SkillDependencyResolutionError):
    SAFE_MESSAGE = "skill dependency analysis is inconsistent"


class InconsistentSkillResolutionGraph(SkillDependencyResolutionError):
    SAFE_MESSAGE = "skill dependency resolution graph is inconsistent"


class SkillDependencyResolutionInvariantError(SkillDependencyResolutionError):
    SAFE_MESSAGE = "skill dependency resolution invariant failed"
