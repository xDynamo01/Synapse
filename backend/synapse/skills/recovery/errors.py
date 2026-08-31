from __future__ import annotations


class SkillsRecoveryError(RuntimeError):
    message = "skills recovery operation failed"

    def __init__(self, _unsafe_context: object = None) -> None:
        super().__init__(self.message)


class SkillsRecoveryInvalidConfiguration(SkillsRecoveryError):
    message = "skills recovery configuration is invalid"


class SkillsRecoverySourceOpen(SkillsRecoveryError):
    message = "skills recovery requires a closed composition"


class SkillsRecoverySourceUnavailable(SkillsRecoveryError):
    message = "skills recovery source is unavailable"


class SkillsRecoverySourceUnhealthy(SkillsRecoveryError):
    message = "skills recovery source is unhealthy"


class SkillsRecoveryConflict(SkillsRecoveryError):
    message = "skills recovery operation conflicts with existing state"


class SkillsRecoveryArtifactInvalid(SkillsRecoveryError):
    message = "skills recovery artifact is invalid"


class SkillsRecoveryArtifactMissing(SkillsRecoveryError):
    message = "skills recovery artifact is missing"


class SkillsRecoveryStagingFailed(SkillsRecoveryError):
    message = "skills recovery staging failed"


class SkillsRecoveryAtomicReplaceFailed(SkillsRecoveryError):
    message = "skills recovery atomic replacement failed"


class SkillsRecoveryPostRestoreFailed(SkillsRecoveryError):
    message = "skills recovery post-restore verification failed; original restored"


class SkillsRecoveryCompositionRebuildFailed(SkillsRecoveryPostRestoreFailed):
    message = "skills recovery composition rebuild failed; original restored"


class SkillsRecoveryManualInterventionRequired(SkillsRecoveryError):
    message = "skills recovery requires manual intervention"
