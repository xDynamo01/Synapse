from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from synapse.private_evals import (
    BaselineEligibilityPolicy,
    BaselineFactory,
    BaselineFingerprintMismatch,
    BaselineId,
    BaselineStatus,
    ComparisonEngine,
    ComparisonId,
    ComparisonInput,
    ComparisonResult,
    ComparisonScope,
    CompatibilityDimension,
    CompatibilityEvaluator,
    CompatibilityPolicy,
    CompatibilityReasonCode,
    CompatibilityStatus,
    ContentChecksum,
    DatasetBindingId,
    DefinitionStatus,
    DeltaDirection,
    DeterminismMode,
    EvalRunId,
    EvalRunManifest,
    EvalRunManifestBuilder,
    ExecutionProtocol,
    Fingerprint,
    IncompatibleComparison,
    InvalidBaselineSource,
    MetricDelta,
    MetricDirection,
    MetricDirectionMissing,
    MetricDirectionSpec,
    MetricThreshold,
    RegressionDetector,
    RegressionEvaluationFailure,
    RegressionReportId,
    RegressionRule,
    RegressionRuleId,
    ScoringDecision,
    ScoringEngine,
    ScoringObservation,
    ScoringProtocol,
    UtcTimestamp,
    Verdict,
)
from synapse.private_evals.errors import DuplicateReference, InvalidRegressionRule
from test_private_evals_run_runtime import manifest_spec
from test_private_evals_scoring import EVALUATOR, observation, protocol

NOW = UtcTimestamp("2026-07-18T12:00:00Z")
LATER = UtcTimestamp("2026-07-18T13:00:00Z")
FINALIZATION = ContentChecksum("f" * 64)


def bundle(
    run: str,
    values: tuple[str, str, str, str] = ("0.8", "1.0", "0.8", "0.8"),
    *,
    source: str = "c",
) -> tuple[EvalRunManifest, ScoringProtocol, ScoringDecision]:
    run_id = EvalRunId(run)
    scoring_protocol = replace(protocol(), run_id=run_id)
    required, optional = scoring_protocol.targets
    observations: tuple[ScoringObservation, ...] = (
        observation(required, 1, values[0], run_id=run_id),
        observation(required, 2, values[1], run_id=run_id),
        observation(optional, 1, values[2], run_id=run_id),
        observation(optional, 2, values[3], run_id=run_id),
    )
    decision = ScoringEngine().score(scoring_protocol, observations)
    spec, _ = manifest_spec()
    spec = replace(
        spec,
        manifest_id=replace(spec.manifest_id, value=f"manifest-{run}"),
        suite_id=scoring_protocol.suite_id,
        suite_version=scoring_protocol.suite_version,
        case_references=tuple(target.case_reference for target in scoring_protocol.targets),
        evaluator=EVALUATOR,
        source_fingerprint=Fingerprint(source * 64),
        execution=ExecutionProtocol(
            DeterminismMode.STOCHASTIC,
            2,
            1,
            0,
            Decimal("60"),
            Decimal("30"),
            (11, 12),
            "arithmetic_mean",
        ),
    )
    return EvalRunManifestBuilder().build(spec), scoring_protocol, decision


def candidate(
    *,
    created_at: UtcTimestamp = NOW,
    policy_dimensions: tuple[CompatibilityDimension, ...] | None = (
        CompatibilityDimension.SOURCE_FINGERPRINT,
    ),
):
    manifest, scoring_protocol, decision = bundle("run-baseline")
    scope = ComparisonScope(
        scoring_protocol.suite_id,
        scoring_protocol.suite_version,
        "default",
        (
            tuple(
                item.value
                for item in (policy_dimensions or ())
                if item is not CompatibilityDimension.SUITE_VERSION
            )
            or ("subject",)
        ),
    )
    return BaselineFactory().create_candidate(
        baseline_id=BaselineId("baseline-1"),
        scope=scope,
        manifest=manifest,
        protocol=scoring_protocol,
        decision=decision,
        finalization_checksum=FINALIZATION,
        created_at=created_at,
        compatibility_policy=(
            CompatibilityPolicy(
                "source-comparison",
                scoring_protocol.suite_version,
                policy_dimensions,
            )
            if policy_dimensions is not None
            else None
        ),
    )


