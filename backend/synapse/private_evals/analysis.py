from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .catalog import DatasetBindingRef, EvalCaseVersionRef, EvaluatorIdentity
from .errors import (
    DuplicateReference,
    InvalidBaseline,
    InvalidComparison,
    InvalidDelta,
    InvalidRegressionReport,
    InvalidRegressionRule,
    MissingBaselineAuthority,
)
from .states import BaselineStatus, ComparisonResult, DefinitionStatus, Verdict
from .values import (
    BaselineId,
    ComparisonId,
    ContentChecksum,
    EvalRunId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    RegressionReportId,
    RegressionRuleId,
    Revision,
    UtcTimestamp,
)

_SAFE_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class DeltaDirection(StrEnum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    INSUFFICIENT_DATA = "insufficient_data"


class CompatibilityStatus(StrEnum):
    COMPATIBLE = "compatible"
    CONDITIONALLY_COMPATIBLE = "conditionally_compatible"
    INCOMPATIBLE = "incompatible"


class CompatibilityDimension(StrEnum):
    SUITE_VERSION = "suite_version"
    SOURCE_FINGERPRINT = "source_fingerprint"
    MODEL_PROVIDER = "model_provider"
    SKILLS = "skills"
    TOOLS = "tools"


class CompatibilityReasonCode(StrEnum):
    EXACT_MATCH = "exact_match"
    CONTROLLED_DIFFERENCE = "controlled_difference"
    BLOCKING_DIFFERENCE = "blocking_difference"


class ComparisonReasonCode(StrEnum):
    REQUIRED_CASE_AGGREGATE_MISSING = "required_case_aggregate_missing"
    COMPARABLE_AGGREGATE_MISSING = "comparable_aggregate_missing"
    DIRECTED_REGRESSION_OBSERVED = "directed_regression_observed"
    NON_REGRESSIVE_CHANGE_OBSERVED = "all_observed_changes_non_regressive"
    ALL_METRICS_UNCHANGED = "all_comparable_metrics_unchanged"


class RegressionReasonCode(StrEnum):
    METRIC_THRESHOLD_REGRESSED = "metric_threshold_regressed"
    OVERALL_REGRESSION = "overall_regression"
    CRITICAL_CASE_REGRESSED = "critical_case_regressed"
    REQUIRED_CASE_DEGRADED = "required_case_degraded"
    COVERAGE_LOSS = "coverage_loss"
    VARIANCE_INCREASED = "variance_increased"
    VARIANCE_LIMIT_EXCEEDED = "variance_limit_exceeded"
    CONFIDENCE_REDUCED = "confidence_reduced"
    CONFIDENCE_BELOW_REQUIRED = "confidence_below_required"
    FAILURE_BUDGET_EXCEEDED = "failure_budget_exceeded"
    VERDICT_DEGRADED = "verdict_degraded"
    COMPARABLE_AGGREGATE_MISSING = "comparable_aggregate_missing"
    MINIMUM_REPETITIONS_NOT_MET = "minimum_repetitions_not_met"
    VARIANCE_UNAVAILABLE = "variance_unavailable"
    CONFIDENCE_UNAVAILABLE = "confidence_unavailable"
    COVERAGE_UNAVAILABLE = "coverage_unavailable"
    RULES_SATISFIED = "rules_satisfied"


@dataclass(frozen=True)
class CompatibilityPolicy:
    policy_id: str
    version: EvalVersion
    allowed_dimensions: tuple[CompatibilityDimension, ...]

    def __post_init__(self) -> None:
        _require_code(self.policy_id, "compatibility policy ID", InvalidComparison)
        _require_type(self.version, EvalVersion, "compatibility policy version", InvalidComparison)
        if not self.allowed_dimensions or any(
            not isinstance(item, CompatibilityDimension) for item in self.allowed_dimensions
        ):
            raise InvalidComparison("compatibility policy requires typed dimensions")
        _unique(self.allowed_dimensions, "compatibility policy dimension")
        object.__setattr__(
            self,
            "allowed_dimensions",
            tuple(sorted(self.allowed_dimensions, key=lambda item: item.value)),
        )

    @property
    def policy_fingerprint(self) -> Fingerprint:
        from .canonical import fingerprint

        return fingerprint(
            {
                "policy_id": self.policy_id,
                "version": self.version,
                "allowed_dimensions": self.allowed_dimensions,
            }
        )


@dataclass(frozen=True)
class BaselineEligibilityPolicy:
    allow_inconclusive_research: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allow_inconclusive_research, bool):
            raise InvalidBaseline("baseline eligibility policy must be typed")


