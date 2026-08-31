from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from synapse.private_evals import (
    EVALUATION_TERMINALITY_POLICY_REFERENCE,
    CaseEvaluationReasonCode,
    CaseEvaluationStatus,
    CaseExecutionStatus,
    ContentChecksum,
    EvalRun,
    EvalRunFinalizationFactory,
    EvalRunFinalizationId,
    EvalRunFinalizationService,
    EvalRunRuntime,
    EvaluationAttemptRecord,
    EvaluationCorrespondenceMismatch,
    EvaluationEventIdentity,
    ExecutionAccountingProjection,
    ExecutionAccountingStatus,
    FinalizationAlreadyExists,
    FinalizationLifecycleConflict,
    FinalizationPathConflict,
    FinalizationPersistenceUnavailable,
    FinalizationRecoveryRequired,
    FinalizationReproducibilityMismatch,
    FinalizationScoringDecisionMismatch,
    FinalizationWriteDisposition,
    Fingerprint,
    IdempotencyKey,
    InvalidRunTransition,
    LogicalExecutionIdentity,
    PartialFailureSummary,
    ResourceUsage,
    RetryTerminalityKind,
    RetryTerminalityProof,
    Revision,
    RunFinalizationCoverage,
    RunFinalizationDisposition,
    RunFinalizationInput,
    RunFinalizationPath,
    RunFinalizationReadinessStatus,
    RunFinalizationReasonCode,
    RunStatus,
    RunTerminalCause,
    ScoringDecisionFactory,
    StoreWriteOutcome,
    TerminalFailureMismatch,
    TerminalFailureProjection,
    TerminalFailureStage,
    TerminalFailureStatus,
    UtcTimestamp,
    Verdict,
    WriteDisposition,
    assess_run_finalization_readiness,
    evaluation_attempt_checksum,
    evaluation_attempt_record,
    evaluation_terminality_policy_fingerprint,
    fingerprint,
    logical_execution_projection,
    run_scoring_decision_checksum,
    terminal_finalization_policy,
)
from synapse.private_evals.store_errors import EvalRevisionConflict, EvalStoreUnavailable
from test_private_evals_case_evaluation import evaluation_request, evaluation_response
from test_private_evals_execution import record as execution_record
from test_private_evals_execution import request as execution_request
from test_private_evals_run_scoring import LATER, scoring_input, scoring_manifest


def accounting(
    *,
    total: int,
    succeeded: int,
    infrastructure_failed: int = 0,
    timed_out: int = 0,
    cancelled: int = 0,
    policy_denied: int = 0,
    invalid: int = 0,
    pending: int = 0,
    retryable: int = 0,
    exhausted: int = 0,
) -> ExecutionAccountingProjection:
    complete = pending == 0 and retryable == 0
    return ExecutionAccountingProjection(
        ExecutionAccountingStatus.EXECUTIONS_ACCOUNTED_FOR
        if complete
        else ExecutionAccountingStatus.INCOMPLETE,
        pending == 0,
        retryable == 0,
        PartialFailureSummary(
            total,
            succeeded,
            infrastructure_failed,
            timed_out,
            cancelled,
            policy_denied,
            invalid,
            pending,
            retryable,
            exhausted,
        ),
    )


def finalization_input(**changes: object) -> RunFinalizationInput:
    scoring = scoring_input()
    manifest = scoring_manifest(protocol_model=scoring.protocol)
    decision = ScoringDecisionFactory().create(scoring)
    run = EvalRun(
        scoring.run_id,
        scoring.suite_id,
        scoring.suite_version,
        RunStatus.RUNNING,
        Revision(4),
        scoring.created_at,
        scoring.created_at,
        manifest.manifest_id,
    )
    source = RunFinalizationInput(
        EvalRunFinalizationId("finalization-1"),
        run,
        manifest,
        scoring.expected_matrix,
        scoring.results,
        decision,
        (),
        accounting(total=4, succeeded=4),
        (),
        (),
        "security-snapshot-1",
        fingerprint(manifest.security),
        "private-evals",
        "13.1.0",
        LATER,
        IdempotencyKey("run-finalization-1"),
        "correlation-1",
    )
    return replace(source, **changes)


