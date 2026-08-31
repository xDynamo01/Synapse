from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase11_errors import InvalidSkillPrivateEvalBindingHistory
from synapse.skills.phase11_identity import (
    _private_eval_binding_ref,
    _private_eval_occurrence_ref,
)
from synapse.skills.phase11_models import (
    SkillPrivateEvalBindingDiagnostic,
    SkillPrivateEvalBindingDiagnosticKind,
    SkillPrivateEvalBindingHistory,
    SkillPrivateEvalBindingProjection,
    SkillPrivateEvalBindingRecord,
)
from synapse.skills.phase11_refs import PrivateEvalBindingOccurrenceRef

_ReferenceT = TypeVar("_ReferenceT")


def _canonical_private_eval_history(
    identity: PublishedSkillVersionId,
    history: SkillPrivateEvalBindingHistory,
    limit: SkillStoreQueryLimit,
) -> SkillPrivateEvalBindingHistory:
    if (
        not isinstance(history, SkillPrivateEvalBindingHistory)
        or len(history.records) > limit.limit
    ):
        raise InvalidSkillPrivateEvalBindingHistory()
    by_occurrence: dict[PrivateEvalBindingOccurrenceRef, SkillPrivateEvalBindingRecord] = {}
    evaluated_results: dict[tuple[object, object], object] = {}
    for record in history.records:
        if record.identity != identity:
            raise InvalidSkillPrivateEvalBindingHistory()
        expected_binding_ref = _private_eval_binding_ref(record)
        expected_occurrence_ref = _private_eval_occurrence_ref(
            expected_binding_ref,
            record.binder_ref,
            record.bound_at,
        )
        if (
            record.binding_ref != expected_binding_ref
            or record.occurrence_ref != expected_occurrence_ref
        ):
            raise InvalidSkillPrivateEvalBindingHistory()
        existing = by_occurrence.get(record.occurrence_ref)
        if existing is not None and existing != record:
            raise InvalidSkillPrivateEvalBindingHistory()
        result_identity = (record.run_ref, record.result_ref)
        previous_time = evaluated_results.setdefault(result_identity, record.evaluated_at)
        if previous_time != record.evaluated_at:
            raise InvalidSkillPrivateEvalBindingHistory()
        by_occurrence[record.occurrence_ref] = record
    records = tuple(
        sorted(
            by_occurrence.values(),
            key=lambda record: (
                record.evaluated_at,
                record.bound_at,
                str(record.occurrence_ref),
            ),
        )
    )
    return SkillPrivateEvalBindingHistory(records, history.complete)


def _private_eval_projection(
    identity: PublishedSkillVersionId,
    history: SkillPrivateEvalBindingHistory,
) -> SkillPrivateEvalBindingProjection:
    records = history.records
    occurrence_refs = tuple(record.occurrence_ref for record in records)
    runs = _unique_sorted(record.run_ref for record in records)
    results = _unique_sorted(record.result_ref for record in records)
    verdicts = _unique_sorted(
        record.verdict_ref for record in records if record.verdict_ref is not None
    )
    suites = _unique_sorted(record.suite_ref for record in records)
    cases = _unique_sorted(record.case_ref for record in records if record.case_ref is not None)
    profiles = _unique_sorted(record.profile_ref for record in records)
    baselines = _unique_sorted(
        record.baseline_ref for record in records if record.baseline_ref is not None
    )
    comparisons = _unique_sorted(
        record.comparison_ref for record in records if record.comparison_ref is not None
    )
    regressions = _unique_sorted(
        record.regression_ref for record in records if record.regression_ref is not None
    )
    diagnostics = _multiplicity_diagnostics(
        occurrence_refs,
        (
            (runs, SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_RUN_REFERENCES),
            (results, SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_RESULT_REFERENCES),
            (verdicts, SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_VERDICT_REFERENCES),
            (suites, SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_SUITE_REFERENCES),
            (cases, SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_CASE_REFERENCES),
            (profiles, SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_PROFILE_REFERENCES),
            (baselines, SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_BASELINE_REFERENCES),
            (
                comparisons,
                SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_COMPARISON_REFERENCES,
            ),
            (
                regressions,
                SkillPrivateEvalBindingDiagnosticKind.MULTIPLE_REGRESSION_REFERENCES,
            ),
        ),
        history.complete,
    )
    return SkillPrivateEvalBindingProjection(
        identity=identity,
        history=history,
        granularities=_unique_sorted(record.granularity for record in records),
        run_refs=runs,
        result_refs=results,
        verdict_refs=verdicts,
        suite_refs=suites,
        case_refs=cases,
        profile_refs=profiles,
        baseline_refs=baselines,
        comparison_refs=comparisons,
        regression_refs=regressions,
        evidence_refs=_unique_sorted(
            evidence for record in records for evidence in record.evidence_refs
        ),
        binder_refs=_unique_sorted(record.binder_ref for record in records),
        binding_refs=_unique_sorted(record.binding_ref for record in records),
        occurrence_refs=occurrence_refs,
        diagnostics=diagnostics,
        complete=history.complete,
    )


def _multiplicity_diagnostics(
    occurrence_refs: tuple[PrivateEvalBindingOccurrenceRef, ...],
    collections: Iterable[
        tuple[tuple[object, ...], SkillPrivateEvalBindingDiagnosticKind]
    ],
    complete: bool,
) -> tuple[SkillPrivateEvalBindingDiagnostic, ...]:
    diagnostic_occurrences = tuple(sorted(occurrence_refs))
    diagnostics = [
        SkillPrivateEvalBindingDiagnostic(kind, diagnostic_occurrences)
        for values, kind in collections
        if len(values) > 1
    ]
    if not complete:
        diagnostics.append(
            SkillPrivateEvalBindingDiagnostic(
                SkillPrivateEvalBindingDiagnosticKind.INCOMPLETE_HISTORY,
                diagnostic_occurrences,
            )
        )
    return tuple(diagnostics)


def _unique_sorted(values: Iterable[_ReferenceT]) -> tuple[_ReferenceT, ...]:
    return tuple(sorted(dict.fromkeys(values), key=str))
