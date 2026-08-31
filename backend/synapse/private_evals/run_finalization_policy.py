from __future__ import annotations

from dataclasses import dataclass

from .run_finalization_errors import FinalizationReproducibilityMismatch
from .run_finalization_models import (
    EvalRunFinalizationRecord,
    RunFinalizationCoverage,
    RunFinalizationDisposition,
    RunFinalizationReasonCode,
    RunTerminalCause,
    TerminalFailureProjection,
    TerminalFailureStage,
    TerminalFailureStatus,
)
from .states import RunStatus


@dataclass(frozen=True)
class TerminalFinalizationPolicy:
    disposition: RunFinalizationDisposition
    coverage: RunFinalizationCoverage
    causes: tuple[RunTerminalCause, ...]
    lifecycle_status: RunStatus
    reason_codes: tuple[RunFinalizationReasonCode, ...]


def terminal_finalization_policy(
    failures: tuple[TerminalFailureProjection, ...],
    *,
    accepted_result_count: int,
) -> TerminalFinalizationPolicy:
    statuses = {item.status for item in failures}
    causes = tuple(
        sorted({_terminal_cause(item) for item in failures}, key=lambda item: item.value)
    )
    coverage = (
        RunFinalizationCoverage.PARTIAL
        if accepted_result_count
        else RunFinalizationCoverage.NONE
    )
    # Structural invalidity wins because no trustworthy operational conclusion exists.
    # A definitive policy denial then wins over cancellation and infrastructure causes.
    # Cancellation wins over ordinary failures but never erases the recorded cause set.
    if TerminalFailureStatus.INVALID in statuses:
        disposition = RunFinalizationDisposition.INVALID
        lifecycle = RunStatus.INVALID
    elif TerminalFailureStatus.POLICY_DENIED in statuses:
        disposition = RunFinalizationDisposition.POLICY_DENIED
        lifecycle = RunStatus.POLICY_DENIED
    elif TerminalFailureStatus.CANCELLED in statuses:
        disposition = RunFinalizationDisposition.CANCELLED
        lifecycle = RunStatus.CANCELLED
    else:
        disposition = RunFinalizationDisposition.FAILED
        lifecycle = (
            RunStatus.PARTIALLY_FAILED
            if coverage is RunFinalizationCoverage.PARTIAL
            else RunStatus.FAILED
        )
    reasons = tuple(
        sorted({item.reason_code for item in failures}, key=lambda item: item.value)
    )
    return TerminalFinalizationPolicy(
        disposition, coverage, causes, lifecycle, reasons
    )


def _terminal_cause(item: TerminalFailureProjection) -> RunTerminalCause:
    if item.status is TerminalFailureStatus.INVALID:
        return RunTerminalCause.INVALID_RESPONSE
    if item.status is TerminalFailureStatus.POLICY_DENIED:
        return RunTerminalCause.POLICY_DENIAL
    if item.status is TerminalFailureStatus.CANCELLED:
        return RunTerminalCause.CANCELLATION
    if item.stage is TerminalFailureStage.EVALUATION:
        return RunTerminalCause.EVALUATION_FAILURE
    return RunTerminalCause.EXECUTION_FAILURE


def validate_finalization_policy(record: EvalRunFinalizationRecord) -> None:
    if not record.terminal_failures:
        if (
            record.disposition is not RunFinalizationDisposition.COMPLETED
            or record.coverage is not RunFinalizationCoverage.COMPLETE
            or record.terminal_causes
            or record.lifecycle_status is not RunStatus.COMPLETED
            or record.reason_codes
            != (RunFinalizationReasonCode.SCORING_COMPLETED,)
        ):
            raise FinalizationReproducibilityMismatch()
        return
    expected = terminal_finalization_policy(
        record.terminal_failures,
        accepted_result_count=record.accepted_result_count,
    )
    if (
        record.disposition is not expected.disposition
        or record.coverage is not expected.coverage
        or record.terminal_causes != expected.causes
        or record.lifecycle_status is not expected.lifecycle_status
        or record.reason_codes != expected.reason_codes
    ):
        raise FinalizationReproducibilityMismatch()
