from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_values import validate_store_timestamp
from synapse.skills.phase10_refs import ExternalBinderRef
from synapse.skills.phase11_errors import (
    InvalidSkillPrivateEvalBindingRequest,
    InvalidSkillPrivateEvalGranularity,
    InvalidSkillPrivateEvalTemporalRelation,
)
from synapse.skills.phase11_refs import (
    PrivateEvalBaselineRef,
    PrivateEvalBindingOccurrenceRef,
    PrivateEvalBindingRef,
    PrivateEvalCaseRef,
    PrivateEvalComparisonRef,
    PrivateEvalEvidenceRef,
    PrivateEvalProfileRef,
    PrivateEvalRegressionRef,
    PrivateEvalResultRef,
    PrivateEvalRunRef,
    PrivateEvalSuiteRef,
    PrivateEvalVerdictRef,
)


class SkillPrivateEvalBindingGranularity(StrEnum):
    SUITE_RESULT = "suite_result"
    CASE_RESULT = "case_result"
    COMPARISON_RESULT = "comparison_result"
    REGRESSION_RESULT = "regression_result"


class SkillPrivateEvalBindingOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"


class SkillPrivateEvalBindingDiagnosticKind(StrEnum):
    MULTIPLE_RUN_REFERENCES = "multiple_run_references"
    MULTIPLE_RESULT_REFERENCES = "multiple_result_references"
    MULTIPLE_VERDICT_REFERENCES = "multiple_verdict_references"
    MULTIPLE_SUITE_REFERENCES = "multiple_suite_references"
    MULTIPLE_CASE_REFERENCES = "multiple_case_references"
    MULTIPLE_PROFILE_REFERENCES = "multiple_profile_references"
    MULTIPLE_BASELINE_REFERENCES = "multiple_baseline_references"
    MULTIPLE_COMPARISON_REFERENCES = "multiple_comparison_references"
    MULTIPLE_REGRESSION_REFERENCES = "multiple_regression_references"
    INCOMPLETE_HISTORY = "incomplete_history"


@dataclass(frozen=True)
class SkillPrivateEvalBindingDiagnostic:
    kind: SkillPrivateEvalBindingDiagnosticKind
    occurrences: tuple[PrivateEvalBindingOccurrenceRef, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, SkillPrivateEvalBindingDiagnosticKind)
            or not _tuple_of(self.occurrences, PrivateEvalBindingOccurrenceRef)
            or len(set(self.occurrences)) != len(self.occurrences)
            or tuple(sorted(self.occurrences)) != self.occurrences
        ):
            raise InvalidSkillPrivateEvalBindingRequest()


@dataclass(frozen=True, kw_only=True)
class BindSkillPrivateEvalResultRequest:
    identity: PublishedSkillVersionId
    granularity: SkillPrivateEvalBindingGranularity
    run_ref: PrivateEvalRunRef
    result_ref: PrivateEvalResultRef
    verdict_ref: PrivateEvalVerdictRef | None
    suite_ref: PrivateEvalSuiteRef
    case_ref: PrivateEvalCaseRef | None
    profile_ref: PrivateEvalProfileRef
    baseline_ref: PrivateEvalBaselineRef | None
    comparison_ref: PrivateEvalComparisonRef | None
    regression_ref: PrivateEvalRegressionRef | None
    evidence_refs: tuple[PrivateEvalEvidenceRef, ...]
    binder_ref: ExternalBinderRef
    evaluated_at: datetime
    bound_at: datetime

    def __post_init__(self) -> None:
        _validate_binding_fields(self)
        _validate_granularity(
            self.granularity,
            self.case_ref,
            self.baseline_ref,
            self.comparison_ref,
            self.regression_ref,
        )
        _validate_temporal_relation(self.evaluated_at, self.bound_at)
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise InvalidSkillPrivateEvalBindingRequest()
        object.__setattr__(self, "evidence_refs", tuple(sorted(self.evidence_refs)))