def _reason(
    stage: TerminalFailureStage, status: TerminalFailureStatus
) -> RunFinalizationReasonCode:
    if status is TerminalFailureStatus.POLICY_DENIED:
        return RunFinalizationReasonCode.POLICY_DENIED
    if status is TerminalFailureStatus.CANCELLED:
        return RunFinalizationReasonCode.CANCELLED
    if status is TerminalFailureStatus.INVALID:
        return RunFinalizationReasonCode.INVALID
    return {
        (TerminalFailureStage.EXECUTION, TerminalFailureStatus.INFRASTRUCTURE_FAILED):
            RunFinalizationReasonCode.EXECUTION_FAILED,
        (TerminalFailureStage.EXECUTION, TerminalFailureStatus.TIMED_OUT):
            RunFinalizationReasonCode.EXECUTION_TIMED_OUT,
        (TerminalFailureStage.EVALUATION, TerminalFailureStatus.INFRASTRUCTURE_FAILED):
            RunFinalizationReasonCode.EVALUATION_FAILED,
        (TerminalFailureStage.EVALUATION, TerminalFailureStatus.TIMED_OUT):
            RunFinalizationReasonCode.EVALUATION_TIMED_OUT,
    }[(stage, status)]


def _execution_status(status: TerminalFailureStatus) -> CaseExecutionStatus:
    return CaseExecutionStatus(status.value)


def _evaluation_status(status: TerminalFailureStatus) -> CaseEvaluationStatus:
    return CaseEvaluationStatus(status.value)


def _evaluation_reason(status: CaseEvaluationStatus) -> CaseEvaluationReasonCode:
    return {
        CaseEvaluationStatus.INFRASTRUCTURE_FAILED:
            CaseEvaluationReasonCode.INFRASTRUCTURE_UNAVAILABLE,
        CaseEvaluationStatus.TIMED_OUT: CaseEvaluationReasonCode.EVALUATION_TIMEOUT,
        CaseEvaluationStatus.CANCELLED: CaseEvaluationReasonCode.CANCELLED_BY_REQUEST,
        CaseEvaluationStatus.POLICY_DENIED:
            CaseEvaluationReasonCode.POLICY_NOT_AUTHORIZED,
        CaseEvaluationStatus.INVALID: CaseEvaluationReasonCode.RESPONSE_INVALID,
    }[status]


