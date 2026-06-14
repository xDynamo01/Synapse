from __future__ import annotations

__all__ = ["ApprovalManager", "ApprovalPolicy", "ApprovalRequest", "ApprovalResumeRuntime"]


def __getattr__(name: str):
    if name in {"ApprovalManager", "ApprovalPolicy", "ApprovalRequest"}:
        from synapse.approvals.manager import ApprovalManager, ApprovalPolicy, ApprovalRequest

        exports = {
            "ApprovalManager": ApprovalManager,
            "ApprovalPolicy": ApprovalPolicy,
            "ApprovalRequest": ApprovalRequest,
        }
        return exports[name]
    if name == "ApprovalResumeRuntime":
        from synapse.approvals.resume import ApprovalResumeRuntime

        return ApprovalResumeRuntime
    raise AttributeError(name)
