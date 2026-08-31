from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

import synapse.private_evals.run_scoring as run_scoring_module
from synapse.private_evals import (
    ContentChecksum,
    DuplicateLogicalResult,
    EvalCaseId,
    EvalCaseVersionRef,
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalInvalidStoreQuery,
    EvalRecordNotFound,
    EvalResult,
    EvalResultId,
    EvalRunId,
    EvalStoreUnavailable,
    EvalVersion,
    ExpectedResultMissing,
    FailureBudget,
    FailureBudgetUnit,
    Fingerprint,
    IdempotencyKey,
    IncompatibleConfidenceMethod,
    IncompatibleScale,
    ResourceUsage,
    ResultStatus,
    RunResultCorrespondenceMismatch,
    RunResultFingerprintMismatch,
    RunScoringDecisionMismatch,
    RunScoringEligibilityStatus,
    RunScoringIdempotencyConflict,
    RunScoringInput,
    RunScoringInputInvalid,
    RunScoringObservationMismatch,
    RunScoringPersistenceUnavailable,
    RunScoringProtocolMismatch,
    RunScoringService,
    RunScoringTargetMismatch,
    ScoreKind,
    ScoreStatus,
    ScoreThreshold,
    ScoringDecisionAlreadyExists,
    ScoringDecisionFactory,
    ScoringDecisionId,
    StoreWriteOutcome,
    ThresholdOperator,
    ThresholdScope,
    UnexpectedRunResult,
    UtcTimestamp,
    Verdict,
    WriteDisposition,
    assess_run_scoring_eligibility,
    create_expected_execution_matrix,
    derive_case_verdict,
    eval_result_checksum,
    expected_execution_matrix_fingerprint,
    fingerprint,
    run_scoring_decision_checksum,
    validate_run_scoring_decision,
)
from synapse.private_evals.values import Revision
from test_private_evals_execution import manifest
from test_private_evals_scoring import (
    CASE_OPTIONAL,
    CASE_REQUIRED,
    EVALUATOR,
    RUN_ID,
    SHA_A,
    SUITE_ID,
    VERSION,
    observation,
    protocol,
    score,
    valid_observations,
)

NOW = UtcTimestamp("2026-07-19T12:00:00Z")
LATER = UtcTimestamp("2026-07-19T12:00:01Z")


def scoring_manifest(*, protocol_model=None, **changes: object):
    base = replace(
        manifest(),
        suite_id=SUITE_ID,
        suite_version=VERSION,
        case_references=(CASE_REQUIRED, CASE_OPTIONAL),
        evaluator=EVALUATOR,
    )
    if protocol_model is not None:
        base = replace(
            base,
            execution=replace(
                base.execution,
                determinism_mode=protocol_model.determinism_mode,
                repetitions=protocol_model.expected_repetitions,
                seeds=tuple(range(1, protocol_model.expected_repetitions + 1)),
            ),
        )
    return replace(base, **changes) if changes else base


def result_from_observation(item, *, index: int, protocol_model=None) -> EvalResult:
    protocol_model = protocol_model or protocol()
    result_fingerprint = fingerprint(
        {
            "run": item.run_id,
            "case": item.case_reference,
            "repetition": item.repetition,
            "scores": item.scores,
        }
    )
    threshold = next(
        (
            value
            for value in protocol_model.thresholds
            if value.scope is ThresholdScope.CASE
            and value.case_reference == item.case_reference
        ),
        None,
    )
    verdict = derive_case_verdict(item.scores, threshold)
    candidate = EvalResult(
        EvalResultId(f"result-{index}"),
        item.run_id,
        item.case_reference,
        item.repetition,
        f"execution-{index}",
        ResultStatus.VALID,
        f"output-asset-{index}",
        None,
        SHA_A,
        "private_evals:evaluated",
        item.scores,
        verdict,
        None,
        ResourceUsage(10),
        f"evaluator-artifact-{index}",
        f"evaluator-provenance-{index}",
        result_fingerprint,
        "private-evals",
        "12.0.0",
        NOW,
        ContentChecksum("0" * 64),
    )
    return replace(candidate, checksum=eval_result_checksum(candidate))