def terminal_input(
    specifications: tuple[
        tuple[TerminalFailureStage, TerminalFailureStatus, RetryTerminalityKind], ...
    ] = (
        (
            TerminalFailureStage.EXECUTION,
            TerminalFailureStatus.INFRASTRUCTURE_FAILED,
            RetryTerminalityKind.RETRY_EXHAUSTED,
        ),
    ),
    **changes: object,
) -> RunFinalizationInput:
    base = finalization_input()
    missing = base.expected_matrix.slots[-len(specifications):]
    missing_set = set(missing)
    results = tuple(
        item
        for item in base.results
        if base.expected_matrix.slots[
            next(
                index
                for index, slot in enumerate(base.expected_matrix.slots)
                if slot.case_reference == item.case_reference
                and slot.repetition == item.repetition
            )
        ]
        not in missing_set
    )
    failures: list[TerminalFailureProjection] = []
    execution_projections = []
    evaluation_attempts: list[EvaluationAttemptRecord] = []
    execution_statuses: list[TerminalFailureStatus] = []
    for slot, (stage, status, kind) in zip(missing, specifications, strict=True):
        if stage is TerminalFailureStage.EXECUTION:
            maximum = base.manifest.execution.retry_count + 1
            policy_reference = (
                f"run-execution-protocol:{base.manifest.manifest_id.value}"
            )
            policy_fingerprint = fingerprint(base.manifest.execution)
        else:
            maximum = 1
            policy_reference = EVALUATION_TERMINALITY_POLICY_REFERENCE
            policy_fingerprint = evaluation_terminality_policy_fingerprint()
        attempt_number = maximum if kind is RetryTerminalityKind.RETRY_EXHAUSTED else 1
        proof = RetryTerminalityProof(
            kind,
            status,
            policy_reference,
            policy_fingerprint,
            maximum,
            attempt_number,
        )
        if stage is TerminalFailureStage.EXECUTION:
            logical = LogicalExecutionIdentity(
                base.run.run_id, slot.case_reference, slot.repetition
            )
            attempts = tuple(
                execution_record(
                    _execution_status(status),
                    target=execution_request(
                        number, logical_execution=logical
                    ),
                )
                for number in range(1, attempt_number + 1)
            )
            projection = logical_execution_projection(logical, attempts)
            execution_projections.append(projection)
            latest = attempts[-1]
            attempt_reference = latest.attempt_identity.fingerprint
            source_checksum = latest.checksum
            execution_statuses.append(status)
        else:
            event = EvaluationEventIdentity(
                base.run.run_id,
                slot.case_reference,
                slot.repetition,
                fingerprint(("output", slot)),
                base.manifest.evaluator,
                fingerprint(("protocol", base.manifest.protocol_fingerprint)),
            )
            attempts = tuple(
                EvaluationAttemptRecord(
                    event,
                    number,
                    fingerprint(("request", slot, number)),
                    fingerprint(("response", slot, number)),
                    _evaluation_status(status),
                    base.run.updated_at,
                    base.created_at,
                    _evaluation_reason(_evaluation_status(status)),
                    None,
                    None,
                    ResourceUsage(1),
                )
                for number in range(1, attempt_number + 1)
            )
            evaluation_attempts.extend(attempts)
            latest = attempts[-1]
            attempt_reference = latest.fingerprint
            source_checksum = latest.checksum
        assert attempt_reference is not None and source_checksum is not None
        failures.append(
            TerminalFailureProjection(
                base.run.run_id,
                slot,
                stage,
                status,
                attempt_reference,
                source_checksum,
                proof,
                _reason(stage, status),
                "terminal-failure-provenance-1",
            )
        )
    counts = {status: execution_statuses.count(status) for status in TerminalFailureStatus}
    execution_failed_count = len(execution_statuses)
    source = replace(
        base,
        results=results,
        scoring_decision=None,
        terminal_failures=tuple(failures),
        execution_projections=tuple(execution_projections),
        evaluation_attempts=tuple(evaluation_attempts),
        execution_accounting=accounting(
            total=len(base.expected_matrix.slots),
            succeeded=len(base.expected_matrix.slots) - execution_failed_count,
            infrastructure_failed=counts[TerminalFailureStatus.INFRASTRUCTURE_FAILED],
            timed_out=counts[TerminalFailureStatus.TIMED_OUT],
            cancelled=counts[TerminalFailureStatus.CANCELLED],
            policy_denied=counts[TerminalFailureStatus.POLICY_DENIED],
            invalid=counts[TerminalFailureStatus.INVALID],
            exhausted=sum(
                specification[0] is TerminalFailureStage.EXECUTION
                and specification[2] is RetryTerminalityKind.RETRY_EXHAUSTED
                for specification in specifications
            ),
        ),
    )
    return replace(source, **changes)


