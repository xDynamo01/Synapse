from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum

from .canonical import fingerprint
from .catalog import EvalCaseVersionRef, EvaluatorIdentity
from .runs import Score
from .scoring_errors import (
    DecisionFingerprintMismatch,
    DuplicateRepetition,
    EvaluatorMismatch,
    IncompatibleConfidenceMethod,
    IncompatibleMetric,
    IncompatibleScale,
    InvalidFailureBudget,
    InvalidScoringInput,
    InvalidScoringWeight,
    ThresholdMismatch,
)
from .states import DeterminismMode, ResultStatus, ScoreKind, ScoreStatus, Verdict
from .values import EvalRunId, EvalSuiteId, EvalVersion, Fingerprint

_QUANTUM = Decimal("0.000000000001")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _q(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        context.rounding = ROUND_HALF_EVEN
        return value.quantize(_QUANTUM)


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        context.rounding = ROUND_HALF_EVEN
        return _q(sum(values, Decimal("0")) / Decimal(len(values)))


class AggregationMethod(StrEnum):
    ARITHMETIC_MEAN = "arithmetic_mean"


class ThresholdScope(StrEnum):
    CASE = "case"
    METRIC = "metric"
    GLOBAL = "global"


class ThresholdOperator(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    BETWEEN = "between"


class FailureBudgetUnit(StrEnum):
    COUNT = "count"
    WEIGHT = "weight"


class ScoringReasonCode(StrEnum):
    INVALID_SCORING_INPUT = "invalid_scoring_input"
    POLICY_DENIED = "policy_denied"
    EXTERNAL_PREREQUISITE_BLOCKED = "external_prerequisite_blocked"
    REQUIRED_CASE_THRESHOLD_FAILED = "required_case_threshold_failed"
    FAILURE_BUDGET_EXCEEDED = "failure_budget_exceeded"
    AGGREGATE_THRESHOLD_FAILED = "aggregate_threshold_failed"
    REQUIRED_REPETITION_MISSING = "required_repetition_missing"
    REQUIRED_SCORE_MISSING = "required_score_missing"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    EXECUTION_CANCELLED = "execution_cancelled"
    INSUFFICIENT_STATISTICS = "insufficient_statistics"
    NO_SCOREABLE_DATA = "no_scoreable_data"
    ALL_SCORING_RULES_SATISFIED = "all_scoring_rules_satisfied"


@dataclass(frozen=True)
class ScoringTarget:
    case_reference: EvalCaseVersionRef
    metric_id: str
    evaluator: EvaluatorIdentity
    weight: Decimal
    required: bool
    critical: bool

    def __post_init__(self) -> None:
        if not isinstance(self.metric_id, str) or not _SAFE_IDENTIFIER.fullmatch(
            self.metric_id.strip()
        ):
            raise InvalidScoringInput()
        if not isinstance(self.weight, Decimal) or not self.weight.is_finite() or self.weight <= 0:
            raise InvalidScoringWeight()
        if self.critical and not self.required:
            raise InvalidScoringInput()
        if not _SAFE_IDENTIFIER.fullmatch(self.evaluator.kind):
            raise InvalidScoringInput()
        object.__setattr__(self, "metric_id", self.metric_id.strip().casefold())


@dataclass(frozen=True)
class ScoringObservation:
    run_id: EvalRunId
    case_reference: EvalCaseVersionRef
    repetition: int
    result_status: ResultStatus
    scores: tuple[Score, ...]
    result_fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        if isinstance(self.repetition, bool) or not isinstance(self.repetition, int) or self.repetition < 1:
            raise InvalidScoringInput()
        if not isinstance(self.result_status, ResultStatus):
            raise InvalidScoringInput()
        if not isinstance(self.scores, tuple) or any(
            not isinstance(score, Score) for score in self.scores
        ):
            raise InvalidScoringInput()
        if self.result_fingerprint is not None and not isinstance(
            self.result_fingerprint, Fingerprint
        ):
            raise InvalidScoringInput()
        metrics = tuple(score.metric_id.casefold() for score in self.scores)
        if len(metrics) != len(set(metrics)):
            raise IncompatibleMetric()
        if self.result_status is not ResultStatus.VALID and self.scores:
            raise InvalidScoringInput()


@dataclass(frozen=True)
class ScoreThreshold:
    scope: ThresholdScope
    operator: ThresholdOperator
    lower: Decimal | None = None
    upper: Decimal | None = None
    metric_id: str | None = None
    case_reference: EvalCaseVersionRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ThresholdScope) or not isinstance(
            self.operator, ThresholdOperator
        ):
            raise ThresholdMismatch()
        for value in (self.lower, self.upper):
            if value is not None and (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or not Decimal("0") <= value <= Decimal("1")
            ):
                raise ThresholdMismatch()
        if self.operator is ThresholdOperator.AT_LEAST and (
            self.lower is None or self.upper is not None
        ):
            raise ThresholdMismatch()
        if self.operator is ThresholdOperator.AT_MOST and (
            self.upper is None or self.lower is not None
        ):
            raise ThresholdMismatch()
        if self.operator is ThresholdOperator.BETWEEN and (
            self.lower is None
            or self.upper is None
            or self.lower > self.upper
        ):
            raise ThresholdMismatch()
        metric = self.metric_id.strip().casefold() if isinstance(self.metric_id, str) else None
        if self.scope is ThresholdScope.CASE and (
            self.case_reference is None or not metric
        ):
            raise ThresholdMismatch()
        if self.scope is ThresholdScope.METRIC and (
            self.case_reference is not None or not metric
        ):
            raise ThresholdMismatch()
        if self.scope is ThresholdScope.GLOBAL and (
            self.case_reference is not None or self.metric_id is not None
        ):
            raise ThresholdMismatch()
        object.__setattr__(self, "metric_id", metric)

    def accepts(self, value: Decimal) -> bool:
        if self.operator is ThresholdOperator.AT_LEAST:
            assert self.lower is not None
            return value >= self.lower
        if self.operator is ThresholdOperator.AT_MOST:
            assert self.upper is not None
            return value <= self.upper
        assert self.lower is not None and self.upper is not None
        return self.lower <= value <= self.upper


@dataclass(frozen=True)
class FailureBudget:
    unit: FailureBudgetUnit
    count_limit: int | None = None
    weight_limit: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.unit, FailureBudgetUnit):
            raise InvalidFailureBudget()
        if self.unit is FailureBudgetUnit.COUNT:
            if (
                isinstance(self.count_limit, bool)
                or not isinstance(self.count_limit, int)
                or self.count_limit < 0
                or self.weight_limit is not None
            ):
                raise InvalidFailureBudget()
        elif (
            self.count_limit is not None
            or not isinstance(self.weight_limit, Decimal)
            or not self.weight_limit.is_finite()
            or self.weight_limit < 0
        ):
            raise InvalidFailureBudget()


