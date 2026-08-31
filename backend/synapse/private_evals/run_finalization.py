from __future__ import annotations

from dataclasses import dataclass

from .canonical import fingerprint
from .case_evaluation import CaseEvaluationStatus, eval_result_checksum
from .evaluation_records import EvaluationAttemptRecord
from .execution import CaseExecutionStatus
from .execution_records import (
    ExecutionAccountingProjection,
    ExecutionAccountingStatus,
    LogicalExecutionProjection,
)
from .run_finalization_errors import (
    FinalizationIncomplete,
    FinalizationInputInvalid,
    FinalizationPathConflict,
    FinalizationReproducibilityMismatch,
    FinalizationRetryStillAvailable,
    FinalizationScoringDecisionMismatch,
    FinalizationScoringDecisionMissing,
    TerminalFailureMismatch,
    TerminalFailureMissing,
)
from .run_finalization_models import (
    EvalRunFinalizationRecord,
    RetryTerminalityKind,
    RunFinalizationCoverage,
    RunFinalizationDisposition,
    RunFinalizationPath,
    RunFinalizationReadinessStatus,
    RunFinalizationReasonCode,
    RunTerminalCause,
    TerminalFailureProjection,
    TerminalFailureStage,
    TerminalFailureStatus,
    finalization_checksum,
    finalization_fingerprint,
    finalization_slot_key,
    safe_finalization_reference,
    terminal_failure_fingerprint,
)
from .run_finalization_policy import (
    terminal_finalization_policy,
    validate_finalization_policy,
)
from .run_scoring import (
    ExpectedExecutionMatrix,
    ExpectedResultSlot,
    RunScoringDecision,
    ScoringResultReference,
    run_scoring_decision_checksum,
    scoring_result_set_fingerprint,
)
from .runs import EvalResult, EvalRun, EvalRunManifest
from .states import RunStatus
from .store_models import IdempotencyKey
from .values import EvalRunFinalizationId, Fingerprint, UtcTimestamp

EVALUATION_TERMINALITY_POLICY_REFERENCE = (
    "private-evals-evaluation-terminality:1.0.0"
)


def evaluation_terminality_policy_fingerprint() -> Fingerprint:
    return fingerprint(
        {
            "policy": EVALUATION_TERMINALITY_POLICY_REFERENCE,
            "maximum_attempts": 1,
            "retryable_statuses": (),
        }
    )


@dataclass(frozen=True)
class RunFinalizationReadiness:
    status: RunFinalizationReadinessStatus
    missing_slots: tuple[ExpectedResultSlot, ...] = ()