def test_readiness_separates_paths_and_rejects_every_ambiguous_gap() -> None:
    scorable = finalization_input()
    terminal = terminal_input()
    assert (
        assess_run_finalization_readiness(scorable).status
        is RunFinalizationReadinessStatus.READY_SCORABLE
    )
    assert (
        assess_run_finalization_readiness(terminal).status
        is RunFinalizationReadinessStatus.READY_TERMINALLY_UNSCORABLE
    )
    missing = replace(scorable, results=scorable.results[:-1], scoring_decision=None)
    assert (
        assess_run_finalization_readiness(missing).status
        is RunFinalizationReadinessStatus.INCOMPLETE
    )
    assert (
        assess_run_finalization_readiness(
            replace(terminal, results=scorable.results)
        ).status
        is RunFinalizationReadinessStatus.INVALID
    )
    assert (
        assess_run_finalization_readiness(
            replace(terminal, terminal_failures=terminal.terminal_failures * 2)
        ).status
        is RunFinalizationReadinessStatus.INVALID
    )


def test_evaluation_attempt_is_historical_fact_without_retry_policy_state() -> None:
    request = evaluation_request()
    succeeded = evaluation_attempt_record(request, evaluation_response(request), attempt=1)
    failed = evaluation_attempt_record(
        request,
        evaluation_response(request, status=CaseEvaluationStatus.INFRASTRUCTURE_FAILED),
        attempt=1,
    )
    assert succeeded.checksum == evaluation_attempt_checksum(succeeded)
    assert failed.evaluator_artifact_reference is None
    assert not hasattr(failed, "retry_disposition")
    assert "evaluation-provenance-1" not in repr(succeeded)
    with pytest.raises(EvaluationCorrespondenceMismatch):
        replace(failed, checksum=ContentChecksum("f" * 64))


def test_retry_terminality_is_separate_policy_bound_and_verifiable() -> None:
    source = terminal_input()
    proof = source.terminal_failures[0].retry_terminality
    assert proof.policy_fingerprint == fingerprint(source.manifest.execution)
    assert proof.final_attempt == proof.maximum_attempts
    with pytest.raises(TerminalFailureMismatch):
        replace(proof, final_attempt=proof.final_attempt - 1)
    bad = replace(
        proof,
        policy_fingerprint=Fingerprint("f" * 64),
        fingerprint=None,
    )
    failure = replace(source.terminal_failures[0], retry_terminality=bad, fingerprint=None)
    with pytest.raises(TerminalFailureMismatch):
        EvalRunFinalizationFactory().create(
            replace(source, terminal_failures=(failure,))
        )


@pytest.mark.parametrize(
    "status,expected",
    [
        (TerminalFailureStatus.INFRASTRUCTURE_FAILED, RunFinalizationDisposition.FAILED),
        (TerminalFailureStatus.TIMED_OUT, RunFinalizationDisposition.FAILED),
        (TerminalFailureStatus.POLICY_DENIED, RunFinalizationDisposition.POLICY_DENIED),
        (TerminalFailureStatus.CANCELLED, RunFinalizationDisposition.CANCELLED),
        (TerminalFailureStatus.INVALID, RunFinalizationDisposition.INVALID),
    ],
)
def test_terminal_disposition_is_distinct_from_coverage_and_cause(
    status: TerminalFailureStatus, expected: RunFinalizationDisposition
) -> None:
    kind = (
        RetryTerminalityKind.NON_RETRYABLE
        if status
        in {
            TerminalFailureStatus.POLICY_DENIED,
            TerminalFailureStatus.CANCELLED,
            TerminalFailureStatus.INVALID,
        }
        else RetryTerminalityKind.RETRY_EXHAUSTED
    )
    source = terminal_input(((TerminalFailureStage.EXECUTION, status, kind),))
    record = EvalRunFinalizationFactory().create(source)
    assert record.disposition is expected
    assert record.coverage is RunFinalizationCoverage.PARTIAL
    assert record.lifecycle_status is (
        RunStatus.PARTIALLY_FAILED
        if expected is RunFinalizationDisposition.FAILED
        else RunStatus(expected.value)
    )