@dataclass(frozen=True)
class MetricDirectionSpec:
    metric_id: str
    direction: MetricDirection

    def __post_init__(self) -> None:
        _require_code(self.metric_id, "metric_id", InvalidComparison)
        _require_type(self.direction, MetricDirection, "metric direction", InvalidComparison)
        object.__setattr__(self, "metric_id", self.metric_id.strip().casefold())


@dataclass(frozen=True)
class BaselineAggregateSnapshot:
    case_aggregations: tuple[Any, ...]
    metric_aggregations: tuple[tuple[str, Decimal], ...]
    overall_normalized_score: Decimal | None
    valid_score_count: int
    missing_score_count: int
    expected_repetitions: int
    failure_budget_consumed: Decimal


@dataclass(frozen=True)
class BaselineCompatibilitySnapshot:
    case_references: tuple[EvalCaseVersionRef, ...]
    dataset_binding: DatasetBindingRef
    evaluator: EvaluatorIdentity
    scoring_protocol_checksum: ContentChecksum
    model_provider_fingerprint: Fingerprint | None
    execution_protocol_fingerprint: Fingerprint
    skill_fingerprint: Fingerprint
    tool_fingerprint: Fingerprint
    security_fingerprint: Fingerprint
    source_fingerprint: Fingerprint


@dataclass(frozen=True)
class CompatibilityResult:
    status: CompatibilityStatus
    reason_codes: tuple[CompatibilityReasonCode, ...]
    allowed_differences: tuple[str, ...]
    blocking_differences: tuple[str, ...]
    fingerprint: Fingerprint
    condition_policy_fingerprint: Fingerprint | None = None

    @property
    def compatible(self) -> bool:
        return self.status is not CompatibilityStatus.INCOMPATIBLE

    def __repr__(self) -> str:
        return (
            "CompatibilityResult("
            f"status={self.status!r}, reason_codes={self.reason_codes!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def _require_text(value: str, field_name: str, error_type: type[ValueError]) -> None:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be non-empty")


def _require_code(value: str, field_name: str, error_type: type[ValueError]) -> None:
    if not isinstance(value, str) or not _SAFE_CODE.fullmatch(value):
        raise error_type(f"{field_name} must be a safe canonical code")


def _require_type(
    value: object,
    expected: type | tuple[type, ...],
    field_name: str,
    error_type: type[ValueError],
) -> None:
    if not isinstance(value, expected):
        raise error_type(f"{field_name} has an invalid type")


def _unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise DuplicateReference(f"duplicate {label} reference")


@dataclass(frozen=True)
class ComparisonScope:
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    scope_id: str
    controlled_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_type(self.suite_id, EvalSuiteId, "suite_id", InvalidBaseline)
        _require_type(self.suite_version, EvalVersion, "suite version", InvalidBaseline)
        _require_code(self.scope_id, "comparison scope", InvalidBaseline)
        if not self.controlled_dimensions:
            raise InvalidBaseline("comparison scope requires a controlled dimension")
        normalized = tuple(value.strip().casefold() for value in self.controlled_dimensions)
        if any(not value for value in normalized):
            raise InvalidBaseline("controlled dimensions must be non-empty")
        if any(not _SAFE_CODE.fullmatch(value) for value in normalized):
            raise InvalidBaseline("controlled dimensions must be safe canonical codes")
        _unique(normalized, "controlled dimension")
        object.__setattr__(self, "controlled_dimensions", tuple(sorted(normalized)))