def compatible_current(
    baseline,
    *,
    values: tuple[str, str, str, str] = ("0.8", "1.0", "0.8", "0.8"),
    source: str = "c",
):
    manifest, scoring_protocol, decision = bundle("run-current", values, source=source)
    compatibility = CompatibilityEvaluator().evaluate(
        baseline, manifest, scoring_protocol, decision
    )
    return manifest, scoring_protocol, decision, compatibility


def compare(
    baseline,
    *,
    values: tuple[str, str, str, str] = ("0.8", "1.0", "0.8", "0.8"),
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER,
):
    manifest, scoring_protocol, decision, compatibility = compatible_current(
        baseline, values=values
    )
    return ComparisonEngine().compare(
        baseline,
        compatibility,
        ComparisonInput(
            ComparisonId("comparison-1"),
            manifest,
            scoring_protocol,
            decision,
            (MetricDirectionSpec("quality", direction),),
            NOW,
        ),
    )


def rule(**changes):
    scoring_protocol = protocol()
    model = RegressionRule(
        RegressionRuleId("rule-1"),
        scoring_protocol.suite_version,
        DefinitionStatus.FROZEN,
        None,
        Decimal("0.05"),
        (
            MetricThreshold(
                "quality",
                maximum_regression=Decimal("0.05"),
                direction=MetricDirection.HIGHER_IS_BETTER,
            ),
        ),
        tuple(target.case_reference for target in scoring_protocol.targets),
        (scoring_protocol.targets[0].case_reference,),
        0,
        None,
        2,
        None,
        None,
        ContentChecksum("a" * 64),
        maximum_coverage_loss=Decimal("0.05"),
        maximum_variance_increase=Decimal("0.02"),
        maximum_confidence_reduction=Decimal("0.05"),
    )
    return replace(model, **changes)


def test_candidate_is_valid_safe_and_deterministic() -> None:
    first = candidate()
    second = candidate(created_at=LATER)
    assert first.status is BaselineStatus.CANDIDATE
    assert first.source_run_verdict is Verdict.PASSED
    assert first.content_checksum == second.content_checksum
    assert first.created_at != second.created_at
    assert not hasattr(first, "payload")
    assert "custody://" not in repr(first)
    BaselineFactory().validate(first)
    with pytest.raises(BaselineFingerprintMismatch):
        BaselineFactory().validate(replace(first, summary_checksum=ContentChecksum("e" * 64)))


def test_inconclusive_is_an_explicitly_eligible_known_state() -> None:
    manifest, scoring_protocol, _ = bundle("run-inconclusive")
    scoring_protocol = replace(scoring_protocol, maximum_variance=Decimal("0.001"))
    required, optional = scoring_protocol.targets
    decision = ScoringEngine().score(
        scoring_protocol,
        (
            observation(required, 1, "0.8", run_id=scoring_protocol.run_id),
            observation(required, 2, "1.0", run_id=scoring_protocol.run_id),
            observation(optional, 1, "0.8", run_id=scoring_protocol.run_id),
            observation(optional, 2, "1.0", run_id=scoring_protocol.run_id),
        ),
    )
    result = BaselineFactory().create_candidate(
        baseline_id=BaselineId("baseline-inconclusive"),
        scope=ComparisonScope(
            scoring_protocol.suite_id,
            scoring_protocol.suite_version,
            "known-state",
            ("source_fingerprint",),
        ),
        manifest=manifest,
        protocol=scoring_protocol,
        decision=decision,
        finalization_checksum=FINALIZATION,
        created_at=NOW,
        eligibility_policy=BaselineEligibilityPolicy(allow_inconclusive_research=True),
    )
    assert result.source_run_verdict is Verdict.INCONCLUSIVE