def results_from_observations(items, *, protocol_model=None) -> tuple[EvalResult, ...]:
    return tuple(
        result_from_observation(
            item,
            index=index,
            protocol_model=protocol_model,
        )
        for index, item in enumerate(items, 1)
    )


def scoring_input(
    *,
    protocol_model=None,
    results: tuple[EvalResult, ...] | None = None,
    decision_id: str = "decision-1",
    created_at: UtcTimestamp = NOW,
    **changes: object,
) -> RunScoringInput:
    protocol_model = protocol_model or protocol()
    manifest_model = scoring_manifest(protocol_model=protocol_model)
    matrix = create_expected_execution_matrix(manifest_model, protocol_model)
    source_results = (
        results_from_observations(valid_observations(), protocol_model=protocol_model)
        if results is None
        else results
    )
    return replace(
        RunScoringInput(
            RUN_ID,
            manifest_model.manifest_id,
            fingerprint(manifest_model),
            SUITE_ID,
            VERSION,
            protocol_model,
            fingerprint(protocol_model),
            matrix,
            source_results,
            ScoringDecisionId(decision_id),
            "private-evals",
            "12.0.0",
            created_at,
            IdempotencyKey("run-scoring-1"),
            "correlation-1",
        ),
        **changes,
    )


def with_result_change(result: EvalResult, **changes: object) -> EvalResult:
    changed = replace(result, **changes)
    return replace(changed, checksum=eval_result_checksum(changed))


def test_input_matrix_is_complete_frozen_deterministic_and_order_independent() -> None:
    source = scoring_input()
    matrix = source.expected_matrix
    assert len(matrix.slots) == 4
    assert matrix.fingerprint == expected_execution_matrix_fingerprint(matrix)
    assert ScoringDecisionFactory().create(source) == ScoringDecisionFactory().create(
        replace(source, results=tuple(reversed(source.results)))
    )
    with pytest.raises(FrozenInstanceError):
        source.run_id = EvalRunId("other-run")  # type: ignore[misc]


def test_eligibility_distinguishes_ready_incomplete_and_invalid() -> None:
    source = scoring_input()
    assert assess_run_scoring_eligibility(source).status is RunScoringEligibilityStatus.READY
    incomplete = replace(source, results=source.results[:-1])
    assessment = assess_run_scoring_eligibility(incomplete)
    assert assessment.status is RunScoringEligibilityStatus.INCOMPLETE
    assert len(assessment.missing_slots) == 1
    duplicate = replace(source, results=source.results + (source.results[0],))
    assert assess_run_scoring_eligibility(duplicate).status is RunScoringEligibilityStatus.INVALID


def test_missing_extra_duplicate_run_case_and_repetition_are_rejected() -> None:
    source = scoring_input()
    with pytest.raises(ExpectedResultMissing):
        ScoringDecisionFactory().create(replace(source, results=source.results[:-1]))
    with pytest.raises(DuplicateLogicalResult):
        ScoringDecisionFactory().create(
            replace(source, results=source.results + (source.results[0],))
        )
    with pytest.raises(RunResultCorrespondenceMismatch):
        changed = with_result_change(source.results[0], run_id=EvalRunId("other-run"))
        ScoringDecisionFactory().create(replace(source, results=(changed, *source.results[1:])))
    with pytest.raises(UnexpectedRunResult):
        changed = with_result_change(source.results[0], repetition=3)
        ScoringDecisionFactory().create(replace(source, results=(changed, *source.results[1:])))
    with pytest.raises(UnexpectedRunResult):
        other_case = EvalCaseVersionRef(
            SUITE_ID,
            EvalCaseId("other-case"),
            VERSION,
            SHA_A,
        )
        changed = with_result_change(source.results[0], case_reference=other_case)
        ScoringDecisionFactory().create(replace(source, results=(changed, *source.results[1:])))