@dataclass(frozen=True)
class EvalBaseline:
    baseline_id: BaselineId
    scope: ComparisonScope
    source_run_id: EvalRunId
    source_run_verdict: Verdict
    run_fingerprint: Fingerprint
    finalization_checksum: ContentChecksum
    protocol_fingerprint: Fingerprint
    subject_fingerprint: Fingerprint
    compatibility_signature: Fingerprint
    summary_checksum: ContentChecksum
    status: BaselineStatus
    content_checksum: ContentChecksum
    revision: Revision
    governance_binding_reference: str | None
    created_at: UtcTimestamp
    decision_fingerprint: Fingerprint | None = None
    aggregates: BaselineAggregateSnapshot | None = None
    compatibility: BaselineCompatibilitySnapshot | None = None
    compatibility_policy: CompatibilityPolicy | None = None
    eligibility_policy: BaselineEligibilityPolicy = BaselineEligibilityPolicy()

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.baseline_id, BaselineId, "baseline_id"),
            (self.scope, ComparisonScope, "comparison scope"),
            (self.source_run_id, EvalRunId, "source run_id"),
            (self.source_run_verdict, Verdict, "source run verdict"),
            (self.run_fingerprint, Fingerprint, "run fingerprint"),
            (self.finalization_checksum, ContentChecksum, "finalization checksum"),
            (self.protocol_fingerprint, Fingerprint, "protocol fingerprint"),
            (self.subject_fingerprint, Fingerprint, "subject fingerprint"),
            (self.compatibility_signature, Fingerprint, "compatibility signature"),
            (self.summary_checksum, ContentChecksum, "summary checksum"),
            (self.status, BaselineStatus, "baseline status"),
            (self.content_checksum, ContentChecksum, "baseline checksum"),
            (self.revision, Revision, "baseline revision"),
            (self.created_at, UtcTimestamp, "created_at"),
        ):
            _require_type(value, expected, name, InvalidBaseline)
        if self.source_run_verdict not in {Verdict.PASSED, Verdict.INCONCLUSIVE}:
            raise InvalidBaseline("baseline source run is not eligible")
        _require_type(
            self.eligibility_policy,
            BaselineEligibilityPolicy,
            "baseline eligibility policy",
            InvalidBaseline,
        )
        if (
            self.source_run_verdict is Verdict.INCONCLUSIVE
            and not self.eligibility_policy.allow_inconclusive_research
        ):
            raise InvalidBaseline("inconclusive baseline requires explicit research permission")
        if self.compatibility_policy is not None:
            _require_type(
                self.compatibility_policy,
                CompatibilityPolicy,
                "compatibility policy",
                InvalidBaseline,
            )
        if self.status is not BaselineStatus.CANDIDATE:
            if not self.governance_binding_reference:
                raise MissingBaselineAuthority("baseline authority reference is required")

    def __repr__(self) -> str:
        return (
            "EvalBaseline("
            f"baseline_id={self.baseline_id!r}, source_run_id={self.source_run_id!r}, "
            f"status={self.status!r}, content_checksum={self.content_checksum!r})"
        )


@dataclass(frozen=True)
class MetricDelta:
    metric_id: str
    baseline_value: Decimal
    current_value: Decimal
    delta: Decimal
    normalized_delta: Decimal | None = None
    direction: DeltaDirection | None = None
    case_reference: EvalCaseVersionRef | None = None
    metric_direction: MetricDirection | None = None
    baseline_variance: Decimal | None = None
    current_variance: Decimal | None = None
    variance_delta: Decimal | None = None
    baseline_confidence: Decimal | None = None
    current_confidence: Decimal | None = None
    confidence_delta: Decimal | None = None
    confidence_method: str | None = None

    def __post_init__(self) -> None:
        _require_code(self.metric_id, "metric_id", InvalidDelta)
        if any(
            not isinstance(value, Decimal)
            for value in (self.baseline_value, self.current_value, self.delta)
        ):
            raise InvalidDelta("comparison metric values must be Decimal values")
        if any(
            not value.is_finite()
            for value in (self.baseline_value, self.current_value, self.delta)
        ):
            raise InvalidDelta("comparison metric values must be finite")
        if self.current_value - self.baseline_value != self.delta:
            raise InvalidDelta("metric delta does not match its values")
        if self.normalized_delta is not None and not self.normalized_delta.is_finite():
            raise InvalidDelta("normalized metric delta must be finite")
        if self.direction is not None:
            _require_type(self.direction, DeltaDirection, "delta direction", InvalidComparison)
        if self.metric_direction is not None:
            _require_type(
                self.metric_direction,
                MetricDirection,
                "configured metric direction",
                InvalidDelta,
            )
        statistical_values = (
            self.baseline_variance,
            self.current_variance,
            self.variance_delta,
            self.baseline_confidence,
            self.current_confidence,
            self.confidence_delta,
        )
        if any(value is not None and (not isinstance(value, Decimal) or not value.is_finite()) for value in statistical_values):
            raise InvalidDelta("statistical delta values must be finite Decimal values")


