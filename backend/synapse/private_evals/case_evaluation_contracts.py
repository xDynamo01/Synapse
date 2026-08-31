from __future__ import annotations

from typing import Protocol, runtime_checkable

from .case_evaluation import CaseEvaluationRequest, CaseEvaluationResponse


@runtime_checkable
class EvalCaseEvaluatorPort(Protocol):
    """Consumer-owned boundary for one external evaluator invocation."""

    async def evaluate(self, request: CaseEvaluationRequest) -> CaseEvaluationResponse: ...