def test_suite_manifest_protocol_and_matrix_correspondence_are_enforced() -> None:
    source = scoring_input()
    with pytest.raises(RunScoringProtocolMismatch):
        ScoringDecisionFactory().create(
            replace(source, manifest_fingerprint=Fingerprint("f" * 64))
        )
    with pytest.raises(RunScoringProtocolMismatch):
        ScoringDecisionFactory().create(
            replace(source, scoring_protocol_fingerprint=Fingerprint("f" * 64))
        )
    with pytest.raises(RunScoringProtocolMismatch):
        ScoringDecisionFactory().create(
            replace(source, run_id=EvalRunId("other-run"))
        )
    with pytest.raises(RunScoringProtocolMismatch):
        create_expected_execution_matrix(
            scoring_manifest(case_references=(CASE_REQUIRED,)),
            protocol(),
        )


def test_matrix_binds_manifest_repetitions_determinism_and_evaluator() -> None:
    protocol_model = protocol()
    manifest_model = scoring_manifest(protocol_model=protocol_model)
    matrix = create_expected_execution_matrix(manifest_model, protocol_model)
    assert matrix.expected_repetitions == manifest_model.execution.repetitions == 2
    assert matrix.determinism_mode is protocol_model.determinism_mode
    assert matrix.evaluator == manifest_model.evaluator

    wrong_repetitions = replace(
        manifest_model,
        execution=replace(manifest_model.execution, repetitions=3, seeds=(1, 2, 3)),
    )
    with pytest.raises(RunScoringProtocolMismatch):
        create_expected_execution_matrix(wrong_repetitions, protocol_model)

    wrong_determinism = replace(
        manifest_model,
        execution=replace(
            manifest_model.execution,
            determinism_mode=run_scoring_module.DeterminismMode.DETERMINISTIC,
        ),
    )
    with pytest.raises(RunScoringProtocolMismatch):
        create_expected_execution_matrix(wrong_determinism, protocol_model)

    wrong_evaluator = replace(EVALUATOR, version=EvalVersion("2.0.0"))
    with pytest.raises(RunScoringProtocolMismatch):
        create_expected_execution_matrix(
            replace(manifest_model, evaluator=wrong_evaluator),
            protocol_model,
        )


def test_projection_preserves_one_result_one_metric_and_protocol_authority() -> None:
    source = scoring_input()
    decision = ScoringDecisionFactory().create(source)
    assert len(decision.observation_fingerprints) == len(source.results) == 4
    targets = {target.case_reference: target for target in source.protocol.targets}
    for result in source.results:
        target = targets[result.case_reference]
        score_model = result.scores[0]
        assert score_model.evaluator == target.evaluator
        assert score_model.weight == target.weight
        assert score_model.required == target.required
        assert score_model.critical == target.critical


def test_result_integrity_target_and_observation_mismatches_are_rejected(monkeypatch) -> None:
    source = scoring_input()
    with pytest.raises(RunResultFingerprintMismatch):
        tampered = replace(source.results[0], result_fingerprint=Fingerprint("f" * 64))
        ScoringDecisionFactory().create(replace(source, results=(tampered, *source.results[1:])))
    with pytest.raises(RunScoringTargetMismatch):
        wrong_score = replace(source.results[0].scores[0], weight=Decimal("99"))
        changed = with_result_change(source.results[0], scores=(wrong_score,))
        ScoringDecisionFactory().create(replace(source, results=(changed, *source.results[1:])))

    original = run_scoring_module.project_scoring_observation

    def divergent(result):
        return replace(original(result), result_fingerprint=Fingerprint("f" * 64))

    monkeypatch.setattr(run_scoring_module, "project_scoring_observation", divergent)
    with pytest.raises(RunScoringObservationMismatch):
        ScoringDecisionFactory().create(source)


def test_case_verdict_metric_evaluator_and_producer_are_correspondence_facts() -> None:
    source = scoring_input()
    failed_result = next(result for result in source.results if result.verdict is Verdict.FAILED)
    with pytest.raises(RunResultCorrespondenceMismatch):
        changed = with_result_change(failed_result, verdict=Verdict.PASSED)
        ScoringDecisionFactory().create(
            replace(
                source,
                results=tuple(changed if item is failed_result else item for item in source.results),
            )
        )
    with pytest.raises(RunScoringTargetMismatch):
        wrong_metric = replace(source.results[0].scores[0], metric_id="other_metric")
        changed = with_result_change(source.results[0], scores=(wrong_metric,))
        ScoringDecisionFactory().create(replace(source, results=(changed, *source.results[1:])))
    with pytest.raises(RunScoringTargetMismatch):
        wrong_evaluator = replace(EVALUATOR, version=EvalVersion("2.0.0"))
        wrong_score = replace(source.results[0].scores[0], evaluator=wrong_evaluator)
        changed = with_result_change(source.results[0], scores=(wrong_score,))
        ScoringDecisionFactory().create(replace(source, results=(changed, *source.results[1:])))
    with pytest.raises(RunResultCorrespondenceMismatch):
        changed = with_result_change(source.results[0], producer_id="token=unsafe")
        ScoringDecisionFactory().create(replace(source, results=(changed, *source.results[1:])))