@dataclass(frozen=True)
class EvalComparison:
    comparison_id: ComparisonId
    current_run_id: EvalRunId
    baseline_id: BaselineId
    baseline_run_id: EvalRunId
    scope: ComparisonScope
    current_protocol_fingerprint: Fingerprint
    baseline_protocol_fingerprint: Fingerprint
    allowed_differences: tuple[str, ...]
    result: ComparisonResult
    metric_deltas: tuple[MetricDelta, ...]
    reason_codes: tuple[str, ...]
    checksum: ContentChecksum
    created_at: UtcTimestamp
    compatibility_fingerprint: Fingerprint | None = None
    case_deltas: tuple[MetricDelta, ...] = ()
    overall_delta: MetricDelta | None = None
    baseline_verdict: Verdict | None = None
    current_verdict: Verdict | None = None
    baseline_coverage: Decimal | None = None
    current_coverage: Decimal | None = None
    coverage_delta: Decimal | None = None
    baseline_variance: Decimal | None = None
    current_variance: Decimal | None = None
    baseline_confidence: Decimal | None = None
    current_confidence: Decimal | None = None
    current_repetitions: int | None = None
    baseline_failed_required_cases: tuple[EvalCaseVersionRef, ...] = ()
    current_failed_required_cases: tuple[EvalCaseVersionRef, ...] = ()
    baseline_failure_budget_consumed: Decimal | None = None
    current_failure_budget_consumed: Decimal | None = None
    variance_delta: Decimal | None = None
    confidence_delta: Decimal | None = None
    compatibility_status: CompatibilityStatus | None = None
    failure_budget_unit: str | None = None

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.comparison_id, ComparisonId, "comparison_id"),
            (self.current_run_id, EvalRunId, "current run_id"),
            (self.baseline_id, BaselineId, "baseline_id"),
            (self.baseline_run_id, EvalRunId, "baseline run_id"),
            (self.scope, ComparisonScope, "comparison scope"),
            (self.current_protocol_fingerprint, Fingerprint, "current protocol fingerprint"),
            (self.baseline_protocol_fingerprint, Fingerprint, "baseline protocol fingerprint"),
            (self.result, ComparisonResult, "comparison result"),
            (self.checksum, ContentChecksum, "comparison checksum"),
            (self.created_at, UtcTimestamp, "created_at"),
        ):
            _require_type(value, expected, name, InvalidComparison)
        if any(not isinstance(value, MetricDelta) for value in self.metric_deltas):
            raise InvalidComparison("metric deltas must be typed")
        if any(not isinstance(value, MetricDelta) for value in self.case_deltas):
            raise InvalidComparison("case deltas must be typed")
        if self.current_run_id == self.baseline_run_id:
            raise InvalidComparison("a run cannot be compared with itself")
        normalized = tuple(value.strip().casefold() for value in self.allowed_differences)
        if any(not value for value in normalized):
            raise InvalidComparison("allowed differences must be non-empty")
        if any(not _SAFE_CODE.fullmatch(value) for value in normalized):
            raise InvalidComparison("allowed differences must be safe canonical codes")
        _unique(normalized, "allowed difference")
        object.__setattr__(self, "allowed_differences", normalized)
        metric_ids = tuple(delta.metric_id for delta in self.metric_deltas)
        _unique(metric_ids, "comparison metric")
        if self.result is ComparisonResult.INCOMPATIBLE:
            if self.metric_deltas:
                raise InvalidComparison("incompatible comparison cannot contain metric deltas")
            if not self.reason_codes:
                raise InvalidComparison("incompatible comparison requires a reason code")
        elif self.current_protocol_fingerprint != self.baseline_protocol_fingerprint and not (
            self.allowed_differences
        ):
            raise InvalidComparison(
                "different protocol fingerprints require declared compatibility dimensions"
            )
        if any(not _SAFE_CODE.fullmatch(str(code)) for code in self.reason_codes):
            raise InvalidComparison("comparison reason codes must be safe canonical codes")


