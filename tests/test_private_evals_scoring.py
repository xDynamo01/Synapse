from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from synapse.private_evals import (
    AggregationMethod,
    ContentChecksum,
    DecisionFingerprintMismatch,
    DeterminismMode,
    DuplicateRepetition,
    EvalCaseId,
    EvalCaseVersionRef,
    EvalRunId,
    EvalSuiteId,
    EvaluatorId,
    EvaluatorIdentity,
    EvalVersion,
    FailureBudget,
    FailureBudgetUnit,
    IncompatibleConfidenceMethod,
    IncompatibleMetric,
    IncompatibleScale,
    InvalidFailureBudget,
    InvalidScoringInput,
    InvalidScoringWeight,
    ResultStatus,
    Score,
    ScoreKind,
    ScoreStatus,
    ScoreThreshold,
    ScoringEngine,
    ScoringObservation,
    ScoringProtocol,
    ScoringTarget,
    ThresholdMismatch,
    ThresholdOperator,
    ThresholdScope,
    Verdict,
)
from synapse.private_evals.errors import InvalidScore
from synapse.private_evals.scoring_errors import EvaluatorMismatch

SHA_A = ContentChecksum("a" * 64)
SHA_B = ContentChecksum("b" * 64)
RUN_ID = EvalRunId("run-scoring")
SUITE_ID = EvalSuiteId("suite-scoring")
VERSION = EvalVersion("1.0.0")
CASE_REQUIRED = EvalCaseVersionRef(SUITE_ID, EvalCaseId("case-required"), VERSION, SHA_A)
CASE_OPTIONAL = EvalCaseVersionRef(SUITE_ID, EvalCaseId("case-optional"), VERSION, SHA_B)
EVALUATOR = EvaluatorIdentity(
    EvaluatorId("evaluator-scoring"), VERSION, SHA_A, "numeric", SHA_B
)


def target(
    reference: EvalCaseVersionRef,
    *,
    weight: str,
    required: bool,
    critical: bool = False,
) -> ScoringTarget:
    return ScoringTarget(
        reference,
        "quality",
        EVALUATOR,
        Decimal(weight),
        required,
        critical,
    )


def score(
    value: str,
    *,
    target_model: ScoringTarget,
    evaluator: EvaluatorIdentity = EVALUATOR,
    scale_maximum: str = "1",
    confidence: str | None = "0.9",
) -> Score:
    raw = Decimal(value)
    maximum = Decimal(scale_maximum)
    normalized = raw / maximum
    return Score(
        "quality",
        evaluator,
        ScoreKind.NUMERIC,
        ScoreStatus.VALID,
        raw,
        Decimal("0"),
        maximum,
        normalized,
        target_model.weight,
        1,
        Decimal(confidence) if confidence is not None else None,
        None,
        "provided-bound" if confidence is not None else None,
        target_model.critical,
        target_model.required,
        None,
        SHA_A,
    )


def observation(
    target_model: ScoringTarget,
    repetition: int,
    value: str = "0.9",
    *,
    status: ResultStatus = ResultStatus.VALID,
    run_id: EvalRunId = RUN_ID,
    score_model: Score | None = None,
) -> ScoringObservation:
    scores = (
        (score_model or score(value, target_model=target_model)),
    ) if status is ResultStatus.VALID else ()
    return ScoringObservation(
        run_id,
        target_model.case_reference,
        repetition,
        status,
        scores,
    )


def protocol(
    *,
    thresholds: tuple[ScoreThreshold, ...] | None = None,
    budget: FailureBudget | None = None,
    blocked: tuple[EvalCaseVersionRef, ...] = (),
    maximum_variance: Decimal | None = None,
    required_confidence: Decimal | None = None,
) -> ScoringProtocol:
    required_target = target(CASE_REQUIRED, weight="2", required=True, critical=True)
    optional_target = target(CASE_OPTIONAL, weight="1", required=False)
    default_thresholds = (
        ScoreThreshold(
            ThresholdScope.CASE,
            ThresholdOperator.AT_LEAST,
            lower=Decimal("0.8"),
            metric_id="quality",
            case_reference=CASE_REQUIRED,
        ),
        ScoreThreshold(
            ThresholdScope.CASE,
            ThresholdOperator.AT_LEAST,
            lower=Decimal("0.75"),
            metric_id="quality",
            case_reference=CASE_OPTIONAL,
        ),
    )
    return ScoringProtocol(
        RUN_ID,
        SUITE_ID,
        VERSION,
        (required_target, optional_target),
        2,
        2,
        DeterminismMode.STOCHASTIC,
        AggregationMethod.ARITHMETIC_MEAN,
        default_thresholds if thresholds is None else thresholds,
        budget or FailureBudget(FailureBudgetUnit.COUNT, count_limit=1),
        maximum_variance,
        required_confidence,
        blocked,
    )