def test_non_measurement_result_cannot_fill_an_expected_scoring_slot() -> None:
    source = scoring_input()
    original = source.results[0]
    non_measurement = replace(
        original,
        status=ResultStatus.POLICY_DENIED,
        output_asset_id=None,
        output_checksum=None,
        scores=(),
        verdict=Verdict.POLICY_DENIED,
        error_code="policy_denied",
        evaluator_artifact_reference=None,
        provenance_reference=None,
    )
    non_measurement = replace(
        non_measurement,
        checksum=eval_result_checksum(non_measurement),
    )
    with pytest.raises(RunResultCorrespondenceMismatch):
        ScoringDecisionFactory().create(
            replace(source, results=(non_measurement, *source.results[1:]))
        )


def decision_for_observations(items, *, protocol_model=None):
    protocol_model = protocol_model or protocol()
    return ScoringDecisionFactory().create(
        scoring_input(
            protocol_model=protocol_model,
            results=results_from_observations(items, protocol_model=protocol_model),
        )
    )


def test_engine_integration_passed_failed_required_critical_and_budget() -> None:
    assert decision_for_observations(valid_observations()).verdict is Verdict.PASSED
    required, optional = protocol().targets
    required_failure = (
        observation(required, 1, "0.4"),
        observation(required, 2, "0.6"),
        observation(optional, 1, "0.9"),
        observation(optional, 2, "0.9"),
    )
    assert decision_for_observations(required_failure).verdict is Verdict.FAILED
    strict = replace(
        protocol(),
        failure_budget=FailureBudget(FailureBudgetUnit.COUNT, count_limit=0),
    )
    assert decision_for_observations(valid_observations(), protocol_model=strict).verdict is Verdict.FAILED
    weighted_ok = replace(
        protocol(),
        failure_budget=FailureBudget(FailureBudgetUnit.WEIGHT, weight_limit=Decimal("1")),
    )
    assert decision_for_observations(valid_observations(), protocol_model=weighted_ok).verdict is Verdict.PASSED
    weighted_fail = replace(
        weighted_ok,
        failure_budget=FailureBudget(FailureBudgetUnit.WEIGHT, weight_limit=Decimal("0.9")),
    )
    assert decision_for_observations(valid_observations(), protocol_model=weighted_fail).verdict is Verdict.FAILED


def test_engine_integration_threshold_directions_boundaries_and_between() -> None:
    required, optional = protocol().targets
    values = (
        observation(required, 1, "0.8"),
        observation(required, 2, "1.0"),
        observation(optional, 1, "0.8"),
        observation(optional, 2, "0.8"),
    )
    at_most = replace(
        protocol(),
        thresholds=(
            ScoreThreshold(
                ThresholdScope.CASE,
                ThresholdOperator.AT_MOST,
                upper=Decimal("0.9"),
                metric_id="quality",
                case_reference=CASE_REQUIRED,
            ),
            protocol().thresholds[1],
        ),
    )
    assert decision_for_observations(values, protocol_model=at_most).verdict is Verdict.PASSED
    between = replace(
        protocol(),
        thresholds=(
            ScoreThreshold(
                ThresholdScope.CASE,
                ThresholdOperator.BETWEEN,
                lower=Decimal("0.9"),
                upper=Decimal("0.9"),
                metric_id="quality",
                case_reference=CASE_REQUIRED,
            ),
            protocol().thresholds[1],
        ),
    )
    assert decision_for_observations(values, protocol_model=between).verdict is Verdict.PASSED