@dataclass(frozen=True)
class SkillPrivateEvalBindingRecord:
    binding_ref: PrivateEvalBindingRef
    occurrence_ref: PrivateEvalBindingOccurrenceRef
    identity: PublishedSkillVersionId
    granularity: SkillPrivateEvalBindingGranularity
    run_ref: PrivateEvalRunRef
    result_ref: PrivateEvalResultRef
    verdict_ref: PrivateEvalVerdictRef | None
    suite_ref: PrivateEvalSuiteRef
    case_ref: PrivateEvalCaseRef | None
    profile_ref: PrivateEvalProfileRef
    baseline_ref: PrivateEvalBaselineRef | None
    comparison_ref: PrivateEvalComparisonRef | None
    regression_ref: PrivateEvalRegressionRef | None
    evidence_refs: tuple[PrivateEvalEvidenceRef, ...]
    binder_ref: ExternalBinderRef
    evaluated_at: datetime
    bound_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, PrivateEvalBindingRef) or not isinstance(
            self.occurrence_ref, PrivateEvalBindingOccurrenceRef
        ):
            raise InvalidSkillPrivateEvalBindingRequest()
        _validate_binding_fields(self)
        _validate_granularity(
            self.granularity,
            self.case_ref,
            self.baseline_ref,
            self.comparison_ref,
            self.regression_ref,
        )
        _validate_temporal_relation(self.evaluated_at, self.bound_at)
        if (
            len(set(self.evidence_refs)) != len(self.evidence_refs)
            or tuple(sorted(self.evidence_refs)) != self.evidence_refs
        ):
            raise InvalidSkillPrivateEvalBindingRequest()


@dataclass(frozen=True)
class SkillPrivateEvalBindingHistory:
    records: tuple[SkillPrivateEvalBindingRecord, ...]
    complete: bool

    def __post_init__(self) -> None:
        if not _tuple_of(self.records, SkillPrivateEvalBindingRecord) or not isinstance(
            self.complete, bool
        ):
            raise InvalidSkillPrivateEvalBindingRequest()


@dataclass(frozen=True)
class SkillPrivateEvalBindingProjection:
    identity: PublishedSkillVersionId
    history: SkillPrivateEvalBindingHistory
    granularities: tuple[SkillPrivateEvalBindingGranularity, ...]
    run_refs: tuple[PrivateEvalRunRef, ...]
    result_refs: tuple[PrivateEvalResultRef, ...]
    verdict_refs: tuple[PrivateEvalVerdictRef, ...]
    suite_refs: tuple[PrivateEvalSuiteRef, ...]
    case_refs: tuple[PrivateEvalCaseRef, ...]
    profile_refs: tuple[PrivateEvalProfileRef, ...]
    baseline_refs: tuple[PrivateEvalBaselineRef, ...]
    comparison_refs: tuple[PrivateEvalComparisonRef, ...]
    regression_refs: tuple[PrivateEvalRegressionRef, ...]
    evidence_refs: tuple[PrivateEvalEvidenceRef, ...]
    binder_refs: tuple[ExternalBinderRef, ...]
    binding_refs: tuple[PrivateEvalBindingRef, ...]
    occurrence_refs: tuple[PrivateEvalBindingOccurrenceRef, ...]
    diagnostics: tuple[SkillPrivateEvalBindingDiagnostic, ...]
    complete: bool

    def __post_init__(self) -> None:
        checks = (
            _tuple_of(self.granularities, SkillPrivateEvalBindingGranularity),
            _tuple_of(self.run_refs, PrivateEvalRunRef),
            _tuple_of(self.result_refs, PrivateEvalResultRef),
            _tuple_of(self.verdict_refs, PrivateEvalVerdictRef),
            _tuple_of(self.suite_refs, PrivateEvalSuiteRef),
            _tuple_of(self.case_refs, PrivateEvalCaseRef),
            _tuple_of(self.profile_refs, PrivateEvalProfileRef),
            _tuple_of(self.baseline_refs, PrivateEvalBaselineRef),
            _tuple_of(self.comparison_refs, PrivateEvalComparisonRef),
            _tuple_of(self.regression_refs, PrivateEvalRegressionRef),
            _tuple_of(self.evidence_refs, PrivateEvalEvidenceRef),
            _tuple_of(self.binder_refs, ExternalBinderRef),
            _tuple_of(self.binding_refs, PrivateEvalBindingRef),
            _tuple_of(self.occurrence_refs, PrivateEvalBindingOccurrenceRef),
            _tuple_of(self.diagnostics, SkillPrivateEvalBindingDiagnostic),
        )
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.history, SkillPrivateEvalBindingHistory)
            or not all(checks)
            or not isinstance(self.complete, bool)
            or self.complete != self.history.complete
        ):
            raise InvalidSkillPrivateEvalBindingRequest()