def test_inconclusive_requires_permission_and_complete_aggregates() -> None:
    manifest, scoring_protocol, decision = bundle("run-inconclusive-policy")
    decision = replace(decision, verdict=Verdict.INCONCLUSIVE)
    scope = ComparisonScope(
        scoring_protocol.suite_id,
        scoring_protocol.suite_version,
        "research",
        ("source_fingerprint",),
    )
    factory = BaselineFactory()
    with pytest.raises(InvalidBaselineSource, match="research permission"):
        factory.create_candidate(
            baseline_id=BaselineId("baseline-no-permission"),
            scope=scope,
            manifest=manifest,
            protocol=scoring_protocol,
            decision=decision,
            finalization_checksum=FINALIZATION,
            created_at=NOW,
        )
    incomplete = replace(decision, case_aggregations=decision.case_aggregations[:-1])
    with pytest.raises(InvalidBaselineSource, match="complete comparable aggregates"):
        factory.create_candidate(
            baseline_id=BaselineId("baseline-incomplete"),
            scope=scope,
            manifest=manifest,
            protocol=scoring_protocol,
            decision=incomplete,
            finalization_checksum=FINALIZATION,
            created_at=NOW,
            eligibility_policy=BaselineEligibilityPolicy(allow_inconclusive_research=True),
        )


@pytest.mark.parametrize("verdict", [Verdict.INVALID, Verdict.POLICY_DENIED, Verdict.FAILED])
def test_candidate_rejects_ineligible_verdicts(verdict: Verdict) -> None:
    manifest, scoring_protocol, decision = bundle("run-baseline")
    decision = replace(decision, verdict=verdict)
    with pytest.raises(InvalidBaselineSource):
        BaselineFactory().create_candidate(
            baseline_id=BaselineId("baseline-bad"),
            scope=ComparisonScope(
                scoring_protocol.suite_id,
                scoring_protocol.suite_version,
                "default",
                ("source_fingerprint",),
            ),
            manifest=manifest,
            protocol=scoring_protocol,
            decision=decision,
            finalization_checksum=FINALIZATION,
            created_at=NOW,
        )


def test_non_candidate_still_requires_external_authority() -> None:
    with pytest.raises(Exception):
        replace(candidate(), status=BaselineStatus.ACTIVE)


def test_compatibility_is_typed_deterministic_and_allows_declared_difference() -> None:
    baseline = candidate()
    _, _, _, exact = compatible_current(baseline)
    assert exact.status is CompatibilityStatus.COMPATIBLE
    _, _, _, conditional = compatible_current(baseline, source="d")
    assert conditional.status is CompatibilityStatus.CONDITIONALLY_COMPATIBLE
    assert conditional.allowed_differences == ("source_fingerprint",)
    assert conditional.reason_codes == (CompatibilityReasonCode.CONTROLLED_DIFFERENCE,)
    assert conditional.condition_policy_fingerprint is not None


def test_scope_alone_cannot_authorize_a_conditional_comparison() -> None:
    baseline = candidate(policy_dimensions=None)
    _, _, _, result = compatible_current(baseline, source="d")
    assert result.status is CompatibilityStatus.INCOMPATIBLE
    assert result.condition_policy_fingerprint is None


def test_suite_version_requires_an_explicit_structural_compatibility_policy() -> None:
    baseline = candidate(policy_dimensions=(CompatibilityDimension.SUITE_VERSION,))
    manifest, scoring_protocol, decision = bundle("run-current")
    version = replace(scoring_protocol.suite_version, value="1.1.0")
    current_protocol = replace(scoring_protocol, suite_version=version)
    current_manifest = replace(manifest, suite_version=version)
    result = CompatibilityEvaluator().evaluate(
        baseline, current_manifest, current_protocol, decision
    )
    assert result.status is CompatibilityStatus.CONDITIONALLY_COMPATIBLE
    assert result.allowed_differences == ("suite_version",)


def test_multiple_controlled_changes_are_not_a_conditional_fallback() -> None:
    baseline = candidate(
        policy_dimensions=(
            CompatibilityDimension.SOURCE_FINGERPRINT,
            CompatibilityDimension.MODEL_PROVIDER,
        )
    )
    manifest, scoring_protocol, decision = bundle("run-current", source="d")
    assert manifest.model_provider is not None
    changed_manifest = replace(
        manifest,
        model_provider=replace(
            manifest.model_provider,
            configuration_checksum=ContentChecksum("e" * 64),
        ),
    )
    result = CompatibilityEvaluator().evaluate(
        baseline, changed_manifest, scoring_protocol, decision
    )
    assert result.status is CompatibilityStatus.INCOMPATIBLE
    assert "multiple_controlled_dimensions" in result.blocking_differences