@dataclass(frozen=True)
class ScoringProtocol:
    run_id: EvalRunId
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    targets: tuple[ScoringTarget, ...]
    expected_repetitions: int
    minimum_repetitions: int
    determinism_mode: DeterminismMode
    aggregation_method: AggregationMethod
    thresholds: tuple[ScoreThreshold, ...]
    failure_budget: FailureBudget
    maximum_variance: Decimal | None = None
    required_confidence: Decimal | None = None
    blocked_cases: tuple[EvalCaseVersionRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.targets, tuple) or not self.targets:
            raise InvalidScoringInput()
        if any(not isinstance(target, ScoringTarget) for target in self.targets):
            raise InvalidScoringInput()
        identities = tuple(item.case_reference for item in self.targets)
        if len(identities) != len(set(identities)):
            raise InvalidScoringInput()
        if any(target.case_reference.suite_id != self.suite_id for target in self.targets):
            raise InvalidScoringInput()
        if (
            isinstance(self.expected_repetitions, bool)
            or not isinstance(self.expected_repetitions, int)
            or self.expected_repetitions < 1
            or isinstance(self.minimum_repetitions, bool)
            or not isinstance(self.minimum_repetitions, int)
            or not 1 <= self.minimum_repetitions <= self.expected_repetitions
        ):
            raise InvalidScoringInput()
        if not isinstance(self.determinism_mode, DeterminismMode) or not isinstance(
            self.aggregation_method, AggregationMethod
        ):
            raise InvalidScoringInput()
        for value in (self.maximum_variance, self.required_confidence):
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value < 0
            ):
                raise InvalidScoringInput()
        if self.required_confidence is not None and self.required_confidence > 1:
            raise InvalidScoringInput()
        threshold_keys = tuple(
            (item.scope, item.case_reference, item.metric_id) for item in self.thresholds
        )
        if len(threshold_keys) != len(set(threshold_keys)):
            raise ThresholdMismatch()
        if not isinstance(self.thresholds, tuple) or any(
            not isinstance(item, ScoreThreshold) for item in self.thresholds
        ):
            raise ThresholdMismatch()
        if not isinstance(self.failure_budget, FailureBudget):
            raise InvalidFailureBudget()
        identity_set = {
            (item.case_reference, item.metric_id) for item in self.targets
        }
        metric_set = {item.metric_id for item in self.targets}
        for threshold in self.thresholds:
            if threshold.scope is ThresholdScope.CASE and (
                threshold.case_reference,
                threshold.metric_id,
            ) not in identity_set:
                raise ThresholdMismatch()
            if (
                threshold.scope is ThresholdScope.METRIC
                and threshold.metric_id not in metric_set
            ):
                raise ThresholdMismatch()
        target_refs = {item.case_reference for item in self.targets}
        if not isinstance(self.blocked_cases, tuple) or (
            len(self.blocked_cases) != len(set(self.blocked_cases))
            or not set(self.blocked_cases) <= target_refs
        ):
            raise InvalidScoringInput()


