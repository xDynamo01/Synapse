"""Closed, orthogonal Sandbox lifecycle states."""

from enum import StrEnum


class SandboxCleanupState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class SandboxRollbackState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    COMPLETED = "completed"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"