def test_dangerous_protocol_differences_are_always_blocking() -> None:
    baseline = candidate()
    manifest, scoring_protocol, decision = bundle("run-current")

    dataset_changed = replace(
        manifest,
        dataset_binding=replace(
            manifest.dataset_binding,
            binding_id=DatasetBindingId("different-dataset"),
        ),
    )
    dataset_result = CompatibilityEvaluator().evaluate(
        baseline, dataset_changed, scoring_protocol, decision
    )
    assert "dataset_identity" in dataset_result.blocking_differences

    case_removed = replace(manifest, case_references=manifest.case_references[:-1])
    case_result = CompatibilityEvaluator().evaluate(
        baseline, case_removed, scoring_protocol, decision
    )
    assert "case_set" in case_result.blocking_differences

    changed_targets = (
        scoring_protocol.targets[0],
        replace(scoring_protocol.targets[1], required=True),
    )
    required_changed = replace(scoring_protocol, targets=changed_targets)
    required_result = CompatibilityEvaluator().evaluate(
        baseline, manifest, required_changed, decision
    )
    assert "scoring_protocol" in required_result.blocking_differences

    changed_aggregation = replace(
        decision.case_aggregations[0],
        scale_maximum=Decimal("2"),
    )
    scale_result = CompatibilityEvaluator().evaluate(
        baseline,
        manifest,
        scoring_protocol,
        replace(
            decision,
            case_aggregations=(changed_aggregation,) + decision.case_aggregations[1:],
        ),
    )
    assert "metric_scale:quality" in scale_result.blocking_differences

    changed_method = replace(
        decision.case_aggregations[0],
        confidence_projection_method="conservative_minimum:different-method",
    )
    method_result = CompatibilityEvaluator().evaluate(
        baseline,
        manifest,
        scoring_protocol,
        replace(
            decision,
            case_aggregations=(changed_method,) + decision.case_aggregations[1:],
        ),
    )
    assert "confidence_method:quality" in method_result.blocking_differences


def test_compatibility_collects_sorted_blocking_differences() -> None:
    baseline = candidate()
    manifest, scoring_protocol, decision = bundle("run-current")
    manifest = replace(
        manifest,
        evaluator=replace(manifest.evaluator, version=replace(manifest.evaluator.version, value="2.0.0")),
        dataset_binding=replace(manifest.dataset_binding, revision=replace(manifest.dataset_binding.revision, value=2)),
    )
    result = CompatibilityEvaluator().evaluate(baseline, manifest, scoring_protocol, decision)
    assert result.status is CompatibilityStatus.INCOMPATIBLE
    assert result.blocking_differences == tuple(sorted(result.blocking_differences))
    assert "evaluator_identity" in result.blocking_differences


def test_comparison_covers_improvement_stability_inverse_direction_and_decimal() -> None:
    baseline = candidate()
    stable = compare(baseline)
    assert stable.result is ComparisonResult.STABLE
    improved = compare(baseline, values=("0.9", "1.0", "0.9", "0.9"))
    assert improved.result is ComparisonResult.IMPROVED
    assert all(isinstance(item.delta, Decimal) for item in improved.metric_deltas)
    inverse = compare(
        baseline,
        values=("0.9", "1.0", "0.9", "0.9"),
        direction=MetricDirection.LOWER_IS_BETTER,
    )
    assert inverse.metric_deltas[0].direction is DeltaDirection.REGRESSED
    assert inverse.result is ComparisonResult.REGRESSED


def test_comparison_rejects_incompatibility_and_missing_direction() -> None:
    baseline = candidate()
    manifest, scoring_protocol, decision, compatibility = compatible_current(
        baseline, source="d"
    )
    incompatible = replace(
        compatibility,
        status=CompatibilityStatus.INCOMPATIBLE,
        blocking_differences=("suite_id",),
    )
    comparison_input = ComparisonInput(
        ComparisonId("comparison-bad"),
        manifest,
        scoring_protocol,
        decision,
        (),
        NOW,
    )
    with pytest.raises(IncompatibleComparison):
        ComparisonEngine().compare(baseline, incompatible, comparison_input)
    with pytest.raises(MetricDirectionMissing):
        ComparisonEngine().compare(baseline, compatibility, comparison_input)


