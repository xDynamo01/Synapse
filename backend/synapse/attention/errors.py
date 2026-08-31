from __future__ import annotations

from synapse.core.exceptions import NotFound, SynapseError


class AttentionError:
    code = "attention_error"
    status_code = 400

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class AttentionNotFound(NotFound, AttentionError):
    code = "attention_not_found"
    status_code = 404


class AttentionExpired(SynapseError, AttentionError):
    code = "attention_expired"
    status_code = 410


class AttentionSuppressed(SynapseError, AttentionError):
    code = "attention_suppressed"
    status_code = 409


class DecisionDenied(SynapseError, AttentionError):
    code = "decision_denied"
    status_code = 403


class DecisionExpired(SynapseError, AttentionError):
    code = "decision_expired"
    status_code = 410


class AutonomyExceeded(SynapseError, AttentionError):
    code = "autonomy_exceeded"
    status_code = 403