@dataclass(frozen=True)
class MetricThreshold:
    metric_id: str
    minimum: Decimal | None = None
    maximum_regression: Decimal | None = None
    direction: MetricDirection | None = None

    def __post_init__(self) -> None:
        _require_code(self.metric_id, "metric_id", InvalidRegressionRule)
        if any(
            value is not None and not isinstance(value, Decimal)
            for value in (self.minimum, self.maximum_regression)
        ):
            raise InvalidRegressionRule("metric thresholds must be Decimal values")
        if self.minimum is None and self.maximum_regression is None:
            raise InvalidRegressionRule("metric threshold requires a limit")
        for value in (self.minimum, self.maximum_regression):
            if value is not None and not value.is_finite():
                raise InvalidRegressionRule("metric thresholds must be finite")
        if self.minimum is not None and not Decimal("0") <= self.minimum <= Decimal("1"):
            raise InvalidRegressionRule("normalized metric minimum must be in [0, 1]")
        if self.maximum_regression is not None and self.maximum_regression < 0:
            raise InvalidRegressionRule("maximum regression cannot be negative")
        if self.direction is not None:
            _require_type(self.direction, MetricDirection, "metric direction", InvalidRegressionRule)


@dataclass(frozen=True)
class RegressionRule:
    rule_id: RegressionRuleId
    version: EvalVersion
    status: DefinitionStatus
    overall_minimum: Decimal | None
    maximum_overall_regression: Decimal | None
    metric_thresholds: tuple[MetricThreshold, ...]
    mandatory_cases: tuple[EvalCaseVersionRef, ...]
    critical_cases: tuple[EvalCaseVersionRef, ...]
    failure_budget_count: int | None
    failure_budget_weight: Decimal | None
    minimum_repetitions: int
    maximum_variance: Decimal | None
    required_confidence: Decimal | None
    checksum: ContentChecksum
    maximum_coverage_loss: Decimal | None = None
    maximum_variance_increase: Decimal | None = None
    maximum_confidence_reduction: Decimal | None = None
    fail_on_verdict_degradation: bool = True

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.rule_id, RegressionRuleId, "rule_id"),
            (self.version, EvalVersion, "rule version"),
            (self.status, DefinitionStatus, "rule status"),
            (self.checksum, ContentChecksum, "rule checksum"),
        ):
            _require_type(value, expected, name, InvalidRegressionRule)
        if any(not isinstance(value, MetricThreshold) for value in self.metric_thresholds):
            raise InvalidRegressionRule("metric thresholds must be typed")
        if any(not isinstance(value, EvalCaseVersionRef) for value in self.mandatory_cases):
            raise InvalidRegressionRule("mandatory cases must be typed")
        if any(not isinstance(value, EvalCaseVersionRef) for value in self.critical_cases):
            raise InvalidRegressionRule("critical cases must be typed")
        decimal_values = (
            self.overall_minimum,
            self.maximum_overall_regression,
            self.failure_budget_weight,
            self.maximum_variance,
            self.required_confidence,
            self.maximum_coverage_loss,
            self.maximum_variance_increase,
            self.maximum_confidence_reduction,
        )
        if any(value is not None and not isinstance(value, Decimal) for value in decimal_values):
            raise InvalidRegressionRule("regression numeric limits must be Decimal values")
        metric_ids = tuple(item.metric_id for item in self.metric_thresholds)
        _unique(metric_ids, "metric threshold")
        _unique(self.mandatory_cases, "mandatory case")
        _unique(self.critical_cases, "critical case")
        if not set(self.critical_cases) <= set(self.mandatory_cases):
            raise InvalidRegressionRule("critical cases must also be mandatory")
        for threshold, label in (
            (self.overall_minimum, "overall minimum"),
            (self.required_confidence, "required confidence"),
        ):
            if threshold is not None and (
                not threshold.is_finite()
                or not Decimal("0") <= threshold <= Decimal("1")
            ):
                raise InvalidRegressionRule(f"{label} must be in [0, 1]")
        if self.maximum_overall_regression is not None and (
            not self.maximum_overall_regression.is_finite()
            or self.maximum_overall_regression < 0
        ):
            raise InvalidRegressionRule("maximum overall regression cannot be negative")
        if self.failure_budget_count is not None and (
            isinstance(self.failure_budget_count, bool) or self.failure_budget_count < 0
        ):
            raise InvalidRegressionRule("failure budget count cannot be negative")
        if self.failure_budget_weight is not None and (
            not self.failure_budget_weight.is_finite() or self.failure_budget_weight < 0
        ):
            raise InvalidRegressionRule("failure budget weight cannot be negative")
        if self.failure_budget_count is not None and self.failure_budget_weight is not None:
            raise InvalidRegressionRule("failure budget must use count or weight, not both")
        if isinstance(self.minimum_repetitions, bool) or self.minimum_repetitions < 1:
            raise InvalidRegressionRule("minimum repetitions must be positive")
        if self.maximum_variance is not None and (
            not self.maximum_variance.is_finite() or self.maximum_variance < 0
        ):
            raise InvalidRegressionRule("maximum variance cannot be negative")
        for threshold_value, label in (
            (self.maximum_coverage_loss, "maximum coverage loss"),
            (self.maximum_variance_increase, "maximum variance increase"),
            (self.maximum_confidence_reduction, "maximum confidence reduction"),
        ):
            if threshold_value is not None and (
                not threshold_value.is_finite() or threshold_value < 0
            ):
                raise InvalidRegressionRule(f"{label} must be finite and non-negative")
        has_non_global_rule = bool(
            self.metric_thresholds
            or self.mandatory_cases
            or self.critical_cases
            or self.failure_budget_count is not None
            or self.failure_budget_weight is not None
            or self.maximum_variance is not None
            or self.required_confidence is not None
            or self.maximum_coverage_loss is not None
            or self.maximum_variance_increase is not None
            or self.maximum_confidence_reduction is not None
            or self.minimum_repetitions > 1
        )
        if not has_non_global_rule:
            raise InvalidRegressionRule("regression rule cannot depend only on a global mean")