def test_critical_regression_wins_even_when_other_case_improves() -> None:
    baseline = candidate()
    comparison = compare(baseline, values=("0.83", "0.85", "1.0", "1.0"))
    assert comparison.overall_delta is not None
    assert comparison.overall_delta.direction is DeltaDirection.IMPROVED
    report = RegressionDetector().evaluate(
        comparison,
        rule(),
        report_id=RegressionReportId("report-1"),
        created_at=NOW,
    )
    assert report.result is ComparisonResult.REGRESSED
    assert "critical_case_regressed" in report.reason_codes
    assert report.critical_regressions
    assert report.comparison_fingerprint == Fingerprint(comparison.checksum.value)
    assert "run-current" not in repr(report)


def test_coverage_variance_and_confidence_regressions_override_improvement() -> None:
    baseline = candidate()
    improved = compare(baseline, values=("0.9", "1.0", "0.9", "1.0"))
    detector = RegressionDetector()

    coverage = replace(improved, coverage_delta=Decimal("-0.1"))
    coverage_report = detector.evaluate(
        coverage, rule(), report_id=RegressionReportId("report-coverage"), created_at=NOW
    )
    assert "coverage_loss" in coverage_report.reason_codes

    variance = replace(
        improved,
        baseline_variance=Decimal("0.01"),
        current_variance=Decimal("0.05"),
        variance_delta=Decimal("0.04"),
    )
    variance_report = detector.evaluate(
        variance, rule(), report_id=RegressionReportId("report-variance"), created_at=NOW
    )
    assert "variance_increased" in variance_report.reason_codes

    critical_reference = rule().critical_cases[0]
    critical_case = next(
        item for item in improved.case_deltas if item.case_reference == critical_reference
    )
    optional_case = next(
        item for item in improved.case_deltas if item.case_reference != critical_reference
    )
    confidence = replace(
        improved,
        case_deltas=(
            replace(
                critical_case,
                baseline_confidence=Decimal("0.95"),
                current_confidence=Decimal("0.80"),
                confidence_delta=Decimal("-0.15"),
            ),
            replace(
                optional_case,
                baseline_confidence=Decimal("0.80"),
                current_confidence=Decimal("0.90"),
                confidence_delta=Decimal("0.10"),
            ),
        ),
    )
    confidence_report = detector.evaluate(
        confidence,
        rule(),
        report_id=RegressionReportId("report-confidence"),
        created_at=NOW,
    )
    assert "confidence_reduced" in confidence_report.reason_codes
    assert critical_case.case_reference in confidence_report.critical_regressions


def test_regression_rule_rejects_duplicate_conflicting_and_directionless_rules() -> None:
    threshold = MetricThreshold(
        "quality",
        maximum_regression=Decimal("0.05"),
        direction=MetricDirection.HIGHER_IS_BETTER,
    )
    with pytest.raises(DuplicateReference):
        replace(rule(), metric_thresholds=(threshold, threshold))
    with pytest.raises(InvalidRegressionRule):
        replace(rule(), failure_budget_weight=Decimal("0"))

    comparison = compare(candidate(), values=("0.7", "0.8", "0.8", "0.8"))
    with pytest.raises(RegressionEvaluationFailure, match="direction is required"):
        RegressionDetector().evaluate(
            comparison,
            rule(
                metric_thresholds=(
                    MetricThreshold("quality", maximum_regression=Decimal("0.05")),
                )
            ),
            report_id=RegressionReportId("report-directionless"),
            created_at=NOW,
        )
    with pytest.raises(RegressionEvaluationFailure, match="incompatible"):
        RegressionDetector().evaluate(
            comparison,
            rule(
                metric_thresholds=(
                    MetricThreshold(
                        "quality",
                        maximum_regression=Decimal("0.05"),
                        direction=MetricDirection.LOWER_IS_BETTER,
                    ),
                )
            ),
            report_id=RegressionReportId("report-wrong-direction"),
            created_at=NOW,
        )