@dataclass(frozen=True)
class CaseScoreAggregation:
    case_reference: EvalCaseVersionRef
    metric_id: str
    evaluator: EvaluatorIdentity
    normalized_mean: Decimal
    normalized_minimum: Decimal
    normalized_maximum: Decimal
    raw_mean: Decimal
    scale_minimum: Decimal
    scale_maximum: Decimal
    score_kind: ScoreKind
    binary_success_rate: Decimal | None
    sample_count: int
    sample_variance: Decimal | None
    conservative_confidence_bound: Decimal | None
    confidence_projection_method: str | None
    weight: Decimal
    required: bool
    critical: bool
    threshold_passed: bool | None


@dataclass(frozen=True)
class FailureBudgetOutcome:
    unit: FailureBudgetUnit
    available: Decimal
    consumed: Decimal
    responsible_cases: tuple[EvalCaseVersionRef, ...]
    within_budget: bool


@dataclass(frozen=True)
class ScoringDecision:
    run_id: EvalRunId
    verdict: Verdict
    reason_codes: tuple[ScoringReasonCode, ...]
    case_aggregations: tuple[CaseScoreAggregation, ...]
    metric_aggregations: tuple[tuple[str, Decimal], ...]
    overall_normalized_score: Decimal | None
    failure_budget: FailureBudgetOutcome
    valid_score_count: int
    missing_score_count: int
    missing_repetition_count: int
    explicit_missing_score_count: int
    infrastructure_failure_count: int
    cancelled_observation_count: int
    policy_denial_count: int
    invalid_result_count: int
    failed_required_cases: tuple[EvalCaseVersionRef, ...]
    decision_fingerprint: Fingerprint

    def __repr__(self) -> str:
        return (
            "ScoringDecision("
            f"run_id={self.run_id!r}, verdict={self.verdict!r}, "
            f"reason_codes={self.reason_codes!r}, "
            f"decision_fingerprint={self.decision_fingerprint!r})"
        )