def valid_observations() -> tuple[ScoringObservation, ...]:
    required_target, optional_target = protocol().targets
    return (
        observation(required_target, 1, "0.8"),
        observation(required_target, 2, "1.0"),
        observation(optional_target, 1, "0.6"),
        observation(optional_target, 2, "0.8"),
    )


def test_mean_variance_weighted_mean_and_failure_budget_are_deterministic() -> None:
    decision = ScoringEngine().score(protocol(), valid_observations())
    by_case = {item.case_reference: item for item in decision.case_aggregations}
    required = by_case[CASE_REQUIRED]
    optional = by_case[CASE_OPTIONAL]
    assert required.normalized_mean == Decimal("0.900000000000")
    assert required.sample_variance == Decimal("0.020000000000")
    assert required.normalized_minimum == Decimal("0.8")
    assert required.normalized_maximum == Decimal("1.0")
    assert optional.threshold_passed is False
    assert decision.overall_normalized_score == Decimal("0.833333333333")
    assert decision.failure_budget.consumed == 1
    assert decision.failure_budget.within_budget
    assert decision.verdict is Verdict.PASSED


def test_order_is_irrelevant_and_semantic_rule_changes_fingerprint() -> None:
    engine = ScoringEngine()
    observations = valid_observations()
    first = engine.score(protocol(), observations)
    second = engine.score(
        replace(
            protocol(),
            targets=tuple(reversed(protocol().targets)),
            thresholds=tuple(reversed(protocol().thresholds)),
        ),
        tuple(reversed(observations)),
    )
    assert first == second
    decimal_equivalent = replace(
        protocol(),
        targets=tuple(
            replace(target, weight=target.weight.quantize(Decimal("0.0")))
            for target in protocol().targets
        ),
    )
    assert (
        engine.score(decimal_equivalent, observations).decision_fingerprint
        == first.decision_fingerprint
    )
    stricter = replace(
        protocol(),
        failure_budget=FailureBudget(FailureBudgetUnit.COUNT, count_limit=0),
    )
    assert engine.score(stricter, observations).decision_fingerprint != first.decision_fingerprint
    engine.validate_decision(protocol(), observations, first)
    with pytest.raises(DecisionFingerprintMismatch):
        engine.validate_decision(
            protocol(),
            observations,
            replace(first, decision_fingerprint=replace(first.decision_fingerprint, value="f" * 64)),
        )
    with pytest.raises(DecisionFingerprintMismatch):
        engine.validate_decision(
            protocol(),
            observations,
            replace(first, reason_codes=("tampered_reason",)),
        )


def test_duplicate_repetition_run_scope_metric_and_evaluator_are_rejected() -> None:
    engine = ScoringEngine()
    observations = valid_observations()
    with pytest.raises(DuplicateRepetition):
        engine.score(protocol(), observations + (observations[0],))
    with pytest.raises(InvalidScoringInput):
        engine.score(protocol(), (replace(observations[0], run_id=EvalRunId("other-run")),))
    required_target = protocol().targets[0]
    alien_metric = replace(score("0.9", target_model=required_target), metric_id="alien")
    with pytest.raises(IncompatibleMetric):
        engine.score(protocol(), (observation(required_target, 1, score_model=alien_metric),))
    other_evaluator = replace(EVALUATOR, evaluator_id=EvaluatorId("other-evaluator"))
    incompatible = score("0.9", target_model=required_target, evaluator=other_evaluator)
    with pytest.raises(EvaluatorMismatch):
        engine.score(protocol(), (observation(required_target, 1, score_model=incompatible),))


def test_missing_infrastructure_cancelled_and_optional_missing_are_not_zero_scores() -> None:
    engine = ScoringEngine()
    required_target, optional_target = protocol().targets
    missing = engine.score(
        protocol(),
        (
            observation(required_target, 1),
            observation(optional_target, 1),
            observation(optional_target, 2),
        ),
    )
    assert missing.verdict is Verdict.INCONCLUSIVE
    assert "required_repetition_missing" in missing.reason_codes
    assert missing.missing_repetition_count == 1
    infrastructure = engine.score(
        protocol(),
        (
            observation(required_target, 1, status=ResultStatus.INFRASTRUCTURE_FAILED),
            observation(required_target, 2),
            observation(optional_target, 1),
            observation(optional_target, 2),
        ),
    )
    assert infrastructure.verdict is Verdict.INCONCLUSIVE
    assert infrastructure.infrastructure_failure_count == 1
    cancelled = engine.score(
        protocol(),
        (
            observation(required_target, 1, status=ResultStatus.CANCELLED),
            observation(required_target, 2),
            observation(optional_target, 1),
            observation(optional_target, 2),
        ),
    )
    assert cancelled.verdict is Verdict.INCONCLUSIVE
    assert "execution_cancelled" in cancelled.reason_codes