def test_verdict_coverage_variance_confidence_and_insufficient_rules() -> None:
    baseline = candidate()
    degraded = compare(baseline, values=("0.6", "0.7", "0.7", "0.7"))
    report = RegressionDetector().evaluate(
        degraded,
        rule(),
        report_id=RegressionReportId("report-degraded"),
        created_at=NOW,
    )
    assert "verdict_degraded" in report.reason_codes

    missing_statistics = replace(
        degraded,
        metric_deltas=(),
        case_deltas=(),
        overall_delta=None,
        baseline_verdict=Verdict.PASSED,
        current_verdict=Verdict.PASSED,
        current_failed_required_cases=(),
        current_failure_budget_consumed=Decimal("0"),
        current_variance=None,
        current_confidence=None,
    )
    insufficient = RegressionDetector().evaluate(
        missing_statistics,
        rule(maximum_variance_increase=None, maximum_confidence_reduction=None),
        report_id=RegressionReportId("report-insufficient"),
        created_at=NOW,
    )
    assert insufficient.result is ComparisonResult.INSUFFICIENT_DATA
    assert "comparable_aggregate_missing" in insufficient.reason_codes


def test_rule_and_report_fingerprints_are_semantically_sensitive() -> None:
    baseline = candidate()
    comparison = compare(baseline, values=("0.6", "0.7", "0.7", "0.7"))
    detector = RegressionDetector()
    first = detector.evaluate(
        comparison, rule(), report_id=RegressionReportId("report-fp"), created_at=NOW
    )
    later = detector.evaluate(
        comparison, rule(), report_id=RegressionReportId("report-fp"), created_at=LATER
    )
    changed = detector.evaluate(
        comparison,
        rule(
            metric_thresholds=(
                MetricThreshold(
                    "quality",
                    maximum_regression=Decimal("0.5"),
                    direction=MetricDirection.HIGHER_IS_BETTER,
                ),
            )
        ),
        report_id=RegressionReportId("report-fp"),
        created_at=NOW,
    )
    assert first.checksum == later.checksum
    assert first.checksum != changed.checksum


def test_fingerprints_normalize_rule_order_and_include_metric_direction() -> None:
    baseline = candidate()
    comparison = compare(baseline)
    latency = MetricDelta(
        "latency",
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0"),
        Decimal("0"),
        DeltaDirection.UNCHANGED,
        None,
        MetricDirection.LOWER_IS_BETTER,
    )
    comparison = replace(comparison, metric_deltas=comparison.metric_deltas + (latency,))
    quality = MetricThreshold(
        "quality",
        maximum_regression=Decimal("0.05"),
        direction=MetricDirection.HIGHER_IS_BETTER,
    )
    latency_threshold = MetricThreshold(
        "latency",
        maximum_regression=Decimal("0.05"),
        direction=MetricDirection.LOWER_IS_BETTER,
    )
    first_rule = rule(metric_thresholds=(quality, latency_threshold))
    reordered_rule = rule(metric_thresholds=(latency_threshold, quality))
    detector = RegressionDetector()
    first = detector.evaluate(
        comparison,
        first_rule,
        report_id=RegressionReportId("report-order"),
        created_at=NOW,
    )
    reordered = detector.evaluate(
        comparison,
        reordered_rule,
        report_id=RegressionReportId("report-order"),
        created_at=LATER,
    )
    assert first.checksum == reordered.checksum

    inverse = compare(baseline, direction=MetricDirection.LOWER_IS_BETTER)
    assert comparison.checksum != inverse.checksum


def test_errors_and_reprs_do_not_echo_sensitive_inputs() -> None:
    baseline = candidate()
    manifest, scoring_protocol, decision, compatibility = compatible_current(baseline)
    unsafe_marker = "token=never-echo-this"
    with pytest.raises(MetricDirectionMissing) as caught:
        ComparisonEngine().compare(
            baseline,
            compatibility,
            ComparisonInput(
                ComparisonId("comparison-safe-error"),
                manifest,
                scoring_protocol,
                decision,
                (),
                NOW,
            ),
        )
    assert unsafe_marker not in str(caught.value)
    assert unsafe_marker not in repr(baseline)
