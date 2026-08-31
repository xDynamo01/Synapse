from __future__ import annotations

from synapse.core.exceptions import SynapseError


class AgentLoopError(SynapseError):
    code = "agent_loop_error"
    status_code = 400

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class ApprovalRequired(AgentLoopError):
    code = "approval_required"
    status_code = 409


class ActionNotSupported(AgentLoopError):
    code = "action_not_supported"
    status_code = 422


class ActionExecutionFailed(AgentLoopError):
    code = "action_execution_failed"
    status_code = 502


class ActionVerificationFailed(AgentLoopError):
    code = "action_verification_failed"
    status_code = 502


class LoopInvalidState(AgentLoopError):
    code = "loop_invalid_state"
    status_code = 409


class LoopLockActive(AgentLoopError):
    code = "loop_lock_active"
    status_code = 409


class LoopCycleFailed(AgentLoopError):
    code = "loop_cycle_failed"
    status_code = 500


class NotificationFailed(AgentLoopError):
    code = "notification_failed"
    status_code = 502


class MemoryCommitFailed(AgentLoopError):
    code = "memory_commit_failed"
    status_code = 502
