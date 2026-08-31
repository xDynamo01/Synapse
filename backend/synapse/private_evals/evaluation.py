from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from .analysis import (
    BaselineAggregateSnapshot,
    BaselineCompatibilitySnapshot,
    BaselineEligibilityPolicy,
    ComparisonReasonCode,
    ComparisonScope,
    CompatibilityDimension,
    CompatibilityPolicy,
    CompatibilityReasonCode,
    CompatibilityResult,
    CompatibilityStatus,
    DeltaDirection,
    EvalBaseline,
    EvalComparison,
    MetricDelta,
    MetricDirection,
    MetricDirectionSpec,
    RegressionOutcome,
    RegressionReasonCode,
    RegressionReport,
    RegressionRule,
)
from .canonical import content_checksum, fingerprint
from .catalog import EvalCaseVersionRef
from .errors import (
    BaselineFingerprintMismatch,
    ComparisonFingerprintMismatch,
    IncompatibleComparison,
    IncompatibleMetricScale,
    InvalidBaselineSource,
    MetricDirectionMissing,
    MissingAggregate,
    RegressionEvaluationFailure,
    ReportFingerprintMismatch,
)
from .runs import ComponentKind, EvalRunManifest
from .scoring import CaseScoreAggregation, ScoringDecision, ScoringEngine, ScoringProtocol
from .states import BaselineStatus, ComparisonResult, DefinitionStatus, Verdict
from .values import (
    BaselineId,
    ComparisonId,
    ContentChecksum,
    Fingerprint,
    RegressionReportId,
    Revision,
    UtcTimestamp,
)

_QUANTUM = Decimal("0.000000000001")
_VERDICT_RANK = {
    Verdict.PASSED: 5,
    Verdict.INCONCLUSIVE: 4,
    Verdict.FAILED: 3,
    Verdict.BLOCKED: 2,
    Verdict.INVALID: 1,
    Verdict.POLICY_DENIED: 0,
}