def test_engine_integration_inconclusive_invalid_blocked_repetitions_and_confidence() -> None:
    strict_confidence = replace(protocol(), required_confidence=Decimal("0.95"))
    assert decision_for_observations(
        valid_observations(), protocol_model=strict_confidence
    ).verdict is Verdict.INCONCLUSIVE
    invalid_score = replace(
        valid_observations()[0].scores[0],
        status=ScoreStatus.INVALID,
        raw_value=None,
        normalized_value=None,
        sample_count=0,
        confidence=None,
        confidence_method=None,
        reason_code="shape_invalid",
    )
    invalid_observations = (
        replace(valid_observations()[0], scores=(invalid_score,)),
        *valid_observations()[1:],
    )
    assert decision_for_observations(invalid_observations).verdict is Verdict.INVALID
    blocked = replace(protocol(), blocked_cases=(CASE_REQUIRED,))
    assert decision_for_observations(valid_observations(), protocol_model=blocked).verdict is Verdict.BLOCKED
    assert all(item.repetition in {1, 2} for item in scoring_input().expected_matrix.slots)


def test_repetition_statistics_and_incompatible_score_facts_remain_engine_owned() -> None:
    required, optional = protocol().targets
    one_protocol = replace(protocol(), expected_repetitions=1, minimum_repetitions=1)
    one = (observation(required, 1), observation(optional, 1))
    assert decision_for_observations(one, protocol_model=one_protocol).verdict is Verdict.PASSED

    three_protocol = replace(protocol(), expected_repetitions=3, minimum_repetitions=3)
    three = tuple(
        observation(target_model, repetition, "0.9")
        for target_model in (required, optional)
        for repetition in (1, 2, 3)
    )
    assert decision_for_observations(three, protocol_model=three_protocol).verdict is Verdict.PASSED

    variance_unavailable = replace(
        one_protocol,
        maximum_variance=Decimal("0.1"),
    )
    assert (
        decision_for_observations(one, protocol_model=variance_unavailable).verdict
        is Verdict.INCONCLUSIVE
    )
    variance_available = replace(three_protocol, maximum_variance=Decimal("0"))
    assert (
        decision_for_observations(three, protocol_model=variance_available).verdict
        is Verdict.PASSED
    )

    no_confidence_score = replace(
        score("0.9", target_model=required),
        confidence=None,
        confidence_method=None,
    )
    no_confidence = (
        observation(required, 1, score_model=no_confidence_score),
        observation(optional, 1),
    )
    confidence_required = replace(one_protocol, required_confidence=Decimal("0.8"))
    assert (
        decision_for_observations(no_confidence, protocol_model=confidence_required).verdict
        is Verdict.INCONCLUSIVE
    )

    mixed_method_score = replace(
        score("0.9", target_model=required),
        confidence_method="different_bound",
    )
    mixed = list(valid_observations())
    mixed[1] = observation(required, 2, score_model=mixed_method_score)
    with pytest.raises(IncompatibleConfidenceMethod):
        decision_for_observations(tuple(mixed))

    binary_score = replace(
        score("1", target_model=required),
        kind=ScoreKind.BINARY,
    )
    incompatible_kind = list(valid_observations())
    incompatible_kind[1] = observation(required, 2, score_model=binary_score)
    with pytest.raises(IncompatibleScale):
        decision_for_observations(tuple(incompatible_kind))

    missing_score = replace(
        score("0.9", target_model=required),
        status=ScoreStatus.MISSING,
        raw_value=None,
        normalized_value=None,
        sample_count=0,
        confidence=None,
        confidence_method=None,
        reason_code="measurement_missing",
    )
    explicit_missing = list(valid_observations())
    explicit_missing[0] = observation(required, 1, score_model=missing_score)
    assert decision_for_observations(tuple(explicit_missing)).verdict is Verdict.INCONCLUSIVE


