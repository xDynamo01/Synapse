from __future__ import annotations

from ..evidence_submission_errors import (
    EvidenceReconciliationRequired as AmbiguousExternalWrite,
)
from ..evidence_submission_errors import GovernanceSubmissionUnavailable

__all__ = ["AmbiguousExternalWrite", "GovernanceSubmissionUnavailable"]


class PrivateEvalAdapterError(Exception):
    code = "private_eval_adapter_error"
    safe_message = "Private Evals external boundary failed"

    def __init__(self, _unsafe_message: str | None = None) -> None:
        super().__init__(self.safe_message)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r})"


class SecuritySnapshotUnavailable(PrivateEvalAdapterError):
    code = "security_snapshot_unavailable"
    safe_message = "Security decision snapshot is unavailable"


class SecuritySnapshotMismatch(PrivateEvalAdapterError):
    code = "security_snapshot_mismatch"
    safe_message = "Security decision snapshot is inconsistent"


class AdapterExecutionUnavailable(PrivateEvalAdapterError):
    code = "execution_unavailable"
    safe_message = "Case execution boundary is unavailable"


class AdapterExecutionResponseInvalid(PrivateEvalAdapterError):
    code = "execution_response_invalid"
    safe_message = "Case execution response is invalid"


class AdapterEvaluatorUnavailable(PrivateEvalAdapterError):
    code = "evaluator_unavailable"
    safe_message = "Case evaluator boundary is unavailable"


class AdapterEvaluatorResponseInvalid(PrivateEvalAdapterError):
    code = "evaluator_response_invalid"
    safe_message = "Case evaluator response is invalid"