def _q(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        context.rounding = ROUND_HALF_EVEN
        result = value.quantize(_QUANTUM)
        return abs(result) if result.is_zero() else result


def _protocol_checksum(protocol: ScoringProtocol) -> ContentChecksum:
    identity = dict(ScoringEngine._protocol_identity(protocol))
    identity.pop("run_id", None)
    identity.pop("suite_id", None)
    identity.pop("suite_version", None)
    return content_checksum(identity)


def _case_key(item: CaseScoreAggregation) -> tuple[str, str, str]:
    return (
        item.case_reference.case_id.value,
        item.case_reference.version.value,
        item.metric_id,
    )


def _coverage(decision: ScoringDecision) -> Decimal | None:
    total = decision.valid_score_count + decision.missing_score_count
    if total == 0:
        return None
    return _q(Decimal(decision.valid_score_count) / Decimal(total))


def _variance(decision: ScoringDecision) -> Decimal | None:
    values = tuple(
        item.sample_variance
        for item in decision.case_aggregations
        if item.sample_variance is not None
    )
    return max(values) if values else None


def _confidence(decision: ScoringDecision) -> Decimal | None:
    values = tuple(
        item.conservative_confidence_bound
        for item in decision.case_aggregations
        if item.conservative_confidence_bound is not None
    )
    return min(values) if values else None


def _compatibility_snapshot(
    manifest: EvalRunManifest,
    protocol: ScoringProtocol,
) -> BaselineCompatibilitySnapshot:
    return BaselineCompatibilitySnapshot(
        case_references=tuple(
            sorted(
                manifest.case_references,
                key=lambda item: (item.case_id.value, item.version.value),
            )
        ),
        dataset_binding=manifest.dataset_binding,
        evaluator=manifest.evaluator,
        scoring_protocol_checksum=_protocol_checksum(protocol),
        model_provider_fingerprint=(
            fingerprint(manifest.model_provider) if manifest.model_provider is not None else None
        ),
        execution_protocol_fingerprint=fingerprint(manifest.execution),
        skill_fingerprint=fingerprint(
            tuple(
                sorted(
                    (
                        item
                        for item in manifest.component_references
                        if item.kind is ComponentKind.SKILL
                    ),
                    key=lambda item: (item.kind.value, item.component_id, item.version),
                )
            )
        ),
        tool_fingerprint=fingerprint(
            tuple(
                sorted(
                    (
                        item
                        for item in manifest.component_references
                        if item.kind is ComponentKind.TOOL
                    ),
                    key=lambda item: (item.kind.value, item.component_id, item.version),
                )
            )
        ),
        security_fingerprint=fingerprint(manifest.security),
        source_fingerprint=manifest.source_fingerprint,
    )


def _aggregate_snapshot(
    protocol: ScoringProtocol,
    decision: ScoringDecision,
) -> BaselineAggregateSnapshot:
    return BaselineAggregateSnapshot(
        case_aggregations=tuple(sorted(decision.case_aggregations, key=_case_key)),
        metric_aggregations=tuple(sorted(decision.metric_aggregations)),
        overall_normalized_score=decision.overall_normalized_score,
        valid_score_count=decision.valid_score_count,
        missing_score_count=decision.missing_score_count,
        expected_repetitions=protocol.expected_repetitions,
        failure_budget_consumed=decision.failure_budget.consumed,
    )


def _validate_input(
    manifest: EvalRunManifest,
    protocol: ScoringProtocol,
    decision: ScoringDecision,
) -> None:
    if manifest.suite_id != protocol.suite_id or manifest.suite_version != protocol.suite_version:
        raise InvalidBaselineSource("baseline source references are inconsistent")
    if protocol.run_id != decision.run_id:
        raise InvalidBaselineSource("baseline source run reference is inconsistent")
    manifest_cases = set(manifest.case_references)
    protocol_cases = {target.case_reference for target in protocol.targets}
    if manifest_cases != protocol_cases:
        raise InvalidBaselineSource("baseline case set is incomplete")
    if any(target.evaluator != manifest.evaluator for target in protocol.targets):
        raise InvalidBaselineSource("baseline evaluator identity is inconsistent")


def _rule_identity(rule: RegressionRule) -> dict[str, object]:
    return {
        "rule_id": rule.rule_id,
        "version": rule.version,
        "status": rule.status,
        "overall_minimum": rule.overall_minimum,
        "maximum_overall_regression": rule.maximum_overall_regression,
        "metric_thresholds": tuple(sorted(rule.metric_thresholds, key=lambda item: item.metric_id)),
        "mandatory_cases": tuple(
            sorted(rule.mandatory_cases, key=lambda item: (item.case_id.value, item.version.value))
        ),
        "critical_cases": tuple(
            sorted(rule.critical_cases, key=lambda item: (item.case_id.value, item.version.value))
        ),
        "failure_budget_count": rule.failure_budget_count,
        "failure_budget_weight": rule.failure_budget_weight,
        "minimum_repetitions": rule.minimum_repetitions,
        "maximum_variance": rule.maximum_variance,
        "required_confidence": rule.required_confidence,
        "maximum_coverage_loss": rule.maximum_coverage_loss,
        "maximum_variance_increase": rule.maximum_variance_increase,
        "maximum_confidence_reduction": rule.maximum_confidence_reduction,
        "fail_on_verdict_degradation": rule.fail_on_verdict_degradation,
        "checksum": rule.checksum,
    }


class BaselineFactory:
    """Creates an immutable candidate; institutional promotion stays external."""

    def create_candidate(
        self,
        *,
        baseline_id: BaselineId,
        scope: ComparisonScope,
        manifest: EvalRunManifest,
        protocol: ScoringProtocol,
        decision: ScoringDecision,
        finalization_checksum: ContentChecksum,
        created_at: UtcTimestamp,
        expected_decision_fingerprint: Fingerprint | None = None,
        eligibility_policy: BaselineEligibilityPolicy = BaselineEligibilityPolicy(),
        compatibility_policy: CompatibilityPolicy | None = None,
    ) -> EvalBaseline:
        _validate_input(manifest, protocol, decision)
        if scope.suite_id != manifest.suite_id or scope.suite_version != manifest.suite_version:
            raise InvalidBaselineSource("baseline scope is inconsistent")
        if decision.verdict is Verdict.INCONCLUSIVE and not (
            eligibility_policy.allow_inconclusive_research
        ):
            raise InvalidBaselineSource("inconclusive baseline requires explicit research permission")
        if decision.verdict not in {Verdict.PASSED, Verdict.INCONCLUSIVE}:
            raise InvalidBaselineSource("baseline source verdict is not eligible")
        if not self._has_complete_comparison_data(protocol, decision):
            raise InvalidBaselineSource("baseline source lacks complete comparable aggregates")
        if (
            expected_decision_fingerprint is not None
            and expected_decision_fingerprint != decision.decision_fingerprint
        ):
            raise BaselineFingerprintMismatch("baseline decision fingerprint mismatch")

        aggregates = _aggregate_snapshot(protocol, decision)
        compatibility = _compatibility_snapshot(manifest, protocol)
        summary_checksum = content_checksum(aggregates)
        compatibility_signature = fingerprint(
            {
                "scope": scope,
                "compatibility": compatibility,
                "compatibility_policy": compatibility_policy,
            }
        )
        semantic = {
            "baseline_id": baseline_id,
            "scope": scope,
            "source_run_id": decision.run_id,
            "source_run_verdict": decision.verdict,
            "run_fingerprint": manifest.run_fingerprint,
            "finalization_checksum": finalization_checksum,
            "protocol_fingerprint": manifest.protocol_fingerprint,
            "subject_fingerprint": manifest.subject_fingerprint,
            "decision_fingerprint": decision.decision_fingerprint,
            "compatibility_signature": compatibility_signature,
            "summary_checksum": summary_checksum,
            "status": BaselineStatus.CANDIDATE,
            "aggregates": aggregates,
            "compatibility": compatibility,
            "compatibility_policy": compatibility_policy,
            "eligibility_policy": eligibility_policy,
            "revision": Revision(1),
            "governance_binding_reference": None,
        }
        return EvalBaseline(
            baseline_id=baseline_id,
            scope=scope,
            source_run_id=decision.run_id,
            source_run_verdict=decision.verdict,
            run_fingerprint=manifest.run_fingerprint,
            finalization_checksum=finalization_checksum,
            protocol_fingerprint=manifest.protocol_fingerprint,
            subject_fingerprint=manifest.subject_fingerprint,
            compatibility_signature=compatibility_signature,
            summary_checksum=summary_checksum,
            status=BaselineStatus.CANDIDATE,
            content_checksum=content_checksum(semantic),
            revision=Revision(1),
            governance_binding_reference=None,
            created_at=created_at,
            decision_fingerprint=decision.decision_fingerprint,
            aggregates=aggregates,
            compatibility=compatibility,
            compatibility_policy=compatibility_policy,
            eligibility_policy=eligibility_policy,
        )

    @staticmethod
    def _has_complete_comparison_data(
        protocol: ScoringProtocol,
        decision: ScoringDecision,
    ) -> bool:
        expected = {(item.case_reference, item.metric_id) for item in protocol.targets}
        actual = {(item.case_reference, item.metric_id) for item in decision.case_aggregations}
        return (
            expected == actual
            and bool(decision.metric_aggregations)
            and decision.overall_normalized_score is not None
            and decision.invalid_result_count == 0
            and decision.policy_denial_count == 0
            and decision.infrastructure_failure_count == 0
            and decision.cancelled_observation_count == 0
            and decision.missing_repetition_count == 0
            and decision.explicit_missing_score_count == 0
        )

    def validate(self, baseline: EvalBaseline) -> None:
        if (
            baseline.decision_fingerprint is None
            or baseline.aggregates is None
            or baseline.compatibility is None
        ):
            raise InvalidBaselineSource("baseline comparison metadata is incomplete")
        semantic = {
            "baseline_id": baseline.baseline_id,
            "scope": baseline.scope,
            "source_run_id": baseline.source_run_id,
            "source_run_verdict": baseline.source_run_verdict,
            "run_fingerprint": baseline.run_fingerprint,
            "finalization_checksum": baseline.finalization_checksum,
            "protocol_fingerprint": baseline.protocol_fingerprint,
            "subject_fingerprint": baseline.subject_fingerprint,
            "decision_fingerprint": baseline.decision_fingerprint,
            "compatibility_signature": baseline.compatibility_signature,
            "summary_checksum": baseline.summary_checksum,
            "status": baseline.status,
            "aggregates": baseline.aggregates,
            "compatibility": baseline.compatibility,
            "compatibility_policy": baseline.compatibility_policy,
            "eligibility_policy": baseline.eligibility_policy,
            "revision": baseline.revision,
            "governance_binding_reference": baseline.governance_binding_reference,
        }
        if content_checksum(semantic) != baseline.content_checksum:
            raise BaselineFingerprintMismatch("baseline fingerprint mismatch")


class CompatibilityEvaluator:
    """Compares semantic dimensions and reports controlled differences explicitly."""

    def evaluate(
        self,
        baseline: EvalBaseline,
        manifest: EvalRunManifest,
        protocol: ScoringProtocol,
        decision: ScoringDecision,
    ) -> CompatibilityResult:
        if (
            manifest.suite_id != protocol.suite_id
            or manifest.suite_version != protocol.suite_version
            or protocol.run_id != decision.run_id
        ):
            raise InvalidBaselineSource("current comparison references are inconsistent")
        if baseline.compatibility is None or baseline.decision_fingerprint is None:
            raise InvalidBaselineSource("baseline lacks comparison metadata")
        current = _compatibility_snapshot(manifest, protocol)
        policy_dimensions = (
            set(baseline.compatibility_policy.allowed_dimensions)
            if baseline.compatibility_policy is not None
            else set()
        )
        scope_dimensions = set(baseline.scope.controlled_dimensions)
        blocking: list[str] = []
        allowed: list[str] = []

        def compare(
            field: str,
            left: object,
            right: object,
            *,
            controlled_by: CompatibilityDimension | None = None,
        ) -> None:
            if left == right:
                return
            policy_allows = controlled_by is not None and controlled_by in policy_dimensions
            scope_allows = controlled_by is CompatibilityDimension.SUITE_VERSION or (
                controlled_by is not None and controlled_by.value in scope_dimensions
            )
            if policy_allows and scope_allows:
                allowed.append(field)
            else:
                blocking.append(field)

        compare("suite_id", baseline.scope.suite_id, manifest.suite_id)
        compare(
            "suite_version",
            baseline.scope.suite_version,
            manifest.suite_version,
            controlled_by=CompatibilityDimension.SUITE_VERSION,
        )
        compare(
            "case_set",
            baseline.compatibility.case_references,
            current.case_references,
        )
        compare(
            "dataset_identity",
            baseline.compatibility.dataset_binding.binding_id,
            current.dataset_binding.binding_id,
        )
        revision_changed = (
            baseline.compatibility.dataset_binding.revision != current.dataset_binding.revision
            or baseline.compatibility.dataset_binding.checksum != current.dataset_binding.checksum
        )
        if revision_changed:
            compare("dataset_revision", False, True)
        compare("evaluator_identity", baseline.compatibility.evaluator, current.evaluator)
        compare(
            "scoring_protocol",
            baseline.compatibility.scoring_protocol_checksum,
            current.scoring_protocol_checksum,
        )
        compare(
            "model_provider",
            baseline.compatibility.model_provider_fingerprint,
            current.model_provider_fingerprint,
            controlled_by=CompatibilityDimension.MODEL_PROVIDER,
        )
        compare(
            "execution_protocol",
            baseline.compatibility.execution_protocol_fingerprint,
            current.execution_protocol_fingerprint,
        )
        compare(
            "skills",
            baseline.compatibility.skill_fingerprint,
            current.skill_fingerprint,
            controlled_by=CompatibilityDimension.SKILLS,
        )
        compare(
            "tools",
            baseline.compatibility.tool_fingerprint,
            current.tool_fingerprint,
            controlled_by=CompatibilityDimension.TOOLS,
        )
        compare(
            "security_snapshot",
            baseline.compatibility.security_fingerprint,
            current.security_fingerprint,
        )
        compare(
            "source_fingerprint",
            baseline.compatibility.source_fingerprint,
            current.source_fingerprint,
            controlled_by=CompatibilityDimension.SOURCE_FINGERPRINT,
        )
        baseline_scales = {
            _case_key(item): (item.score_kind, item.scale_minimum, item.scale_maximum)
            for item in baseline.aggregates.case_aggregations
            if isinstance(item, CaseScoreAggregation)
        } if baseline.aggregates is not None else {}
        current_scales = {
            _case_key(item): (item.score_kind, item.scale_minimum, item.scale_maximum)
            for item in decision.case_aggregations
        }
        for key in sorted(set(baseline_scales) & set(current_scales)):
            if baseline_scales[key] != current_scales[key]:
                blocking.append(f"metric_scale:{key[2]}")
        baseline_methods = {
            _case_key(item): item.confidence_projection_method
            for item in baseline.aggregates.case_aggregations
            if isinstance(item, CaseScoreAggregation)
        } if baseline.aggregates is not None else {}
        current_methods = {
            _case_key(item): item.confidence_projection_method
            for item in decision.case_aggregations
        }
        for key in sorted(set(baseline_methods) & set(current_methods)):
            if baseline_methods[key] != current_methods[key]:
                blocking.append(f"confidence_method:{key[2]}")

        blocking_tuple = tuple(sorted(set(blocking)))
        allowed_tuple = tuple(sorted(set(allowed)))
        if len(allowed_tuple) > 1:
            blocking_tuple = tuple(sorted((*blocking_tuple, "multiple_controlled_dimensions")))
            allowed_tuple = ()
        if blocking_tuple:
            status = CompatibilityStatus.INCOMPATIBLE
        elif allowed_tuple:
            status = CompatibilityStatus.CONDITIONALLY_COMPATIBLE
        else:
            status = CompatibilityStatus.COMPATIBLE
        if blocking_tuple:
            reasons = (CompatibilityReasonCode.BLOCKING_DIFFERENCE,)
        elif allowed_tuple:
            reasons = (CompatibilityReasonCode.CONTROLLED_DIFFERENCE,)
        else:
            reasons = (CompatibilityReasonCode.EXACT_MATCH,)
        condition_policy_fingerprint = (
            baseline.compatibility_policy.policy_fingerprint
            if allowed_tuple and baseline.compatibility_policy is not None
            else None
        )
        semantic = {
            "baseline_id": baseline.baseline_id,
            "baseline_decision": baseline.decision_fingerprint,
            "current_decision": decision.decision_fingerprint,
            "status": status,
            "blocking": blocking_tuple,
            "allowed": allowed_tuple,
            "reason_codes": reasons,
            "condition_policy_fingerprint": condition_policy_fingerprint,
        }
        return CompatibilityResult(
            status,
            reasons,
            allowed_tuple,
            blocking_tuple,
            fingerprint(semantic),
            condition_policy_fingerprint,
        )


@dataclass(frozen=True)
class ComparisonInput:
    comparison_id: ComparisonId
    manifest: EvalRunManifest
    protocol: ScoringProtocol
    decision: ScoringDecision
    metric_directions: tuple[MetricDirectionSpec, ...]
    created_at: UtcTimestamp


class ComparisonEngine:
    def compare(
        self,
        baseline: EvalBaseline,
        compatibility: CompatibilityResult,
        comparison_input: ComparisonInput,
    ) -> EvalComparison:
        if not compatibility.compatible:
            raise IncompatibleComparison("comparison compatibility is invalid")
        if baseline.aggregates is None or baseline.compatibility is None:
            raise MissingAggregate("baseline aggregate is unavailable")
        current = comparison_input.decision
        direction_map = {item.metric_id: item.direction for item in comparison_input.metric_directions}
        if len(direction_map) != len(comparison_input.metric_directions):
            raise MetricDirectionMissing("metric direction identifiers must be unique")

        metric_deltas = tuple(
            self._delta(metric, old, new, direction_map)
            for metric, old, new in self._metric_pairs(baseline, current)
        )
        baseline_cases = {
            _case_key(item): item
            for item in baseline.aggregates.case_aggregations
            if isinstance(item, CaseScoreAggregation)
        }
        current_cases = {_case_key(item): item for item in current.case_aggregations}
        case_deltas: list[MetricDelta] = []
        for key in sorted(set(baseline_cases) & set(current_cases)):
            old = baseline_cases[key]
            new = current_cases[key]
            if (old.score_kind, old.scale_minimum, old.scale_maximum) != (
                new.score_kind,
                new.scale_minimum,
                new.scale_maximum,
            ):
                raise IncompatibleMetricScale("metric scales are incompatible")
            case_delta = self._delta(
                    old.metric_id,
                    old.normalized_mean,
                    new.normalized_mean,
                    direction_map,
                    case_reference=old.case_reference,
                )
            variance_delta = (
                _q(new.sample_variance - old.sample_variance)
                if old.sample_variance is not None and new.sample_variance is not None
                else None
            )
            confidence_delta = (
                _q(new.conservative_confidence_bound - old.conservative_confidence_bound)
                if old.conservative_confidence_bound is not None
                and new.conservative_confidence_bound is not None
                else None
            )
            case_deltas.append(
                replace(
                    case_delta,
                    baseline_variance=old.sample_variance,
                    current_variance=new.sample_variance,
                    variance_delta=variance_delta,
                    baseline_confidence=old.conservative_confidence_bound,
                    current_confidence=new.conservative_confidence_bound,
                    confidence_delta=confidence_delta,
                    confidence_method=old.confidence_projection_method,
                )
            )
        overall_delta = None
        if (
            baseline.aggregates.overall_normalized_score is not None
            and current.overall_normalized_score is not None
        ):
            overall_delta = self._delta(
                "global:overall",
                baseline.aggregates.overall_normalized_score,
                current.overall_normalized_score,
                {"global:overall": MetricDirection.HIGHER_IS_BETTER},
            )

        deltas = metric_deltas + tuple(case_deltas)
        baseline_required = {
            item.case_reference
            for item in baseline.aggregates.case_aggregations
            if isinstance(item, CaseScoreAggregation) and item.required
        }
        current_cases_present = {item.case_reference for item in current.case_aggregations}
        if baseline_required - current_cases_present:
            result = ComparisonResult.INSUFFICIENT_DATA
            reasons = (ComparisonReasonCode.REQUIRED_CASE_AGGREGATE_MISSING,)
        elif not deltas or overall_delta is None:
            result = ComparisonResult.INSUFFICIENT_DATA
            reasons = (ComparisonReasonCode.COMPARABLE_AGGREGATE_MISSING,)
        elif any(item.direction is DeltaDirection.REGRESSED for item in deltas):
            result = ComparisonResult.REGRESSED
            reasons = (ComparisonReasonCode.DIRECTED_REGRESSION_OBSERVED,)
        elif any(item.direction is DeltaDirection.IMPROVED for item in deltas):
            result = ComparisonResult.IMPROVED
            reasons = (ComparisonReasonCode.NON_REGRESSIVE_CHANGE_OBSERVED,)
        else:
            result = ComparisonResult.STABLE
            reasons = (ComparisonReasonCode.ALL_METRICS_UNCHANGED,)

        baseline_coverage = self._baseline_coverage(baseline.aggregates)
        current_coverage = _coverage(current)
        coverage_delta = (
            _q(current_coverage - baseline_coverage)
            if baseline_coverage is not None and current_coverage is not None
            else None
        )
        baseline_variance = self._baseline_variance(baseline.aggregates)
        baseline_confidence = self._baseline_confidence(baseline.aggregates)
        current_variance = _variance(current)
        current_confidence = _confidence(current)
        variance_delta = (
            _q(current_variance - baseline_variance)
            if baseline_variance is not None and current_variance is not None
            else None
        )
        confidence_delta = (
            _q(current_confidence - baseline_confidence)
            if baseline_confidence is not None and current_confidence is not None
            else None
        )
        semantic = {
            "comparison_id": comparison_input.comparison_id,
            "baseline_id": baseline.baseline_id,
            "baseline_decision": baseline.decision_fingerprint,
            "current_decision": current.decision_fingerprint,
            "compatibility": compatibility.fingerprint,
            "scope": baseline.scope,
            "metric_deltas": metric_deltas,
            "case_deltas": tuple(case_deltas),
            "overall_delta": overall_delta,
            "coverage_delta": coverage_delta,
            "variance_delta": variance_delta,
            "confidence_delta": confidence_delta,
            "result": result,
            "reason_codes": reasons,
        }
        return EvalComparison(
            comparison_id=comparison_input.comparison_id,
            current_run_id=current.run_id,
            baseline_id=baseline.baseline_id,
            baseline_run_id=baseline.source_run_id,
            scope=baseline.scope,
            current_protocol_fingerprint=comparison_input.manifest.protocol_fingerprint,
            baseline_protocol_fingerprint=baseline.protocol_fingerprint,
            allowed_differences=compatibility.allowed_differences,
            result=result,
            metric_deltas=metric_deltas,
            reason_codes=reasons,
            checksum=content_checksum(semantic),
            created_at=comparison_input.created_at,
            compatibility_fingerprint=compatibility.fingerprint,
            case_deltas=tuple(case_deltas),
            overall_delta=overall_delta,
            baseline_verdict=baseline.source_run_verdict,
            current_verdict=current.verdict,
            baseline_coverage=baseline_coverage,
            current_coverage=current_coverage,
            coverage_delta=coverage_delta,
            baseline_variance=baseline_variance,
            current_variance=current_variance,
            baseline_confidence=baseline_confidence,
            current_confidence=current_confidence,
            current_repetitions=comparison_input.protocol.expected_repetitions,
            baseline_failed_required_cases=tuple(
                item.case_reference
                for item in baseline.aggregates.case_aggregations
                if isinstance(item, CaseScoreAggregation)
                and item.required
                and item.threshold_passed is False
            ),
            current_failed_required_cases=current.failed_required_cases,
            baseline_failure_budget_consumed=baseline.aggregates.failure_budget_consumed,
            current_failure_budget_consumed=current.failure_budget.consumed,
            variance_delta=variance_delta,
            confidence_delta=confidence_delta,
            compatibility_status=compatibility.status,
            failure_budget_unit=current.failure_budget.unit.value,
        )

    @staticmethod
    def _metric_pairs(
        baseline: EvalBaseline,
        current: ScoringDecision,
    ) -> tuple[tuple[str, Decimal, Decimal], ...]:
        old = dict(baseline.aggregates.metric_aggregations) if baseline.aggregates else {}
        new = dict(current.metric_aggregations)
        return tuple((metric, old[metric], new[metric]) for metric in sorted(set(old) & set(new)))

    @staticmethod
    def _delta(
        metric: str,
        old: Decimal,
        new: Decimal,
        directions: dict[str, MetricDirection],
        *,
        case_reference: EvalCaseVersionRef | None = None,
    ) -> MetricDelta:
        direction = directions.get(metric)
        if direction is None:
            raise MetricDirectionMissing("metric direction is required")
        delta = _q(new - old)
        if delta == 0:
            outcome = DeltaDirection.UNCHANGED
        elif (delta > 0) == (direction is MetricDirection.HIGHER_IS_BETTER):
            outcome = DeltaDirection.IMPROVED
        else:
            outcome = DeltaDirection.REGRESSED
        return MetricDelta(
            metric,
            old,
            new,
            delta,
            delta,
            outcome,
            case_reference,
            direction,
        )

    @staticmethod
    def _baseline_coverage(snapshot: BaselineAggregateSnapshot) -> Decimal | None:
        total = snapshot.valid_score_count + snapshot.missing_score_count
        return _q(Decimal(snapshot.valid_score_count) / Decimal(total)) if total else None

    @staticmethod
    def _baseline_variance(snapshot: BaselineAggregateSnapshot) -> Decimal | None:
        values = tuple(
            item.sample_variance
            for item in snapshot.case_aggregations
            if isinstance(item, CaseScoreAggregation) and item.sample_variance is not None
        )
        return max(values) if values else None

    @staticmethod
    def _baseline_confidence(snapshot: BaselineAggregateSnapshot) -> Decimal | None:
        values = tuple(
            item.conservative_confidence_bound
            for item in snapshot.case_aggregations
            if isinstance(item, CaseScoreAggregation)
            and item.conservative_confidence_bound is not None
        )
        return min(values) if values else None


class RegressionDetector:
    def evaluate(
        self,
        comparison: EvalComparison,
        rule: RegressionRule,
        *,
        report_id: RegressionReportId,
        created_at: UtcTimestamp,
        expected_comparison_checksum: ContentChecksum | None = None,
        expected_report_checksum: ContentChecksum | None = None,
    ) -> RegressionReport:
        if expected_comparison_checksum is not None and comparison.checksum != expected_comparison_checksum:
            raise ComparisonFingerprintMismatch("comparison fingerprint mismatch")
        if rule.status is not DefinitionStatus.FROZEN:
            raise RegressionEvaluationFailure("regression rule must be frozen")
        outcomes: list[RegressionOutcome] = []
        reasons: set[str] = set()
        regressed_metrics: set[str] = set()
        improved_metrics = {
            item.metric_id
            for item in comparison.metric_deltas
            if item.direction is DeltaDirection.IMPROVED
        }
        critical_cases: set[EvalCaseVersionRef] = set()

        thresholds = {item.metric_id: item for item in rule.metric_thresholds}
        comparison_metrics = {item.metric_id for item in comparison.metric_deltas}
        for configured_threshold in rule.metric_thresholds:
            if comparison_metrics and configured_threshold.metric_id not in comparison_metrics:
                raise RegressionEvaluationFailure("regression rule metric is not comparable")
            if configured_threshold.direction is None:
                raise RegressionEvaluationFailure("regression rule metric direction is required")
        for delta in comparison.metric_deltas:
            threshold = thresholds.get(delta.metric_id)
            if threshold is not None and threshold.direction is not delta.metric_direction:
                raise RegressionEvaluationFailure("regression rule metric direction is incompatible")
            regressed = delta.direction is DeltaDirection.REGRESSED
            breach = False
            if threshold is not None:
                breach = (
                    threshold.minimum is not None and delta.current_value < threshold.minimum
                ) or (
                    threshold.maximum_regression is not None
                    and regressed
                    and abs(delta.delta) > threshold.maximum_regression
                )
            if breach:
                code = RegressionReasonCode.METRIC_THRESHOLD_REGRESSED
                outcomes.append(RegressionOutcome(code, ComparisonResult.REGRESSED, delta.metric_id))
                reasons.add(code.value)
                regressed_metrics.add(delta.metric_id)

        if comparison.overall_delta is not None:
            overall_breach = (
                rule.overall_minimum is not None
                and comparison.overall_delta.current_value < rule.overall_minimum
            ) or (
                rule.maximum_overall_regression is not None
                and comparison.overall_delta.direction is DeltaDirection.REGRESSED
                and abs(comparison.overall_delta.delta) > rule.maximum_overall_regression
            )
            if overall_breach:
                outcomes.append(
                    RegressionOutcome(RegressionReasonCode.OVERALL_REGRESSION, ComparisonResult.REGRESSED)
                )
                reasons.add(RegressionReasonCode.OVERALL_REGRESSION.value)

        for delta in comparison.case_deltas:
            if delta.case_reference not in rule.critical_cases:
                continue
            threshold = thresholds.get(delta.metric_id)
            limit = (
                threshold.maximum_regression
                if threshold is not None and threshold.maximum_regression is not None
                else rule.maximum_overall_regression
            )
            if delta.direction is DeltaDirection.REGRESSED and (limit is None or abs(delta.delta) > limit):
                outcomes.append(
                    RegressionOutcome(
                        RegressionReasonCode.CRITICAL_CASE_REGRESSED,
                        ComparisonResult.REGRESSED,
                        delta.metric_id,
                        delta.case_reference,
                    )
                )
                reasons.add(RegressionReasonCode.CRITICAL_CASE_REGRESSED.value)
                critical_cases.add(delta.case_reference)
                regressed_metrics.add(delta.metric_id)

        newly_failed = set(comparison.current_failed_required_cases) - set(
            comparison.baseline_failed_required_cases
        )
        for case in sorted(newly_failed, key=lambda item: (item.case_id.value, item.version.value)):
            if case in rule.mandatory_cases:
                outcomes.append(
                    RegressionOutcome(
                        RegressionReasonCode.REQUIRED_CASE_DEGRADED,
                        ComparisonResult.REGRESSED,
                        case_reference=case,
                    )
                )
                reasons.add(RegressionReasonCode.REQUIRED_CASE_DEGRADED.value)
                if case in rule.critical_cases:
                    critical_cases.add(case)

        for delta in comparison.case_deltas:
            statistical_breaches = (
                (
                    RegressionReasonCode.VARIANCE_INCREASED,
                    delta.variance_delta is not None
                    and rule.maximum_variance_increase is not None
                    and delta.variance_delta > rule.maximum_variance_increase,
                ),
                (
                    RegressionReasonCode.VARIANCE_LIMIT_EXCEEDED,
                    delta.current_variance is not None
                    and rule.maximum_variance is not None
                    and delta.current_variance > rule.maximum_variance,
                ),
                (
                    RegressionReasonCode.CONFIDENCE_REDUCED,
                    delta.confidence_delta is not None
                    and rule.maximum_confidence_reduction is not None
                    and delta.confidence_delta < -rule.maximum_confidence_reduction,
                ),
                (
                    RegressionReasonCode.CONFIDENCE_BELOW_REQUIRED,
                    delta.current_confidence is not None
                    and rule.required_confidence is not None
                    and delta.current_confidence < rule.required_confidence,
                ),
            )
            for code, breached in statistical_breaches:
                if not breached:
                    continue
                outcomes.append(
                    RegressionOutcome(
                        code,
                        ComparisonResult.REGRESSED,
                        delta.metric_id,
                        delta.case_reference,
                    )
                )
                reasons.add(code.value)
                regressed_metrics.add(delta.metric_id)
                if delta.case_reference in rule.critical_cases:
                    critical_cases.add(delta.case_reference)

        self._numeric_rule_outcomes(comparison, rule, outcomes, reasons)
        if rule.failure_budget_count is not None and comparison.failure_budget_unit != "count":
            raise RegressionEvaluationFailure("failure budget unit is incompatible")
        if rule.failure_budget_weight is not None and comparison.failure_budget_unit != "weight":
            raise RegressionEvaluationFailure("failure budget unit is incompatible")
        if (
            rule.failure_budget_count is not None
            and comparison.current_failure_budget_consumed is not None
            and comparison.current_failure_budget_consumed > Decimal(rule.failure_budget_count)
        ) or (
            rule.failure_budget_weight is not None
            and comparison.current_failure_budget_consumed is not None
            and comparison.current_failure_budget_consumed > rule.failure_budget_weight
        ):
            outcomes.append(
                RegressionOutcome(
                    RegressionReasonCode.FAILURE_BUDGET_EXCEEDED,
                    ComparisonResult.REGRESSED,
                )
            )
            reasons.add(RegressionReasonCode.FAILURE_BUDGET_EXCEEDED.value)
        if (
            rule.fail_on_verdict_degradation
            and comparison.baseline_verdict is not None
            and comparison.current_verdict is not None
            and _VERDICT_RANK[comparison.current_verdict] < _VERDICT_RANK[comparison.baseline_verdict]
        ):
            outcomes.append(
                RegressionOutcome(RegressionReasonCode.VERDICT_DEGRADED, ComparisonResult.REGRESSED)
            )
            reasons.add(RegressionReasonCode.VERDICT_DEGRADED.value)

        insufficient = self._insufficient(comparison, rule)
        if insufficient and not reasons:
            result = ComparisonResult.INSUFFICIENT_DATA
            reasons.update(insufficient)
        elif reasons:
            result = ComparisonResult.REGRESSED
        elif any(item.direction is DeltaDirection.IMPROVED for item in comparison.metric_deltas):
            result = ComparisonResult.IMPROVED
            outcomes.append(
                RegressionOutcome(RegressionReasonCode.RULES_SATISFIED, ComparisonResult.IMPROVED)
            )
        else:
            result = ComparisonResult.STABLE
            outcomes.append(
                RegressionOutcome(RegressionReasonCode.RULES_SATISFIED, ComparisonResult.STABLE)
            )

        ordered_outcomes = tuple(
            sorted(
                outcomes,
                key=lambda item: (
                    item.rule_code,
                    item.metric_id or "",
                    item.case_reference.case_id.value if item.case_reference else "",
                ),
            )
        )
        reason_codes = tuple(sorted(reasons))
        semantic = {
            "comparison": comparison.checksum,
            "rule": _rule_identity(rule),
            "rule_id": rule.rule_id,
            "rule_version": rule.version,
            "rule_checksum": rule.checksum,
            "result": result,
            "outcomes": ordered_outcomes,
            "reason_codes": reason_codes,
            "regressed_metrics": tuple(sorted(regressed_metrics)),
            "improved_metrics": tuple(sorted(improved_metrics)),
            "critical_regressions": tuple(
                sorted(critical_cases, key=lambda item: (item.case_id.value, item.version.value))
            ),
        }
        report_checksum = content_checksum(semantic)
        if expected_report_checksum is not None and report_checksum != expected_report_checksum:
            raise ReportFingerprintMismatch("report fingerprint mismatch")
        return RegressionReport(
            report_id=report_id,
            comparison_id=comparison.comparison_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            rule_checksum=rule.checksum,
            result=result,
            outcomes=ordered_outcomes,
            reason_codes=reason_codes,
            checksum=report_checksum,
            created_at=created_at,
            baseline_id=comparison.baseline_id,
            current_run_id=comparison.current_run_id,
            compatibility_fingerprint=comparison.compatibility_fingerprint,
            comparison_fingerprint=Fingerprint(comparison.checksum.value),
            regressed_metrics=tuple(sorted(regressed_metrics)),
            improved_metrics=tuple(sorted(improved_metrics)),
            critical_regressions=tuple(
                sorted(critical_cases, key=lambda item: (item.case_id.value, item.version.value))
            ),
            coverage_delta=comparison.coverage_delta,
            verdict_change=(
                (comparison.baseline_verdict, comparison.current_verdict)
                if comparison.baseline_verdict is not None
                and comparison.current_verdict is not None
                and comparison.baseline_verdict != comparison.current_verdict
                else None
            ),
            compatibility_status=comparison.compatibility_status,
        )

    @staticmethod
    def _numeric_rule_outcomes(
        comparison: EvalComparison,
        rule: RegressionRule,
        outcomes: list[RegressionOutcome],
        reasons: set[str],
    ) -> None:
        checks = (
            (
                RegressionReasonCode.COVERAGE_LOSS,
                comparison.coverage_delta is not None
                and rule.maximum_coverage_loss is not None
                and comparison.coverage_delta < -rule.maximum_coverage_loss,
            ),
            (
                RegressionReasonCode.VARIANCE_INCREASED,
                comparison.baseline_variance is not None
                and comparison.current_variance is not None
                and rule.maximum_variance_increase is not None
                and comparison.current_variance - comparison.baseline_variance
                > rule.maximum_variance_increase,
            ),
            (
                RegressionReasonCode.VARIANCE_LIMIT_EXCEEDED,
                comparison.current_variance is not None
                and rule.maximum_variance is not None
                and comparison.current_variance > rule.maximum_variance,
            ),
            (
                RegressionReasonCode.CONFIDENCE_REDUCED,
                comparison.baseline_confidence is not None
                and comparison.current_confidence is not None
                and rule.maximum_confidence_reduction is not None
                and comparison.baseline_confidence - comparison.current_confidence
                > rule.maximum_confidence_reduction,
            ),
            (
                RegressionReasonCode.CONFIDENCE_BELOW_REQUIRED,
                comparison.current_confidence is not None
                and rule.required_confidence is not None
                and comparison.current_confidence < rule.required_confidence,
            ),
        )
        for code, failed in checks:
            if failed:
                outcomes.append(RegressionOutcome(code, ComparisonResult.REGRESSED))
                reasons.add(code.value)

    @staticmethod
    def _insufficient(comparison: EvalComparison, rule: RegressionRule) -> set[str]:
        reasons: set[str] = set()
        if not comparison.metric_deltas or comparison.overall_delta is None:
            reasons.add(RegressionReasonCode.COMPARABLE_AGGREGATE_MISSING.value)
        if comparison.current_repetitions is None or comparison.current_repetitions < rule.minimum_repetitions:
            reasons.add(RegressionReasonCode.MINIMUM_REPETITIONS_NOT_MET.value)
        if rule.maximum_variance is not None and comparison.current_variance is None:
            reasons.add(RegressionReasonCode.VARIANCE_UNAVAILABLE.value)
        if rule.required_confidence is not None and comparison.current_confidence is None:
            reasons.add(RegressionReasonCode.CONFIDENCE_UNAVAILABLE.value)
        if rule.maximum_coverage_loss is not None and comparison.coverage_delta is None:
            reasons.add(RegressionReasonCode.COVERAGE_UNAVAILABLE.value)
        return reasons