@pytest.mark.parametrize(
    "specifications,expected",
    [
        (
            (
                (TerminalFailureStage.EXECUTION, TerminalFailureStatus.INFRASTRUCTURE_FAILED, RetryTerminalityKind.RETRY_EXHAUSTED),
                (TerminalFailureStage.EVALUATION, TerminalFailureStatus.TIMED_OUT, RetryTerminalityKind.NON_RETRYABLE),
            ),
            RunFinalizationDisposition.FAILED,
        ),
        (
            (
                (TerminalFailureStage.EXECUTION, TerminalFailureStatus.INFRASTRUCTURE_FAILED, RetryTerminalityKind.RETRY_EXHAUSTED),
                (TerminalFailureStage.EVALUATION, TerminalFailureStatus.CANCELLED, RetryTerminalityKind.NON_RETRYABLE),
            ),
            RunFinalizationDisposition.CANCELLED,
        ),
        (
            (
                (TerminalFailureStage.EXECUTION, TerminalFailureStatus.TIMED_OUT, RetryTerminalityKind.RETRY_EXHAUSTED),
                (TerminalFailureStage.EVALUATION, TerminalFailureStatus.POLICY_DENIED, RetryTerminalityKind.NON_RETRYABLE),
            ),
            RunFinalizationDisposition.POLICY_DENIED,
        ),
        (
            (
                (TerminalFailureStage.EXECUTION, TerminalFailureStatus.INVALID, RetryTerminalityKind.NON_RETRYABLE),
                (TerminalFailureStage.EVALUATION, TerminalFailureStatus.POLICY_DENIED, RetryTerminalityKind.NON_RETRYABLE),
            ),
            RunFinalizationDisposition.INVALID,
        ),
    ],
)
def test_mixed_terminal_precedence_preserves_all_causes(
    specifications, expected: RunFinalizationDisposition
) -> None:
    record = EvalRunFinalizationFactory().create(terminal_input(specifications))
    assert record.disposition is expected
    assert len(record.terminal_causes) == 2


def test_scorable_finalization_is_completed_independently_of_engine_verdict() -> None:
    record = EvalRunFinalizationFactory().create(finalization_input())
    assert record.path is RunFinalizationPath.SCORABLE
    assert record.disposition is RunFinalizationDisposition.COMPLETED
    assert record.coverage is RunFinalizationCoverage.COMPLETE
    assert record.lifecycle_status is RunStatus.COMPLETED
    assert not hasattr(record, "scoring_verdict")
    assert record.scoring_decision_reference is not None
    assert record.partial_result_references == ()


@pytest.mark.parametrize("verdict", tuple(Verdict))
def test_every_persisted_scoring_verdict_maps_to_completed_lifecycle(
    verdict: Verdict,
) -> None:
    source = finalization_input()
    decision = source.scoring_decision
    assert decision is not None
    changed = replace(decision, aggregate=replace(decision.aggregate, verdict=verdict))
    changed = replace(changed, checksum=run_scoring_decision_checksum(changed))
    record = EvalRunFinalizationFactory().create(
        replace(source, scoring_decision=changed)
    )
    assert changed.verdict is verdict
    assert record.disposition is RunFinalizationDisposition.COMPLETED
    assert record.lifecycle_status is RunStatus.COMPLETED


def test_partial_results_are_references_and_not_a_disposition() -> None:
    record = EvalRunFinalizationFactory().create(terminal_input())
    assert record.path is RunFinalizationPath.TERMINALLY_UNSCORABLE
    assert record.disposition is RunFinalizationDisposition.FAILED
    assert record.coverage is RunFinalizationCoverage.PARTIAL
    assert record.terminal_causes == (RunTerminalCause.EXECUTION_FAILURE,)
    assert record.lifecycle_status is RunStatus.PARTIALLY_FAILED
    assert len(record.partial_result_references) == 3


def test_no_results_is_failed_with_none_coverage_not_partial_lifecycle() -> None:
    specifications = tuple(
        (
            TerminalFailureStage.EXECUTION,
            TerminalFailureStatus.INFRASTRUCTURE_FAILED,
            RetryTerminalityKind.RETRY_EXHAUSTED,
        )
        for _ in range(4)
    )
    record = EvalRunFinalizationFactory().create(terminal_input(specifications))
    assert record.accepted_result_count == 0
    assert record.coverage is RunFinalizationCoverage.NONE
    assert record.disposition is RunFinalizationDisposition.FAILED
    assert record.lifecycle_status is RunStatus.FAILED