class ScoringEngine:
    """Pure deterministic aggregation and verdict derivation over supplied observations."""

    def score(
        self,
        protocol: ScoringProtocol,
        observations: tuple[ScoringObservation, ...],
    ) -> ScoringDecision:
        if not isinstance(observations, tuple):
            raise InvalidScoringInput()
        observation_map = self._validate_observations(protocol, observations)
        aggregations: list[CaseScoreAggregation] = []
        missing_required = False
        missing_repetition_required = False
        explicit_missing_required = False
        invalid_count = 0
        policy_count = 0
        infrastructure_count = 0
        cancelled_count = 0
        missing_count = 0
        missing_repetition_count = 0
        explicit_missing_count = 0
        valid_count = 0
        insufficient_statistics = False

        case_thresholds = {
            (item.case_reference, item.metric_id): item
            for item in protocol.thresholds
            if item.scope is ThresholdScope.CASE
        }
        for target in sorted(
            protocol.targets,
            key=lambda item: (
                item.case_reference.case_id.value,
                item.case_reference.version.value,
                item.metric_id,
            ),
        ):
            scores: list[Score] = []
            for repetition in range(1, protocol.expected_repetitions + 1):
                observation = observation_map.get((target.case_reference, repetition))
                if observation is None:
                    missing_count += 1
                    missing_repetition_count += 1
                    missing_required |= target.required
                    missing_repetition_required |= target.required
                    continue
                if observation.result_status is ResultStatus.INFRASTRUCTURE_FAILED:
                    infrastructure_count += 1
                    continue
                if observation.result_status is ResultStatus.POLICY_DENIED:
                    policy_count += 1
                    continue
                if observation.result_status is ResultStatus.INVALID:
                    invalid_count += 1
                    continue
                if observation.result_status is ResultStatus.CANCELLED:
                    cancelled_count += 1
                    continue
                matches = [
                    score
                    for score in observation.scores
                    if score.metric_id.casefold() == target.metric_id
                ]
                if not matches or matches[0].status is ScoreStatus.MISSING:
                    missing_count += 1
                    explicit_missing_count += 1
                    missing_required |= target.required
                    explicit_missing_required |= target.required
                    continue
                score = matches[0]
                if score.status is ScoreStatus.INVALID:
                    invalid_count += 1
                    continue
                self._validate_score(target, score)
                scores.append(score)
                valid_count += 1
            if not scores:
                continue
            aggregation = self._aggregate_case(target, tuple(scores), case_thresholds.get((target.case_reference, target.metric_id)))
            aggregations.append(aggregation)
            if len(scores) < protocol.minimum_repetitions:
                insufficient_statistics = True
            if protocol.maximum_variance is not None and (
                aggregation.sample_variance is None
                or aggregation.sample_variance > protocol.maximum_variance
            ):
                insufficient_statistics = True
            if protocol.required_confidence is not None and (
                aggregation.conservative_confidence_bound is None
                or aggregation.conservative_confidence_bound
                < protocol.required_confidence
            ):
                insufficient_statistics = True

        aggregation_tuple = tuple(aggregations)
        failed_targets = tuple(
            item
            for item in aggregation_tuple
            if item.threshold_passed is False
        )
        failed_required = tuple(
            item.case_reference for item in failed_targets if item.required or item.critical
        )
        budget = self._failure_budget(protocol.failure_budget, failed_targets)
        metric_values = self._metric_aggregations(aggregation_tuple)
        overall = self._weighted_mean(aggregation_tuple)
        threshold_failures = self._aggregate_threshold_failures(
            protocol.thresholds, metric_values, overall
        )
        verdict, reasons = self._derive_verdict(
            policy_count=policy_count,
            invalid_count=invalid_count,
            blocked=bool(protocol.blocked_cases),
            failed_required=bool(failed_required),
            budget_exceeded=not budget.within_budget,
            aggregate_threshold_failed=threshold_failures,
            missing_required=missing_required,
            missing_repetition_required=missing_repetition_required,
            explicit_missing_required=explicit_missing_required,
            infrastructure_present=bool(infrastructure_count),
            cancelled_present=bool(cancelled_count),
            insufficient_statistics=insufficient_statistics,
            has_score=overall is not None,
        )
        semantic = {
            "protocol": self._protocol_identity(protocol),
            "observations": tuple(
                {
                    "run_id": item.run_id,
                    "case_reference": item.case_reference,
                    "repetition": item.repetition,
                    "result_status": item.result_status,
                    "scores": tuple(
                        sorted(
                            item.scores,
                            key=lambda score: (
                                score.metric_id.casefold(),
                                score.evaluator.evaluator_id.value,
                            ),
                        )
                    ),
                }
                for item in sorted(
                    observations,
                    key=lambda observation: (
                        observation.case_reference.case_id.value,
                        observation.case_reference.version.value,
                        observation.repetition,
                    ),
                )
            ),
            "aggregations": aggregation_tuple,
            "metric_aggregations": metric_values,
            "overall": overall,
            "budget": budget,
            "verdict": verdict,
            "reason_codes": reasons,
        }
        return ScoringDecision(
            protocol.run_id,
            verdict,
            reasons,
            aggregation_tuple,
            metric_values,
            overall,
            budget,
            valid_count,
            missing_count,
            missing_repetition_count,
            explicit_missing_count,
            infrastructure_count,
            cancelled_count,
            policy_count,
            invalid_count,
            tuple(sorted(set(failed_required), key=lambda item: (item.case_id.value, item.version.value))),
            fingerprint(semantic),
        )

    def validate_decision(
        self,
        protocol: ScoringProtocol,
        observations: tuple[ScoringObservation, ...],
        decision: ScoringDecision,
    ) -> None:
        if self.score(protocol, observations) != decision:
            raise DecisionFingerprintMismatch()

    @staticmethod
    def _protocol_identity(protocol: ScoringProtocol) -> dict[str, object]:
        return {
            "run_id": protocol.run_id,
            "suite_id": protocol.suite_id,
            "suite_version": protocol.suite_version,
            "targets": tuple(
                sorted(
                    protocol.targets,
                    key=lambda item: (
                        item.case_reference.case_id.value,
                        item.case_reference.version.value,
                        item.metric_id,
                    ),
                )
            ),
            "expected_repetitions": protocol.expected_repetitions,
            "minimum_repetitions": protocol.minimum_repetitions,
            "determinism_mode": protocol.determinism_mode,
            "aggregation_method": protocol.aggregation_method,
            "thresholds": tuple(
                sorted(
                    protocol.thresholds,
                    key=lambda item: (
                        item.scope.value,
                        item.case_reference.case_id.value
                        if item.case_reference is not None
                        else "",
                        item.metric_id or "",
                    ),
                )
            ),
            "failure_budget": protocol.failure_budget,
            "maximum_variance": protocol.maximum_variance,
            "required_confidence": protocol.required_confidence,
            "blocked_cases": tuple(
                sorted(
                    protocol.blocked_cases,
                    key=lambda item: (item.case_id.value, item.version.value),
                )
            ),
        }

    @staticmethod
    def _validate_observations(
        protocol: ScoringProtocol,
        observations: tuple[ScoringObservation, ...],
    ) -> dict[tuple[EvalCaseVersionRef, int], ScoringObservation]:
        target_metrics: dict[EvalCaseVersionRef, set[str]] = {}
        for target in protocol.targets:
            target_metrics.setdefault(target.case_reference, set()).add(target.metric_id)
        result: dict[tuple[EvalCaseVersionRef, int], ScoringObservation] = {}
        for observation in observations:
            if observation.run_id != protocol.run_id:
                raise InvalidScoringInput()
            if observation.case_reference not in target_metrics:
                raise InvalidScoringInput()
            if observation.repetition > protocol.expected_repetitions:
                raise InvalidScoringInput()
            key = (observation.case_reference, observation.repetition)
            if key in result:
                raise DuplicateRepetition()
            unexpected = {
                score.metric_id.casefold() for score in observation.scores
            } - target_metrics[observation.case_reference]
            if unexpected:
                raise IncompatibleMetric()
            for score in observation.scores:
                ScoringEngine._validate_score_metadata(score)
            result[key] = observation
        return result

    @staticmethod
    def _validate_score_metadata(score: Score) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(score.metric_id):
            raise IncompatibleMetric()
        if not _SAFE_IDENTIFIER.fullmatch(score.evaluator.kind):
            raise EvaluatorMismatch()
        if score.confidence_method is not None and not _SAFE_IDENTIFIER.fullmatch(
            score.confidence_method
        ):
            raise IncompatibleConfidenceMethod()
        if score.reason_code is not None and not _SAFE_IDENTIFIER.fullmatch(
            score.reason_code
        ):
            raise InvalidScoringInput()

    @staticmethod
    def _validate_score(target: ScoringTarget, score: Score) -> None:
        if score.evaluator != target.evaluator:
            raise EvaluatorMismatch()
        if score.weight != target.weight or score.weight <= 0:
            raise InvalidScoringWeight()
        if score.required != target.required or score.critical != target.critical:
            raise InvalidScoringInput()
        if score.sample_count != 1:
            raise InvalidScoringInput()

    @staticmethod
    def _aggregate_case(
        target: ScoringTarget,
        scores: tuple[Score, ...],
        threshold: ScoreThreshold | None,
    ) -> CaseScoreAggregation:
        scales = {(item.kind, item.scale_minimum, item.scale_maximum) for item in scores}
        if len(scales) != 1:
            raise IncompatibleScale()
        normalized = tuple(item.normalized_value for item in scores)
        raw = tuple(item.raw_value for item in scores)
        if any(item is None for item in normalized) or any(item is None for item in raw):
            raise InvalidScoringInput()
        normalized_values = tuple(item for item in normalized if item is not None)
        raw_values = tuple(item for item in raw if item is not None)
        mean = _mean(normalized_values)
        variance = None
        if len(normalized_values) >= 2:
            with localcontext() as context:
                context.prec = 40
                context.rounding = ROUND_HALF_EVEN
                variance = _q(
                    sum((item - mean) ** 2 for item in normalized_values)
                    / Decimal(len(normalized_values) - 1)
                )
        confidences = tuple(item.confidence for item in scores)
        methods = {item.confidence_method for item in scores}
        confidence_bound = None
        confidence_projection_method = None
        non_null_methods = {item for item in methods if item is not None}
        if len(non_null_methods) > 1:
            raise IncompatibleConfidenceMethod()
        if all(item is not None for item in confidences) and len(methods) == 1:
            confidence_bound = min(item for item in confidences if item is not None)
            source_method = next(iter(methods))
            confidence_projection_method = f"conservative_minimum:{source_method}"
        threshold_passed = threshold.accepts(mean) if threshold is not None else None
        first = scores[0]
        return CaseScoreAggregation(
            target.case_reference,
            target.metric_id,
            target.evaluator,
            mean,
            min(normalized_values),
            max(normalized_values),
            _mean(raw_values),
            first.scale_minimum,
            first.scale_maximum,
            first.kind,
            mean if first.kind is ScoreKind.BINARY else None,
            len(scores),
            variance,
            confidence_bound,
            confidence_projection_method,
            target.weight,
            target.required,
            target.critical,
            threshold_passed,
        )

    @staticmethod
    def _failure_budget(
        budget: FailureBudget,
        failed: tuple[CaseScoreAggregation, ...],
    ) -> FailureBudgetOutcome:
        budgeted_by_case: dict[EvalCaseVersionRef, CaseScoreAggregation] = {}
        for item in failed:
            if not item.required and not item.critical:
                budgeted_by_case.setdefault(item.case_reference, item)
        budgeted = tuple(
            budgeted_by_case[key]
            for key in sorted(
                budgeted_by_case,
                key=lambda item: (item.case_id.value, item.version.value),
            )
        )
        responsible = tuple(item.case_reference for item in budgeted)
        if budget.unit is FailureBudgetUnit.COUNT:
            assert budget.count_limit is not None
            available = Decimal(budget.count_limit)
            consumed = Decimal(len(budgeted))
        else:
            assert budget.weight_limit is not None
            available = budget.weight_limit
            consumed = sum((item.weight for item in budgeted), Decimal("0"))
        return FailureBudgetOutcome(
            budget.unit,
            available,
            consumed,
            responsible,
            consumed <= available,
        )

    @staticmethod
    def _metric_aggregations(
        aggregations: tuple[CaseScoreAggregation, ...],
    ) -> tuple[tuple[str, Decimal], ...]:
        metrics: dict[str, list[CaseScoreAggregation]] = {}
        for item in aggregations:
            metrics.setdefault(item.metric_id, []).append(item)
        return tuple(
            (metric, ScoringEngine._weighted_mean(tuple(items)) or Decimal("0"))
            for metric, items in sorted(metrics.items())
        )

    @staticmethod
    def _weighted_mean(
        aggregations: tuple[CaseScoreAggregation, ...],
    ) -> Decimal | None:
        if not aggregations:
            return None
        weight = sum((item.weight for item in aggregations), Decimal("0"))
        if weight <= 0:
            raise InvalidScoringWeight()
        with localcontext() as context:
            context.prec = 40
            context.rounding = ROUND_HALF_EVEN
            return _q(
                sum(
                    (item.normalized_mean * item.weight for item in aggregations),
                    Decimal("0"),
                )
                / weight
            )

    @staticmethod
    def _aggregate_threshold_failures(
        thresholds: tuple[ScoreThreshold, ...],
        metrics: tuple[tuple[str, Decimal], ...],
        overall: Decimal | None,
    ) -> bool:
        metric_map = dict(metrics)
        for threshold in thresholds:
            if threshold.scope is ThresholdScope.METRIC:
                if threshold.metric_id not in metric_map:
                    raise ThresholdMismatch()
                if not threshold.accepts(metric_map[threshold.metric_id]):
                    return True
            elif threshold.scope is ThresholdScope.GLOBAL:
                if overall is None:
                    raise ThresholdMismatch()
                if not threshold.accepts(overall):
                    return True
        return False

    @staticmethod
    def _derive_verdict(
        *,
        policy_count: int,
        invalid_count: int,
        blocked: bool,
        failed_required: bool,
        budget_exceeded: bool,
        aggregate_threshold_failed: bool,
        missing_required: bool,
        missing_repetition_required: bool,
        explicit_missing_required: bool,
        infrastructure_present: bool,
        cancelled_present: bool,
        insufficient_statistics: bool,
        has_score: bool,
    ) -> tuple[Verdict, tuple[ScoringReasonCode, ...]]:
        if invalid_count:
            return Verdict.INVALID, (ScoringReasonCode.INVALID_SCORING_INPUT,)
        if policy_count:
            return Verdict.POLICY_DENIED, (ScoringReasonCode.POLICY_DENIED,)
        if blocked:
            return Verdict.BLOCKED, (ScoringReasonCode.EXTERNAL_PREREQUISITE_BLOCKED,)
        failures: list[ScoringReasonCode] = []
        if failed_required:
            failures.append(ScoringReasonCode.REQUIRED_CASE_THRESHOLD_FAILED)
        if budget_exceeded:
            failures.append(ScoringReasonCode.FAILURE_BUDGET_EXCEEDED)
        if aggregate_threshold_failed:
            failures.append(ScoringReasonCode.AGGREGATE_THRESHOLD_FAILED)
        if failures:
            return Verdict.FAILED, tuple(failures)
        inconclusive: list[ScoringReasonCode] = []
        if missing_repetition_required:
            inconclusive.append(ScoringReasonCode.REQUIRED_REPETITION_MISSING)
        if explicit_missing_required:
            inconclusive.append(ScoringReasonCode.REQUIRED_SCORE_MISSING)
        if missing_required and not (
            missing_repetition_required or explicit_missing_required
        ):
            inconclusive.append(ScoringReasonCode.REQUIRED_SCORE_MISSING)
        if infrastructure_present:
            inconclusive.append(ScoringReasonCode.INFRASTRUCTURE_FAILURE)
        if cancelled_present:
            inconclusive.append(ScoringReasonCode.EXECUTION_CANCELLED)
        if insufficient_statistics:
            inconclusive.append(ScoringReasonCode.INSUFFICIENT_STATISTICS)
        if not has_score:
            inconclusive.append(ScoringReasonCode.NO_SCOREABLE_DATA)
        if inconclusive:
            return Verdict.INCONCLUSIVE, tuple(inconclusive)
        return Verdict.PASSED, (ScoringReasonCode.ALL_SCORING_RULES_SATISFIED,)