def test_policy_invalid_and_blocked_precedence_are_explicit() -> None:
    required_target, optional_target = protocol().targets
    engine = ScoringEngine()
    mixed = (
        observation(required_target, 1, status=ResultStatus.INVALID),
        observation(required_target, 2),
        observation(optional_target, 1, status=ResultStatus.POLICY_DENIED),
        observation(optional_target, 2),
    )
    assert engine.score(protocol(), mixed).verdict is Verdict.INVALID
    invalid_only = tuple(
        item for item in mixed if item.result_status is not ResultStatus.POLICY_DENIED
    ) + (observation(optional_target, 1),)
    assert engine.score(protocol(), invalid_only).verdict is Verdict.INVALID
    blocked = engine.score(
        protocol(blocked=(CASE_REQUIRED,)), valid_observations()
    )
    assert blocked.verdict is Verdict.BLOCKED


def test_required_case_failure_cannot_be_compensated_by_global_mean() -> None:
    required_target, optional_target = protocol().targets
    observations = (
        observation(required_target, 1, "0.7"),
        observation(required_target, 2, "0.7"),
        observation(optional_target, 1, "1"),
        observation(optional_target, 2, "1"),
    )
    decision = ScoringEngine().score(protocol(), observations)
    assert decision.verdict is Verdict.FAILED
    assert decision.failed_required_cases == (CASE_REQUIRED,)
    assert "required_case_threshold_failed" in decision.reason_codes


def test_failure_budget_is_inclusive_and_supports_count_or_weight() -> None:
    observations = valid_observations()
    engine = ScoringEngine()
    at_limit = engine.score(
        protocol(budget=FailureBudget(FailureBudgetUnit.COUNT, count_limit=1)),
        observations,
    )
    assert at_limit.verdict is Verdict.PASSED
    above = engine.score(
        protocol(budget=FailureBudget(FailureBudgetUnit.COUNT, count_limit=0)),
        observations,
    )
    assert above.verdict is Verdict.FAILED
    weighted = engine.score(
        protocol(
            budget=FailureBudget(
                FailureBudgetUnit.WEIGHT, weight_limit=Decimal("1")
            )
        ),
        observations,
    )
    assert weighted.failure_budget.consumed == Decimal("1")
    with pytest.raises(InvalidFailureBudget):
        FailureBudget(FailureBudgetUnit.COUNT, count_limit=1, weight_limit=Decimal("1"))


def test_global_metric_and_case_thresholds_are_typed_and_inclusive() -> None:
    global_threshold = ScoreThreshold(
        ThresholdScope.GLOBAL,
        ThresholdOperator.AT_LEAST,
        lower=Decimal("0.833333333333"),
    )
    decision = ScoringEngine().score(
        protocol(thresholds=protocol().thresholds + (global_threshold,)),
        valid_observations(),
    )
    assert decision.verdict is Verdict.PASSED
    metric_threshold = ScoreThreshold(
        ThresholdScope.METRIC,
        ThresholdOperator.AT_MOST,
        upper=Decimal("0.8"),
        metric_id="quality",
    )
    assert ScoringEngine().score(
        protocol(thresholds=protocol().thresholds + (metric_threshold,)),
        valid_observations(),
    ).verdict is Verdict.FAILED
    with pytest.raises(ThresholdMismatch):
        ScoreThreshold(
            ThresholdScope.GLOBAL,
            ThresholdOperator.BETWEEN,
            lower=Decimal("0.8"),
        )


def test_scale_weight_and_required_zero_weight_are_rejected() -> None:
    required_target, optional_target = protocol().targets
    scale_ten = score(
        "9",
        target_model=required_target,
        scale_maximum="10",
    )
    observations = (
        observation(required_target, 1, "0.8"),
        observation(required_target, 2, score_model=scale_ten),
        observation(optional_target, 1),
        observation(optional_target, 2),
    )
    with pytest.raises(IncompatibleScale):
        ScoringEngine().score(protocol(), observations)
    with pytest.raises(InvalidScoringWeight):
        replace(required_target, weight=Decimal("0"))