def test_evaluation_attempt_sequence_and_success_before_failure_are_rejected() -> None:
    source = terminal_input(
        ((TerminalFailureStage.EVALUATION, TerminalFailureStatus.TIMED_OUT, RetryTerminalityKind.NON_RETRYABLE),)
    )
    attempts = source.evaluation_attempts
    skipped = replace(attempts[0], attempt=3, fingerprint=None, checksum=None)
    with pytest.raises(TerminalFailureMismatch):
        EvalRunFinalizationFactory().create(
            replace(source, evaluation_attempts=(attempts[0], skipped))
        )
    successful = replace(
        attempts[0],
        status=CaseEvaluationStatus.SUCCEEDED,
        reason_code=CaseEvaluationReasonCode.COMPLETED,
        evaluator_artifact_reference="evaluation-artifact-1",
        provenance_reference="evaluation-provenance-1",
        fingerprint=None,
        checksum=None,
    )
    second = replace(attempts[0], attempt=2, fingerprint=None, checksum=None)
    with pytest.raises(TerminalFailureMismatch):
        EvalRunFinalizationFactory().create(
            replace(source, evaluation_attempts=(successful, second))
        )


def test_identity_separates_semantics_reproducibility_and_record_integrity() -> None:
    factory = EvalRunFinalizationFactory()
    source = finalization_input()
    first = factory.create(source)
    reordered = factory.create(replace(source, results=tuple(reversed(source.results))))
    changed_record = factory.create(
        replace(
            source,
            finalization_id=EvalRunFinalizationId("finalization-2"),
            created_at=UtcTimestamp("2026-07-19T12:00:02Z"),
        )
    )
    assert reordered.fingerprint == first.fingerprint
    assert changed_record.fingerprint == first.fingerprint
    assert changed_record.checksum != first.checksum
    assert changed_record.reproducibility_fingerprint == first.reproducibility_fingerprint
    with pytest.raises(FinalizationReproducibilityMismatch):
        replace(first, checksum=ContentChecksum("f" * 64))
    with pytest.raises(FinalizationReproducibilityMismatch):
        replace(first, fingerprint=Fingerprint("f" * 64))
    with pytest.raises(FrozenInstanceError):
        first.path = RunFinalizationPath.TERMINALLY_UNSCORABLE  # type: ignore[misc]


def test_factory_rejects_decision_result_matrix_and_path_mismatch() -> None:
    source = finalization_input()
    bad_decision = replace(
        source.scoring_decision,
        expected_matrix_fingerprint=Fingerprint("d" * 64),
    )
    with pytest.raises(FinalizationScoringDecisionMismatch):
        EvalRunFinalizationFactory().create(
            replace(source, scoring_decision=bad_decision)
        )
    terminal = terminal_input()
    with pytest.raises(FinalizationPathConflict):
        EvalRunFinalizationFactory().create(
            replace(terminal, scoring_decision=source.scoring_decision)
        )


