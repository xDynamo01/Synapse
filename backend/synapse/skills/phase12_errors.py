from __future__ import annotations


class SkillExecutionHandoffError(RuntimeError):
    """Safe Slice 12 error; supplied facts are deliberately not rendered."""

    message = "skill execution handoff is invalid"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.message)


class InvalidSkillExecutionHandoffRequest(SkillExecutionHandoffError):
    message = "skill execution handoff request is invalid"


class InvalidSkillExecutionHandoffPolicy(SkillExecutionHandoffError):
    message = "skill execution handoff policy is invalid"


class SkillExecutionHandoffCorrespondenceError(SkillExecutionHandoffError):
    message = "skill execution handoff correspondence is invalid"


class InvalidSkillExecutionInstallationFact(SkillExecutionHandoffError):
    message = "skill execution installation fact is invalid"


class InvalidSkillExecutionLifecycleFact(SkillExecutionHandoffError):
    message = "skill execution lifecycle fact is invalid"


class InvalidSkillExecutionResolutionFact(SkillExecutionHandoffError):
    message = "skill execution resolution fact is invalid"


class InvalidSkillExecutionBindingReference(SkillExecutionHandoffError):
    message = "skill execution binding reference is invalid"


class CorruptSkillExecutionInputProjection(SkillExecutionHandoffError):
    message = "skill execution input projection is corrupt"


class SkillExecutionHandoffLimitExceeded(SkillExecutionHandoffError):
    message = "skill execution handoff limit was exceeded"


class SkillExecutionHandoffInvariantError(SkillExecutionHandoffError):
    message = "skill execution handoff invariant failed"