@dataclass(frozen=True)
class SkillPrivateEvalBindingResult:
    identity: PublishedSkillVersionId
    record: SkillPrivateEvalBindingRecord
    outcome: SkillPrivateEvalBindingOutcome
    projection: SkillPrivateEvalBindingProjection | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.record, SkillPrivateEvalBindingRecord)
            or not isinstance(self.outcome, SkillPrivateEvalBindingOutcome)
            or (
                self.projection is not None
                and not isinstance(self.projection, SkillPrivateEvalBindingProjection)
            )
            or self.record.identity != self.identity
            or (self.projection is not None and self.projection.identity != self.identity)
        ):
            raise InvalidSkillPrivateEvalBindingRequest()


def _validate_binding_fields(
    value: BindSkillPrivateEvalResultRequest | SkillPrivateEvalBindingRecord,
) -> None:
    if (
        not isinstance(value.identity, PublishedSkillVersionId)
        or not isinstance(value.granularity, SkillPrivateEvalBindingGranularity)
        or not isinstance(value.run_ref, PrivateEvalRunRef)
        or not isinstance(value.result_ref, PrivateEvalResultRef)
        or (
            value.verdict_ref is not None
            and not isinstance(value.verdict_ref, PrivateEvalVerdictRef)
        )
        or not isinstance(value.suite_ref, PrivateEvalSuiteRef)
        or (value.case_ref is not None and not isinstance(value.case_ref, PrivateEvalCaseRef))
        or not isinstance(value.profile_ref, PrivateEvalProfileRef)
        or (
            value.baseline_ref is not None
            and not isinstance(value.baseline_ref, PrivateEvalBaselineRef)
        )
        or (
            value.comparison_ref is not None
            and not isinstance(value.comparison_ref, PrivateEvalComparisonRef)
        )
        or (
            value.regression_ref is not None
            and not isinstance(value.regression_ref, PrivateEvalRegressionRef)
        )
        or not _tuple_of(value.evidence_refs, PrivateEvalEvidenceRef)
        or not isinstance(value.binder_ref, ExternalBinderRef)
    ):
        raise InvalidSkillPrivateEvalBindingRequest()


def _validate_granularity(
    granularity: SkillPrivateEvalBindingGranularity,
    case_ref: PrivateEvalCaseRef | None,
    baseline_ref: PrivateEvalBaselineRef | None,
    comparison_ref: PrivateEvalComparisonRef | None,
    regression_ref: PrivateEvalRegressionRef | None,
) -> None:
    valid = {
        SkillPrivateEvalBindingGranularity.SUITE_RESULT: (
            case_ref is None
            and baseline_ref is None
            and comparison_ref is None
            and regression_ref is None
        ),
        SkillPrivateEvalBindingGranularity.CASE_RESULT: (
            case_ref is not None
            and baseline_ref is None
            and comparison_ref is None
            and regression_ref is None
        ),
        SkillPrivateEvalBindingGranularity.COMPARISON_RESULT: (
            case_ref is None
            and baseline_ref is not None
            and comparison_ref is not None
            and regression_ref is None
        ),
        SkillPrivateEvalBindingGranularity.REGRESSION_RESULT: (
            case_ref is None
            and baseline_ref is not None
            and comparison_ref is not None
            and regression_ref is not None
        ),
    }
    if not valid.get(granularity, False):
        raise InvalidSkillPrivateEvalGranularity()


def _validate_temporal_relation(evaluated_at: datetime, bound_at: datetime) -> None:
    try:
        validate_store_timestamp(evaluated_at)
        validate_store_timestamp(bound_at)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise InvalidSkillPrivateEvalTemporalRelation() from exc
    if evaluated_at > bound_at:
        raise InvalidSkillPrivateEvalTemporalRelation()


def _tuple_of(value: object, expected: type[object]) -> bool:
    return isinstance(value, tuple) and all(isinstance(item, expected) for item in value)
