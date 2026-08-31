from synapse.core.exceptions import ValidationError


class ContextBridgeFailed(ValidationError):
    code = "context_bridge_failed"
    status_code = 500

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "details": {}}


class ContextBudgetExceeded(ValidationError):
    code = "context_budget_exceeded"
    status_code = 422


class ContextSourceUnavailable(ContextBridgeFailed):
    code = "context_source_unavailable"
