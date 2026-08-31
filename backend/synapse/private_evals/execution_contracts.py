from __future__ import annotations

from typing import Protocol, runtime_checkable

from .execution import CaseExecutionRequest, CaseExecutionResponse


@runtime_checkable
class EvalCaseExecutionPort(Protocol):
    """Consumer-owned boundary; implementations resolve governed references."""

    def execute_case(self, request: CaseExecutionRequest) -> CaseExecutionResponse: ...