class RunStoreFake:
    def __init__(self, run: EvalRun):
        self.run = run
        self.finalization = None
        self.unavailable = False
        self.cas_conflict = False
        self.after_save_run: EvalRun | None = None
        self.race_finalization = None

    def get_run(self, _run_id):
        return self.run

    def update_run(self, run, *, expected_revision, idempotency_key):
        if self.cas_conflict:
            raise EvalRevisionConflict("conflict")
        if expected_revision != self.run.revision:
            raise EvalRevisionConflict("stale")
        previous = self.run.revision
        self.run = run
        return StoreWriteOutcome(
            "run-1",
            previous,
            run.revision,
            WriteDisposition.UPDATED,
            ContentChecksum("e" * 64),
        )

    def finalization_exists(self, _run_id):
        if self.unavailable:
            raise EvalStoreUnavailable("unavailable")
        return self.finalization is not None

    def get_finalization_for_run(self, _run_id):
        if self.unavailable:
            raise EvalStoreUnavailable("unavailable")
        return self.finalization

    def save_finalization(self, record, *, idempotency_key):
        if self.unavailable:
            raise EvalStoreUnavailable("unavailable")
        self.finalization = self.race_finalization or record
        if self.after_save_run is not None:
            self.run = self.after_save_run
        assert record.checksum is not None
        return StoreWriteOutcome(
            record.record_reference,
            None,
            Revision(1),
            WriteDisposition.IDEMPOTENT_REPLAY
            if self.race_finalization is not None
            else WriteDisposition.CREATED,
            record.checksum,
        )


def service(source: RunFinalizationInput):
    store = RunStoreFake(source.run)
    runtime = EvalRunRuntime(store, object())  # type: ignore[arg-type]
    return store, EvalRunFinalizationService(store, runtime)  # type: ignore[arg-type]


def test_service_first_create_replay_and_saved_record_recovery() -> None:
    source = finalization_input()
    store, runtime_service = service(source)
    first = runtime_service.finalize(source)
    assert first.disposition is FinalizationWriteDisposition.CREATED
    assert store.run.status is RunStatus.COMPLETED
    replay = runtime_service.finalize(replace(source, run=store.run))
    assert replay.disposition is FinalizationWriteDisposition.IDEMPOTENT_REPLAY

    recovery_store, recovery_service = service(source)
    recovery_store.finalization = EvalRunFinalizationFactory().create(source)
    recovered = recovery_service.finalize(source)
    assert recovered.disposition is FinalizationWriteDisposition.RECOVERED
    assert recovery_store.run.status is RunStatus.COMPLETED


def test_concurrent_create_only_equivalent_recovers_and_divergent_conflicts() -> None:
    source = finalization_input()
    candidate = EvalRunFinalizationFactory().create(source)
    store, runtime_service = service(source)
    store.race_finalization = candidate
    result = runtime_service.finalize(source)
    assert result.disposition is FinalizationWriteDisposition.RECOVERED
    assert store.run.status is RunStatus.COMPLETED

    store, runtime_service = service(source)
    store.race_finalization = EvalRunFinalizationFactory().create(
        replace(source, producer_version="13.1.1")
    )
    with pytest.raises(FinalizationAlreadyExists):
        runtime_service.finalize(source)


def test_service_rejects_stale_divergent_corrupt_and_terminal_conflicts() -> None:
    source = finalization_input()
    store, runtime_service = service(source)
    store.run = replace(source.run, revision=Revision(5))
    with pytest.raises(FinalizationLifecycleConflict):
        runtime_service.finalize(source)
    assert store.finalization is None

    store, runtime_service = service(source)
    store.finalization = EvalRunFinalizationFactory().create(
        replace(source, producer_version="13.1.1")
    )
    with pytest.raises(FinalizationAlreadyExists):
        runtime_service.finalize(source)

    store, runtime_service = service(source)
    corrupt = EvalRunFinalizationFactory().create(source)
    object.__setattr__(corrupt, "checksum", ContentChecksum("f" * 64))
    store.finalization = corrupt
    with pytest.raises(FinalizationReproducibilityMismatch):
        runtime_service.finalize(source)

    store, runtime_service = service(source)
    other = replace(
        source.run,
        status=RunStatus.CANCELLED,
        revision=Revision(5),
        finalization_reference="cancellation:other",
    )
    store.run = other
    with pytest.raises(FinalizationLifecycleConflict):
        runtime_service.finalize(replace(source, run=other))