def test_stochastic_statistics_confidence_and_variance_constraints() -> None:
    decision = ScoringEngine().score(
        protocol(
            maximum_variance=Decimal("0.01"),
            required_confidence=Decimal("0.8"),
        ),
        valid_observations(),
    )
    assert decision.verdict is Verdict.INCONCLUSIVE
    assert "insufficient_statistics" in decision.reason_codes
    assert decision.case_aggregations[0].conservative_confidence_bound == Decimal("0.9")
    assert decision.case_aggregations[0].confidence_projection_method == "conservative_minimum:provided-bound"


def test_optional_missing_is_reported_but_does_not_mask_required_success() -> None:
    required_target, _ = protocol().targets
    decision = ScoringEngine().score(
        protocol(),
        (
            observation(required_target, 1, "0.9"),
            observation(required_target, 2, "0.9"),
        ),
    )
    assert decision.missing_score_count == 2
    assert decision.verdict is Verdict.PASSED


def test_decision_and_errors_are_minimized_and_contain_no_institutional_approval() -> None:
    decision = ScoringEngine().score(protocol(), valid_observations())
    rendered = repr(decision)
    assert "output" not in rendered and "dataset" not in rendered and "prompt" not in rendered
    assert "approved" not in rendered and "promoted" not in rendered
    with pytest.raises(InvalidScoringInput) as caught:
        ScoringObservation(RUN_ID, CASE_REQUIRED, 0, ResultStatus.VALID, ())
    assert "secret" not in str(caught.value)


def test_eligibility_categories_are_exclusive_and_missing_forms_are_distinct() -> None:
    required_target, optional_target = protocol().targets
    valid_score = score("0.9", target_model=required_target)
    for status in (
        ResultStatus.INVALID,
        ResultStatus.POLICY_DENIED,
        ResultStatus.CANCELLED,
        ResultStatus.INFRASTRUCTURE_FAILED,
    ):
        with pytest.raises(InvalidScoringInput):
            ScoringObservation(
                RUN_ID,
                CASE_REQUIRED,
                1,
                status,
                (valid_score,),
            )
    missing_score = Score(
        "quality",
        EVALUATOR,
        ScoreKind.NUMERIC,
        ScoreStatus.MISSING,
        None,
        Decimal("0"),
        Decimal("1"),
        None,
        required_target.weight,
        0,
        None,
        None,
        None,
        required_target.critical,
        required_target.required,
        "score_missing",
        SHA_A,
    )
    decision = ScoringEngine().score(
        protocol(),
        (
            observation(required_target, 1, score_model=missing_score),
            observation(required_target, 2),
            observation(optional_target, 1),
            observation(optional_target, 2),
        ),
    )
    assert decision.explicit_missing_score_count == 1
    assert decision.missing_repetition_count == 0
    assert "required_score_missing" in decision.reason_codes


def test_binary_success_rate_is_explicit_and_intermediate_binary_is_rejected() -> None:
    required_target, optional_target = protocol().targets

    def binary(target_model: ScoringTarget, value: str) -> Score:
        number = Decimal(value)
        return Score(
            "quality",
            EVALUATOR,
            ScoreKind.BINARY,
            ScoreStatus.VALID,
            number,
            Decimal("0"),
            Decimal("1"),
            number,
            target_model.weight,
            1,
            None,
            None,
            None,
            target_model.critical,
            target_model.required,
            None,
            SHA_A,
        )

    observations = (
        observation(required_target, 1, score_model=binary(required_target, "1")),
        observation(required_target, 2, score_model=binary(required_target, "0")),
        observation(optional_target, 1, score_model=binary(optional_target, "1")),
        observation(optional_target, 2, score_model=binary(optional_target, "1")),
    )
    decision = ScoringEngine().score(protocol(), observations)
    by_case = {item.case_reference: item for item in decision.case_aggregations}
    assert by_case[CASE_REQUIRED].binary_success_rate == Decimal("0.500000000000")
    assert by_case[CASE_REQUIRED].score_kind is ScoreKind.BINARY
    with pytest.raises(InvalidScore):
        binary(required_target, "0.5")