@dataclass(frozen=True)
class RegressionOutcome:
    rule_code: str
    result: ComparisonResult
    metric_id: str | None = None
    case_reference: EvalCaseVersionRef | None = None

    def __post_init__(self) -> None:
        _require_type(self.result, ComparisonResult, "regression result", InvalidRegressionReport)
        if self.case_reference is not None:
            _require_type(
                self.case_reference,
                EvalCaseVersionRef,
                "case reference",
                InvalidRegressionReport,
            )
        _require_code(str(self.rule_code), "regression rule code", InvalidRegressionReport)


@dataclass(frozen=True)
class RegressionReport:
    report_id: RegressionReportId
    comparison_id: ComparisonId
    rule_id: RegressionRuleId
    rule_version: EvalVersion
    rule_checksum: ContentChecksum
    result: ComparisonResult
    outcomes: tuple[RegressionOutcome, ...]
    reason_codes: tuple[str, ...]
    checksum: ContentChecksum
    created_at: UtcTimestamp
    baseline_id: BaselineId | None = None
    current_run_id: EvalRunId | None = None
    compatibility_fingerprint: Fingerprint | None = None
    comparison_fingerprint: Fingerprint | None = None
    regressed_metrics: tuple[str, ...] = ()
    improved_metrics: tuple[str, ...] = ()
    critical_regressions: tuple[EvalCaseVersionRef, ...] = ()
    coverage_delta: Decimal | None = None
    verdict_change: tuple[Verdict, Verdict] | None = None
    compatibility_status: CompatibilityStatus | None = None

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.report_id, RegressionReportId, "report_id"),
            (self.comparison_id, ComparisonId, "comparison_id"),
            (self.rule_id, RegressionRuleId, "rule_id"),
            (self.rule_version, EvalVersion, "rule version"),
            (self.rule_checksum, ContentChecksum, "rule checksum"),
            (self.result, ComparisonResult, "regression result"),
            (self.checksum, ContentChecksum, "report checksum"),
            (self.created_at, UtcTimestamp, "created_at"),
        ):
            _require_type(value, expected, name, InvalidRegressionReport)
        if any(not isinstance(value, RegressionOutcome) for value in self.outcomes):
            raise InvalidRegressionReport("regression outcomes must be typed")
        if not self.outcomes and self.result not in {
            ComparisonResult.INCOMPATIBLE,
            ComparisonResult.INSUFFICIENT_DATA,
        }:
            raise InvalidRegressionReport("regression report requires rule outcomes")
        if self.result in {
            ComparisonResult.INCOMPATIBLE,
            ComparisonResult.INSUFFICIENT_DATA,
        } and not self.reason_codes:
            raise InvalidRegressionReport("non-comparable report requires a reason code")
        if any(not _SAFE_CODE.fullmatch(str(code)) for code in self.reason_codes):
            raise InvalidRegressionReport("regression reason codes must be safe canonical codes")

    def __repr__(self) -> str:
        return (
            "RegressionReport("
            f"report_id={self.report_id!r}, comparison_id={self.comparison_id!r}, "
            f"result={self.result!r}, checksum={self.checksum!r})"
        )