def test_cas_conflict_after_save_requires_recovery_and_concurrent_cancel_is_explicit() -> None:
    source = finalization_input()
    store, runtime_service = service(source)
    store.cas_conflict = True
    with pytest.raises(FinalizationRecoveryRequired):
        runtime_service.finalize(source)
    assert store.finalization is not None and store.run.status is RunStatus.RUNNING

    store, runtime_service = service(source)
    store.after_save_run = replace(
        source.run,
        status=RunStatus.CANCELLED,
        revision=Revision(5),
        finalization_reference="cancellation:concurrent",
    )
    with pytest.raises(FinalizationLifecycleConflict):
        runtime_service.finalize(source)
    assert store.finalization is not None


def test_store_unavailable_and_terminal_without_reference_require_intervention() -> None:
    source = finalization_input()
    store, runtime_service = service(source)
    store.unavailable = True
    with pytest.raises(FinalizationPersistenceUnavailable) as caught:
        runtime_service.finalize(source)
    assert str(caught.value) == "Run finalization persistence is unavailable"

    store, runtime_service = service(source)
    terminal = replace(
        source.run,
        status=RunStatus.COMPLETED,
        revision=Revision(5),
        finalization_reference="temporary:valid",
    )
    object.__setattr__(terminal, "finalization_reference", None)
    store.run = terminal
    with pytest.raises(FinalizationRecoveryRequired):
        runtime_service.finalize(replace(source, run=terminal))


def test_apply_finalization_binds_run_and_fingerprint_and_is_idempotent() -> None:
    source = finalization_input()
    record = EvalRunFinalizationFactory().create(source)
    store, runtime_service = service(source)
    assert record.fingerprint is not None
    with pytest.raises(InvalidRunTransition):
        runtime_service.runtime.apply_finalization(
            source.run.run_id,
            RunStatus.COMPLETED,
            record.record_reference.replace(source.run.run_id.value, "other-run"),
            record.fingerprint,
            accepted_result_count=4,
            failed_execution_count=0,
            timestamp=source.created_at,
            expected_revision=source.run.revision,
            idempotency_key=source.idempotency_key,
        )
    with pytest.raises(InvalidRunTransition):
        runtime_service.runtime.apply_finalization(
            source.run.run_id,
            RunStatus.COMPLETED,
            record.record_reference,
            Fingerprint("f" * 64),
            accepted_result_count=4,
            failed_execution_count=0,
            timestamp=source.created_at,
            expected_revision=source.run.revision,
            idempotency_key=source.idempotency_key,
        )
    result = runtime_service.finalize(source)
    replay = runtime_service.runtime.apply_finalization(
        source.run.run_id,
        RunStatus.COMPLETED,
        result.finalization.record_reference,
        result.finalization.fingerprint,  # type: ignore[arg-type]
        accepted_result_count=4,
        failed_execution_count=0,
        timestamp=source.created_at,
        expected_revision=store.run.revision,
        idempotency_key=source.idempotency_key,
    )
    assert replay == store.run


def test_policy_precedence_is_documented_and_deterministic() -> None:
    source = terminal_input(
        (
            (TerminalFailureStage.EXECUTION, TerminalFailureStatus.INVALID, RetryTerminalityKind.NON_RETRYABLE),
            (TerminalFailureStage.EVALUATION, TerminalFailureStatus.POLICY_DENIED, RetryTerminalityKind.NON_RETRYABLE),
        )
    )
    policy = terminal_finalization_policy(
        source.terminal_failures, accepted_result_count=len(source.results)
    )
    assert policy.disposition is RunFinalizationDisposition.INVALID
    assert policy.causes == (
        RunTerminalCause.INVALID_RESPONSE,
        RunTerminalCause.POLICY_DENIAL,
    )


def test_repr_and_errors_do_not_expose_sensitive_values() -> None:
    source = terminal_input()
    record = EvalRunFinalizationFactory().create(source)
    representation = repr(record) + repr(source) + repr(source.terminal_failures[0])
    for forbidden in ("prompt", "payload", "provider message", "token=", "C:\\"):
        assert forbidden not in representation