def test_variance_one_sample_and_two_samples_are_unambiguous() -> None:
    required_target, optional_target = protocol().targets
    one_sample_protocol = replace(
        protocol(), expected_repetitions=1, minimum_repetitions=1
    )
    one = ScoringEngine().score(
        one_sample_protocol,
        (
            observation(required_target, 1, "0.9"),
            observation(optional_target, 1, "0.9"),
        ),
    )
    assert all(item.sample_variance is None for item in one.case_aggregations)
    two = ScoringEngine().score(protocol(), valid_observations())
    by_case = {item.case_reference: item for item in two.case_aggregations}
    assert by_case[CASE_REQUIRED].sample_variance == Decimal("0.020000000000")


def test_confidence_projection_rejects_mixed_methods_and_missing_bounds() -> None:
    required_target, optional_target = protocol().targets
    first = score("0.9", target_model=required_target)
    second = replace(first, confidence_method="different-bound")
    with pytest.raises(IncompatibleConfidenceMethod):
        ScoringEngine().score(
            protocol(),
            (
                observation(required_target, 1, score_model=first),
                observation(required_target, 2, score_model=second),
                observation(optional_target, 1),
                observation(optional_target, 2),
            ),
        )
    without_confidence = score(
        "0.9", target_model=required_target, confidence=None
    )
    decision = ScoringEngine().score(
        protocol(required_confidence=Decimal("0.8")),
        (
            observation(required_target, 1, score_model=without_confidence),
            observation(required_target, 2, score_model=without_confidence),
            observation(optional_target, 1),
            observation(optional_target, 2),
        ),
    )
    assert decision.verdict is Verdict.INCONCLUSIVE


def test_optional_infrastructure_and_cancellation_prevent_false_pass() -> None:
    required_target, optional_target = protocol().targets
    for status in (ResultStatus.INFRASTRUCTURE_FAILED, ResultStatus.CANCELLED):
        observations = (
            observation(required_target, 1),
            observation(required_target, 2),
            observation(optional_target, 1, status=status),
            observation(optional_target, 2),
        )
        assert ScoringEngine().score(protocol(), observations).verdict is Verdict.INCONCLUSIVE


def test_duplicate_thresholds_and_multiple_metrics_per_case_are_rejected() -> None:
    duplicate = protocol().thresholds[0]
    with pytest.raises(ThresholdMismatch):
        replace(protocol(), thresholds=protocol().thresholds + (duplicate,))
    second_metric = replace(protocol().targets[0], metric_id="latency")
    with pytest.raises(InvalidScoringInput):
        replace(protocol(), targets=protocol().targets + (second_metric,))


def test_fingerprint_changes_for_evaluator_confidence_and_required_semantics() -> None:
    engine = ScoringEngine()
    baseline = engine.score(protocol(), valid_observations())
    changed_evaluator = replace(EVALUATOR, version=EvalVersion("1.0.1"))
    changed_targets = tuple(
        replace(item, evaluator=changed_evaluator) for item in protocol().targets
    )
    changed_observations = tuple(
        replace(
            item,
            scores=tuple(
                replace(value, evaluator=changed_evaluator) for value in item.scores
            ),
        )
        for item in valid_observations()
    )
    evaluator_decision = engine.score(
        replace(protocol(), targets=changed_targets), changed_observations
    )
    assert evaluator_decision.decision_fingerprint != baseline.decision_fingerprint
    confidence_changed = tuple(
        replace(
            item,
            scores=tuple(
                replace(value, confidence_method="other-valid-bound")
                for value in item.scores
            ),
        )
        for item in valid_observations()
    )
    assert engine.score(protocol(), confidence_changed).decision_fingerprint != baseline.decision_fingerprint
    required_changed_targets = (
        replace(protocol().targets[0], required=False, critical=False),
        protocol().targets[1],
    )
    required_changed_observations = tuple(
        replace(
            item,
            scores=tuple(
                replace(value, required=False, critical=False)
                if item.case_reference == CASE_REQUIRED
                else value
                for value in item.scores
            ),
        )
        for item in valid_observations()
    )
    required_decision = engine.score(
        replace(protocol(), targets=required_changed_targets),
        required_changed_observations,
    )
    assert required_decision.decision_fingerprint != baseline.decision_fingerprint


def test_protocol_collections_are_strict_and_secret_like_metadata_is_rejected_safely() -> None:
    with pytest.raises(InvalidScoringInput):
        replace(protocol(), targets=list(protocol().targets))  # type: ignore[arg-type]
    required_target = protocol().targets[0]
    unsafe = replace(
        score("0.9", target_model=required_target),
        confidence_method="token=must-not-leak",
    )
    with pytest.raises(IncompatibleConfidenceMethod) as caught:
        ScoringEngine().score(
            protocol(),
            (observation(required_target, 1, score_model=unsafe),),
        )
    assert "must-not-leak" not in str(caught.value)