def test_factory_builds_immutable_minimal_decision_and_validates_tampering() -> None:
    source = scoring_input()
    decision = ScoringDecisionFactory().create(source)
    assert decision.verdict is decision.aggregate.verdict
    assert decision.coverage == (4, 4)
    assert len(decision.result_references) == 4
    assert not hasattr(decision, "results")
    assert decision.checksum == run_scoring_decision_checksum(decision)
    validate_run_scoring_decision(source, decision)
    with pytest.raises(FrozenInstanceError):
        decision.run_id = EvalRunId("other-run")  # type: ignore[misc]
    with pytest.raises(RunScoringDecisionMismatch):
        validate_run_scoring_decision(
            source,
            replace(decision, aggregate=replace(decision.aggregate, verdict=Verdict.FAILED)),
        )
    with pytest.raises(RunScoringDecisionMismatch):
        validate_run_scoring_decision(source, replace(decision, checksum=ContentChecksum("f" * 64)))


def test_decision_id_timestamp_and_input_order_do_not_change_semantic_identity() -> None:
    first = ScoringDecisionFactory().create(scoring_input())
    source = scoring_input(decision_id="decision-2", created_at=LATER)
    second = ScoringDecisionFactory().create(
        replace(source, results=tuple(reversed(source.results)))
    )
    assert first.decision_fingerprint == second.decision_fingerprint
    assert first.checksum != second.checksum


def test_result_record_id_and_timestamp_do_not_change_semantic_decision_identity() -> None:
    source = scoring_input()
    first = ScoringDecisionFactory().create(source)
    changed_result = with_result_change(
        source.results[0],
        result_id=EvalResultId("different-record-id"),
        created_at=LATER,
    )
    second = ScoringDecisionFactory().create(
        replace(source, results=(changed_result, *source.results[1:]))
    )
    assert first.result_set_fingerprint == second.result_set_fingerprint
    assert first.decision_fingerprint == second.decision_fingerprint
    assert first.checksum != second.checksum


def test_wrapper_coverage_and_independent_integrity_fields_reject_tampering() -> None:
    source = scoring_input()
    decision = ScoringDecisionFactory().create(source)
    assert decision.coverage == (4, 4)
    with pytest.raises(RunScoringDecisionMismatch):
        replace(decision, expected_result_count=5)
    with pytest.raises(RunScoringDecisionMismatch):
        validate_run_scoring_decision(
            source,
            replace(decision, decision_fingerprint=Fingerprint("f" * 64)),
        )


class FakeAnalysisStore:
    def __init__(self) -> None:
        self.decisions: dict[EvalRunId, object] = {}
        self.save_calls = 0
        self.failure: Exception | None = None
        self.duplicate_after_store = False
        self.stale_exists = False

    def scoring_decision_exists(self, run_id: EvalRunId) -> bool:
        if self.failure is not None and not isinstance(self.failure, EvalDuplicateRecord):
            raise self.failure
        return False if self.stale_exists else run_id in self.decisions

    def get_scoring_decision_for_run(self, run_id: EvalRunId):
        if run_id not in self.decisions:
            raise EvalRecordNotFound()
        return self.decisions[run_id]

    def get_scoring_decision(self, decision_id):
        for decision in self.decisions.values():
            if decision.decision_id == decision_id:
                return decision
        raise EvalRecordNotFound()

    def save_scoring_decision(self, decision, *, idempotency_key):
        self.save_calls += 1
        if self.duplicate_after_store:
            self.decisions.setdefault(decision.run_id, decision)
            raise EvalDuplicateRecord()
        if self.failure is not None:
            raise self.failure
        if decision.run_id in self.decisions:
            existing = self.decisions[decision.run_id]
            if existing.decision_fingerprint != decision.decision_fingerprint:
                raise EvalIntegrityConflict()
            return StoreWriteOutcome(
                str(decision.decision_id),
                Revision(1),
                Revision(1),
                WriteDisposition.IDEMPOTENT_REPLAY,
                existing.checksum,
            )
        self.decisions[decision.run_id] = decision
        return StoreWriteOutcome(
            str(decision.decision_id),
            None,
            Revision(1),
            WriteDisposition.CREATED,
            decision.checksum,
        )


def test_service_creates_replays_and_never_mutates_run() -> None:
    store = FakeAnalysisStore()
    service = RunScoringService(store)  # type: ignore[arg-type]
    created = service.score_run(scoring_input())
    replay = service.score_run(scoring_input(decision_id="decision-2", created_at=LATER))
    assert created.disposition is WriteDisposition.CREATED
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    assert store.save_calls == 1
    assert not hasattr(store, "update_run") and not hasattr(store, "finalize")