@dataclass(frozen=True)
class RunFinalizationInput:
    finalization_id: EvalRunFinalizationId
    run: EvalRun
    manifest: EvalRunManifest
    expected_matrix: ExpectedExecutionMatrix
    results: tuple[EvalResult, ...]
    scoring_decision: RunScoringDecision | None
    terminal_failures: tuple[TerminalFailureProjection, ...]
    execution_accounting: ExecutionAccountingProjection
    execution_projections: tuple[LogicalExecutionProjection, ...]
    evaluation_attempts: tuple[EvaluationAttemptRecord, ...]
    security_snapshot_reference: str
    security_snapshot_fingerprint: Fingerprint
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    idempotency_key: IdempotencyKey
    correlation_reference: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.finalization_id, EvalRunFinalizationId)
            or not isinstance(self.run, EvalRun)
            or not isinstance(self.manifest, EvalRunManifest)
            or not isinstance(self.expected_matrix, ExpectedExecutionMatrix)
            or not isinstance(self.execution_accounting, ExecutionAccountingProjection)
            or not isinstance(self.security_snapshot_fingerprint, Fingerprint)
            or not isinstance(self.created_at, UtcTimestamp)
            or not isinstance(self.idempotency_key, IdempotencyKey)
            or not isinstance(self.results, tuple)
            or any(not isinstance(item, EvalResult) for item in self.results)
            or not isinstance(self.terminal_failures, tuple)
            or any(
                not isinstance(item, TerminalFailureProjection)
                for item in self.terminal_failures
            )
            or not isinstance(self.execution_projections, tuple)
            or any(
                not isinstance(item, LogicalExecutionProjection)
                for item in self.execution_projections
            )
            or not isinstance(self.evaluation_attempts, tuple)
            or any(
                not isinstance(item, EvaluationAttemptRecord)
                for item in self.evaluation_attempts
            )
            or (
                self.scoring_decision is not None
                and not isinstance(self.scoring_decision, RunScoringDecision)
            )
            or not all(
                safe_finalization_reference(item)
                for item in (
                    self.security_snapshot_reference,
                    self.producer_id,
                    self.producer_version,
                    self.correlation_reference,
                )
            )
        ):
            raise FinalizationInputInvalid()
        object.__setattr__(
            self,
            "results",
            tuple(
                sorted(
                    self.results,
                    key=lambda item: finalization_slot_key(
                        ExpectedResultSlot(item.case_reference, item.repetition)
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "terminal_failures",
            tuple(
                sorted(
                    self.terminal_failures,
                    key=lambda item: finalization_slot_key(item.slot),
                )
            ),
        )

    def __repr__(self) -> str:
        return (
            "RunFinalizationInput("
            f"run_id={self.run.run_id!r}, result_count={len(self.results)!r}, "
            f"failure_count={len(self.terminal_failures)!r})"
        )


def assess_run_finalization_readiness(source: RunFinalizationInput) -> RunFinalizationReadiness:
    expected = set(source.expected_matrix.slots)
    result_slots = tuple(
        ExpectedResultSlot(item.case_reference, item.repetition) for item in source.results
    )
    failure_slots = tuple(item.slot for item in source.terminal_failures)
    if (
        len(result_slots) != len(set(result_slots))
        or len(failure_slots) != len(set(failure_slots))
        or bool(set(result_slots) - expected)
        or bool(set(failure_slots) - expected)
        or bool(set(result_slots) & set(failure_slots))
        or any(item.run_id != source.run.run_id for item in source.results)
        or any(item.run_id != source.run.run_id for item in source.terminal_failures)
    ):
        return RunFinalizationReadiness(RunFinalizationReadinessStatus.INVALID)
    missing = tuple(sorted(expected - set(result_slots), key=finalization_slot_key))
    if not missing:
        if source.terminal_failures:
            return RunFinalizationReadiness(RunFinalizationReadinessStatus.INVALID)
        if source.scoring_decision is None or not _accounting_complete(source):
            return RunFinalizationReadiness(RunFinalizationReadinessStatus.INCOMPLETE)
        return RunFinalizationReadiness(RunFinalizationReadinessStatus.READY_SCORABLE)
    if source.scoring_decision is not None:
        return RunFinalizationReadiness(RunFinalizationReadinessStatus.INVALID, missing)
    if set(missing) != set(failure_slots):
        return RunFinalizationReadiness(RunFinalizationReadinessStatus.INCOMPLETE, missing)
    if not _accounting_complete(source):
        return RunFinalizationReadiness(RunFinalizationReadinessStatus.INCOMPLETE, missing)
    return RunFinalizationReadiness(
        RunFinalizationReadinessStatus.READY_TERMINALLY_UNSCORABLE, missing
    )


def _accounting_complete(source: RunFinalizationInput) -> bool:
    summary = source.execution_accounting.summary
    return (
        source.execution_accounting.status
        is ExecutionAccountingStatus.EXECUTIONS_ACCOUNTED_FOR
        and source.execution_accounting.all_logical_executions_present
        and source.execution_accounting.no_retryable_failures
        and summary.pending == 0
        and summary.retryable == 0
        and summary.total_expected == len(source.expected_matrix.slots)
    )


class EvalRunFinalizationFactory:
    def create(self, source: RunFinalizationInput) -> EvalRunFinalizationRecord:
        self._validate_common(source)
        readiness = assess_run_finalization_readiness(source)
        if readiness.status is RunFinalizationReadinessStatus.INVALID:
            raise FinalizationPathConflict()
        if readiness.status is RunFinalizationReadinessStatus.INCOMPLETE:
            if not source.execution_accounting.no_retryable_failures:
                raise FinalizationRetryStillAvailable()
            if readiness.missing_slots and not source.terminal_failures:
                raise TerminalFailureMissing()
            if not readiness.missing_slots and source.scoring_decision is None:
                raise FinalizationScoringDecisionMissing()
            raise FinalizationIncomplete()
        references = self._result_references(source)
        result_set = scoring_result_set_fingerprint(references)
        matrix_fingerprint = source.expected_matrix.fingerprint
        assert matrix_fingerprint is not None
        if readiness.status is RunFinalizationReadinessStatus.READY_SCORABLE:
            decision = self._validate_scoring(source, references, result_set)
            path = RunFinalizationPath.SCORABLE
            decision_reference = decision.decision_fingerprint
            partial_references: tuple[ScoringResultReference, ...] = ()
            failure_set = None
            disposition = RunFinalizationDisposition.COMPLETED
            coverage = RunFinalizationCoverage.COMPLETE
            causes: tuple[RunTerminalCause, ...] = ()
            lifecycle = RunStatus.COMPLETED
            reasons: tuple[RunFinalizationReasonCode, ...] = (
                RunFinalizationReasonCode.SCORING_COMPLETED,
            )
        else:
            self._validate_failures(source)
            path = RunFinalizationPath.TERMINALLY_UNSCORABLE
            decision_reference = None
            partial_references = references
            failure_set = fingerprint(
                tuple(item.fingerprint for item in source.terminal_failures)
            )
            policy = terminal_finalization_policy(
                source.terminal_failures,
                accepted_result_count=len(references),
            )
            disposition = policy.disposition
            coverage = policy.coverage
            causes = policy.causes
            lifecycle = policy.lifecycle_status
            reasons = policy.reason_codes
        reproducibility = fingerprint(
            {
                "manifest_fingerprint": fingerprint(source.manifest),
                "expected_matrix_fingerprint": matrix_fingerprint,
                "result_set_fingerprint": result_set,
                "terminal_failure_set_fingerprint": failure_set,
                "security_snapshot_fingerprint": source.security_snapshot_fingerprint,
            }
        )
        record = EvalRunFinalizationRecord(
            source.finalization_id,
            source.run.run_id,
            fingerprint(source.manifest),
            source.manifest.suite_id,
            source.manifest.suite_version,
            path,
            decision_reference,
            result_set,
            partial_references,
            matrix_fingerprint,
            len(source.expected_matrix.slots),
            len(references),
            source.terminal_failures,
            failure_set,
            source.security_snapshot_reference,
            source.security_snapshot_fingerprint,
            reproducibility,
            disposition,
            coverage,
            causes,
            lifecycle,
            reasons,
            source.producer_id,
            source.producer_version,
            source.created_at,
        )
        validate_finalization_policy(record)
        return record

    @staticmethod
    def _result_references(
        source: RunFinalizationInput,
    ) -> tuple[ScoringResultReference, ...]:
        if any(item.checksum != eval_result_checksum(item) for item in source.results):
            raise FinalizationScoringDecisionMismatch()
        return tuple(
            ScoringResultReference(
                item.result_id,
                item.case_reference,
                item.repetition,
                item.result_fingerprint,
                item.checksum,
            )
            for item in source.results
        )

    @staticmethod
    def _validate_common(source: RunFinalizationInput) -> None:
        if (
            source.run.status
            not in {
                RunStatus.RUNNING,
                RunStatus.PARTIALLY_FAILED,
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.INVALID,
                RunStatus.POLICY_DENIED,
            }
            or source.run.manifest_id != source.manifest.manifest_id
            or source.run.suite_id != source.manifest.suite_id
            or source.run.suite_version != source.manifest.suite_version
            or source.expected_matrix.manifest_id != source.manifest.manifest_id
            or source.expected_matrix.manifest_fingerprint != fingerprint(source.manifest)
            or source.expected_matrix.suite_id != source.manifest.suite_id
            or source.expected_matrix.suite_version != source.manifest.suite_version
            or source.expected_matrix.fingerprint is None
            or source.security_snapshot_fingerprint != fingerprint(source.manifest.security)
            or source.created_at.instant < source.run.updated_at.instant
        ):
            raise FinalizationReproducibilityMismatch()

    @staticmethod
    def _validate_scoring(
        source: RunFinalizationInput,
        references: tuple[ScoringResultReference, ...],
        result_set: Fingerprint,
    ) -> RunScoringDecision:
        decision = source.scoring_decision
        assert decision is not None
        summary = source.execution_accounting.summary
        if (
            decision.checksum != run_scoring_decision_checksum(decision)
            or decision.run_id != source.run.run_id
            or decision.manifest_id != source.manifest.manifest_id
            or decision.manifest_fingerprint != fingerprint(source.manifest)
            or decision.suite_id != source.manifest.suite_id
            or decision.suite_version != source.manifest.suite_version
            or decision.expected_matrix_fingerprint != source.expected_matrix.fingerprint
            or decision.expected_result_count != len(source.expected_matrix.slots)
            or decision.result_references != references
            or decision.result_set_fingerprint != result_set
            or summary.succeeded != len(source.expected_matrix.slots)
            or any(
                (
                    summary.infrastructure_failed,
                    summary.timed_out,
                    summary.cancelled,
                    summary.policy_denied,
                    summary.invalid,
                )
            )
        ):
            raise FinalizationScoringDecisionMismatch()
        return decision

    @staticmethod
    def _validate_failures(source: RunFinalizationInput) -> None:
        execution_policy = fingerprint(source.manifest.execution)
        execution_policy_reference = (
            f"run-execution-protocol:{source.manifest.manifest_id.value}"
        )
        execution_maximum = source.manifest.execution.retry_count + 1
        expected_slots = set(source.expected_matrix.slots)
        event_attempts: dict[Fingerprint, list[EvaluationAttemptRecord]] = {}
        for attempt in source.evaluation_attempts:
            event_fingerprint = attempt.event_identity.fingerprint
            assert event_fingerprint is not None
            slot = ExpectedResultSlot(
                attempt.event_identity.case_reference,
                attempt.event_identity.repetition,
            )
            if attempt.event_identity.run_id != source.run.run_id or slot not in expected_slots:
                raise TerminalFailureMismatch()
            event_attempts.setdefault(event_fingerprint, []).append(attempt)
        if any(
            sorted(item.attempt for item in attempts)
            != list(range(1, max(item.attempt for item in attempts) + 1))
            for attempts in event_attempts.values()
        ):
            raise TerminalFailureMismatch()
        if any(
            any(item.status is CaseEvaluationStatus.SUCCEEDED for item in attempts[:-1])
            for attempts in (
                sorted(items, key=lambda item: item.attempt)
                for items in event_attempts.values()
            )
        ):
            raise TerminalFailureMismatch()
        if any(
            item.logical_execution.run_id != source.run.run_id
            or ExpectedResultSlot(
                item.logical_execution.case_reference,
                item.logical_execution.repetition,
            )
            not in expected_slots
            for item in source.execution_projections
        ):
            raise TerminalFailureMismatch()
        for failure in source.terminal_failures:
            proof = failure.retry_terminality
            if failure.stage is TerminalFailureStage.EXECUTION:
                if (
                    proof.policy_fingerprint != execution_policy
                    or proof.policy_reference != execution_policy_reference
                    or proof.maximum_attempts != execution_maximum
                    or (
                        failure.status
                        in {
                            TerminalFailureStatus.INFRASTRUCTURE_FAILED,
                            TerminalFailureStatus.TIMED_OUT,
                        }
                        and proof.kind
                        is not RetryTerminalityKind.RETRY_EXHAUSTED
                    )
                ):
                    raise TerminalFailureMismatch()
                EvalRunFinalizationFactory._validate_execution_failure(source, failure)
            else:
                if (
                    proof.policy_fingerprint
                    != evaluation_terminality_policy_fingerprint()
                    or proof.policy_reference
                    != EVALUATION_TERMINALITY_POLICY_REFERENCE
                    or proof.maximum_attempts != 1
                    or proof.kind is not RetryTerminalityKind.NON_RETRYABLE
                ):
                    raise TerminalFailureMismatch()
                EvalRunFinalizationFactory._validate_evaluation_failure(source, failure)
        EvalRunFinalizationFactory._validate_failure_accounting(source)

    @staticmethod
    def _validate_execution_failure(
        source: RunFinalizationInput, failure: TerminalFailureProjection
    ) -> None:
        projections = tuple(
            item
            for item in source.execution_projections
            if item.logical_execution.run_id == source.run.run_id
            and item.logical_execution.case_reference == failure.slot.case_reference
            and item.logical_execution.repetition == failure.slot.repetition
        )
        if len(projections) != 1 or not projections[0].attempts:
            raise TerminalFailureMismatch()
        latest = projections[0].attempts[-1]
        status = {
            CaseExecutionStatus.INFRASTRUCTURE_FAILED:
                TerminalFailureStatus.INFRASTRUCTURE_FAILED,
            CaseExecutionStatus.TIMED_OUT: TerminalFailureStatus.TIMED_OUT,
            CaseExecutionStatus.POLICY_DENIED: TerminalFailureStatus.POLICY_DENIED,
            CaseExecutionStatus.CANCELLED: TerminalFailureStatus.CANCELLED,
            CaseExecutionStatus.INVALID: TerminalFailureStatus.INVALID,
        }.get(latest.status)
        if (
            latest.attempt_identity.fingerprint != failure.final_attempt_reference
            or latest.checksum != failure.source_record_checksum
            or latest.attempt_identity.attempt != failure.retry_terminality.final_attempt
            or status is not failure.status
        ):
            raise TerminalFailureMismatch()

    @staticmethod
    def _validate_evaluation_failure(
        source: RunFinalizationInput, failure: TerminalFailureProjection
    ) -> None:
        candidates = tuple(
            item
            for item in source.evaluation_attempts
            if item.event_identity.run_id == source.run.run_id
            and item.event_identity.case_reference == failure.slot.case_reference
            and item.event_identity.repetition == failure.slot.repetition
        )
        if not candidates:
            raise TerminalFailureMismatch()
        latest = max(candidates, key=lambda item: item.attempt)
        status = {
            CaseEvaluationStatus.INFRASTRUCTURE_FAILED:
                TerminalFailureStatus.INFRASTRUCTURE_FAILED,
            CaseEvaluationStatus.TIMED_OUT: TerminalFailureStatus.TIMED_OUT,
            CaseEvaluationStatus.POLICY_DENIED: TerminalFailureStatus.POLICY_DENIED,
            CaseEvaluationStatus.CANCELLED: TerminalFailureStatus.CANCELLED,
            CaseEvaluationStatus.INVALID: TerminalFailureStatus.INVALID,
        }.get(latest.status)
        if (
            latest.fingerprint != failure.final_attempt_reference
            or latest.checksum != failure.source_record_checksum
            or latest.attempt != failure.retry_terminality.final_attempt
            or status is not failure.status
            or any(item.status is CaseEvaluationStatus.SUCCEEDED for item in candidates)
        ):
            raise TerminalFailureMismatch()

    @staticmethod
    def _validate_failure_accounting(source: RunFinalizationInput) -> None:
        summary = source.execution_accounting.summary
        execution_failures = tuple(
            item
            for item in source.terminal_failures
            if item.stage is TerminalFailureStage.EXECUTION
        )
        counts = {
            TerminalFailureStatus.INFRASTRUCTURE_FAILED: summary.infrastructure_failed,
            TerminalFailureStatus.TIMED_OUT: summary.timed_out,
            TerminalFailureStatus.CANCELLED: summary.cancelled,
            TerminalFailureStatus.POLICY_DENIED: summary.policy_denied,
            TerminalFailureStatus.INVALID: summary.invalid,
        }
        if (
            len(source.results) > summary.succeeded
            or any(
                sum(item.status is status for item in execution_failures) > count
                for status, count in counts.items()
            )
            or summary.exhausted
            != sum(
                item.retry_terminality.kind
                is RetryTerminalityKind.RETRY_EXHAUSTED
                for item in execution_failures
            )
        ):
            raise TerminalFailureMismatch()


__all__ = [
    "EvalRunFinalizationFactory",
    "EvalRunFinalizationRecord",
    "RunFinalizationInput",
    "RunFinalizationReadiness",
    "assess_run_finalization_readiness",
    "evaluation_terminality_policy_fingerprint",
    "finalization_checksum",
    "finalization_fingerprint",
    "terminal_failure_fingerprint",
]