def test_service_rejects_divergent_result_protocol_and_existing_verdict() -> None:
    store = FakeAnalysisStore()
    service = RunScoringService(store)  # type: ignore[arg-type]
    service.score_run(scoring_input())
    source = scoring_input()
    target_model = next(
        target
        for target in source.protocol.targets
        if target.case_reference == source.results[0].case_reference
    )
    changed_score = score("0.5", target_model=target_model)
    changed_result = with_result_change(source.results[0], scores=(changed_score,))
    with pytest.raises(ScoringDecisionAlreadyExists):
        service.score_run(replace(source, results=(changed_result, *source.results[1:])))

    changed_protocol = replace(
        source.protocol,
        required_confidence=Decimal("0.95"),
    )
    with pytest.raises(ScoringDecisionAlreadyExists):
        service.score_run(
            replace(
                source,
                protocol=changed_protocol,
                scoring_protocol_fingerprint=fingerprint(changed_protocol),
            )
        )

    existing = store.decisions[RUN_ID]
    store.decisions[RUN_ID] = replace(
        existing,
        aggregate=replace(existing.aggregate, verdict=Verdict.FAILED),
    )
    with pytest.raises(ScoringDecisionAlreadyExists):
        service.score_run(source)


def test_duplicate_race_equivalent_replays_and_divergent_conflicts() -> None:
    store = FakeAnalysisStore()
    store.duplicate_after_store = True
    result = RunScoringService(store).score_run(scoring_input())  # type: ignore[arg-type]
    assert result.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    stale_equivalent = FakeAnalysisStore()
    first = ScoringDecisionFactory().create(scoring_input())
    stale_equivalent.decisions[RUN_ID] = first
    stale_equivalent.stale_exists = True
    replay = RunScoringService(stale_equivalent).score_run(scoring_input())  # type: ignore[arg-type]
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    divergent = FakeAnalysisStore()
    divergent.decisions[RUN_ID] = replace(first, decision_fingerprint=Fingerprint("f" * 64))
    with pytest.raises(ScoringDecisionAlreadyExists):
        RunScoringService(divergent).score_run(scoring_input())  # type: ignore[arg-type]

    stale_divergent = FakeAnalysisStore()
    stale_divergent.decisions[RUN_ID] = replace(
        first,
        decision_fingerprint=Fingerprint("f" * 64),
    )
    stale_divergent.stale_exists = True
    with pytest.raises(ScoringDecisionAlreadyExists):
        RunScoringService(stale_divergent).score_run(scoring_input())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("store_error", "domain_error"),
    [
        (EvalStoreUnavailable(), RunScoringPersistenceUnavailable),
        (EvalIntegrityConflict(), ScoringDecisionAlreadyExists),
        (EvalIdempotencyConflict(), RunScoringIdempotencyConflict),
        (EvalInvalidStoreQuery(), RunScoringInputInvalid),
        (EvalRecordNotFound(), RunScoringPersistenceUnavailable),
    ],
)
def test_service_translates_store_errors(store_error: Exception, domain_error: type[Exception]) -> None:
    store = FakeAnalysisStore()
    store.failure = store_error
    with pytest.raises(domain_error):
        RunScoringService(store).score_run(scoring_input())  # type: ignore[arg-type]


def test_repr_errors_and_models_are_safe_and_finalization_boundary_is_absent() -> None:
    source = scoring_input()
    decision = ScoringDecisionFactory().create(source)
    rendered = repr(source) + repr(decision)
    forbidden = (
        "prompt",
        "provider-message",
        "dataset",
        "custody://",
        "C:\\",
        "token=",
        "output-asset-1",
    )
    assert not any(value in rendered for value in forbidden)
    with pytest.raises(RunScoringInputInvalid) as caught:
        replace(source, correlation_reference="token=must-not-leak")
    assert "must-not-leak" not in str(caught.value)
    assert not any(
        name in RunScoringService.__dict__
        for name in ("finalize", "update_run", "emit_evidence", "compare", "regress")
    )
