from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase10_errors import InvalidSkillExternalBindingHistory
from synapse.skills.phase10_identity import (
    _binding_occurrence_ref,
    _governance_binding_ref,
    _intelligence_binding_ref,
)
from synapse.skills.phase10_models import (
    SkillExternalBindingDiagnostic,
    SkillExternalBindingDiagnosticKind,
    SkillGovernanceBindingHistory,
    SkillGovernanceBindingProjection,
    SkillGovernanceBindingRecord,
    SkillIntelligenceBindingHistory,
    SkillIntelligenceBindingProjection,
    SkillIntelligenceBindingRecord,
)
from synapse.skills.phase10_refs import ExternalBindingOccurrenceRef

_ReferenceT = TypeVar("_ReferenceT")
_RecordT = TypeVar(
    "_RecordT",
    SkillGovernanceBindingRecord,
    SkillIntelligenceBindingRecord,
)


def _canonical_governance_history(
    identity: PublishedSkillVersionId,
    history: SkillGovernanceBindingHistory,
    limit: SkillStoreQueryLimit,
) -> SkillGovernanceBindingHistory:
    if not isinstance(history, SkillGovernanceBindingHistory) or len(history.records) > limit.limit:
        raise InvalidSkillExternalBindingHistory()
    return SkillGovernanceBindingHistory(
        _canonical_records(identity, history.records),
        history.complete,
    )


def _canonical_intelligence_history(
    identity: PublishedSkillVersionId,
    history: SkillIntelligenceBindingHistory,
    limit: SkillStoreQueryLimit,
) -> SkillIntelligenceBindingHistory:
    if (
        not isinstance(history, SkillIntelligenceBindingHistory)
        or len(history.records) > limit.limit
    ):
        raise InvalidSkillExternalBindingHistory()
    records = _canonical_records(identity, history.records)
    observations: dict[tuple[object, object], object] = {}
    for record in records:
        fact_identity = (record.authority_ref, record.fact_ref)
        previous = observations.setdefault(fact_identity, record.observed_at)
        if previous != record.observed_at:
            raise InvalidSkillExternalBindingHistory()
    return SkillIntelligenceBindingHistory(records, history.complete)


def _governance_projection(
    identity: PublishedSkillVersionId,
    history: SkillGovernanceBindingHistory,
) -> SkillGovernanceBindingProjection:
    records = history.records
    occurrence_refs = tuple(record.occurrence_ref for record in records)
    authorities = _unique_sorted(record.authority_ref for record in records)
    decisions = _unique_sorted(record.decision_ref for record in records)
    decision_kinds = _unique_sorted(record.decision_kind_ref for record in records)
    policies = _unique_sorted(record.policy_ref for record in records)
    diagnostics = _multiplicity_diagnostics(
        occurrence_refs,
        (
            (authorities, SkillExternalBindingDiagnosticKind.MULTIPLE_AUTHORITY_REFERENCES),
            (decisions, SkillExternalBindingDiagnosticKind.MULTIPLE_DECISION_REFERENCES),
            (
                decision_kinds,
                SkillExternalBindingDiagnosticKind.MULTIPLE_DECISION_KIND_REFERENCES,
            ),
            (policies, SkillExternalBindingDiagnosticKind.MULTIPLE_POLICY_REFERENCES),
        ),
        history.complete,
    )
    return SkillGovernanceBindingProjection(
        identity=identity,
        history=history,
        decision_refs=decisions,
        decision_kind_refs=decision_kinds,
        policy_refs=policies,
        authority_refs=authorities,
        binder_refs=_unique_sorted(record.binder_ref for record in records),
        binding_refs=_unique_sorted(record.binding_ref for record in records),
        occurrence_refs=occurrence_refs,
        diagnostics=diagnostics,
        complete=history.complete,
    )


def _intelligence_projection(
    identity: PublishedSkillVersionId,
    history: SkillIntelligenceBindingHistory,
) -> SkillIntelligenceBindingProjection:
    records = history.records
    occurrence_refs = tuple(record.occurrence_ref for record in records)
    authorities = _unique_sorted(record.authority_ref for record in records)
    facts = _unique_sorted(record.fact_ref for record in records)
    analyses = _unique_sorted(
        record.analysis_ref for record in records if record.analysis_ref is not None
    )
    fact_kinds = _unique_sorted(record.fact_kind_ref for record in records)
    profiles = _unique_sorted(record.profile_ref for record in records)
    diagnostics = _multiplicity_diagnostics(
        occurrence_refs,
        (
            (authorities, SkillExternalBindingDiagnosticKind.MULTIPLE_AUTHORITY_REFERENCES),
            (facts, SkillExternalBindingDiagnosticKind.MULTIPLE_FACT_REFERENCES),
            (
                fact_kinds,
                SkillExternalBindingDiagnosticKind.MULTIPLE_FACT_KIND_REFERENCES,
            ),
            (profiles, SkillExternalBindingDiagnosticKind.MULTIPLE_PROFILE_REFERENCES),
            (analyses, SkillExternalBindingDiagnosticKind.MULTIPLE_ANALYSIS_REFERENCES),
        ),
        history.complete,
    )
    return SkillIntelligenceBindingProjection(
        identity=identity,
        history=history,
        fact_refs=facts,
        analysis_refs=analyses,
        fact_kind_refs=fact_kinds,
        profile_refs=profiles,
        authority_refs=authorities,
        binder_refs=_unique_sorted(record.binder_ref for record in records),
        binding_refs=_unique_sorted(record.binding_ref for record in records),
        occurrence_refs=occurrence_refs,
        diagnostics=diagnostics,
        complete=history.complete,
    )


def _multiplicity_diagnostics(
    occurrence_refs: tuple[ExternalBindingOccurrenceRef, ...],
    collections: Iterable[tuple[tuple[object, ...], SkillExternalBindingDiagnosticKind]],
    complete: bool,
) -> tuple[SkillExternalBindingDiagnostic, ...]:
    diagnostic_occurrences = tuple(sorted(occurrence_refs))
    diagnostics = [
        SkillExternalBindingDiagnostic(kind, diagnostic_occurrences)
        for values, kind in collections
        if len(values) > 1
    ]
    if not complete:
        diagnostics.append(
            SkillExternalBindingDiagnostic(
                SkillExternalBindingDiagnosticKind.INCOMPLETE_HISTORY,
                diagnostic_occurrences,
            )
        )
    return tuple(diagnostics)


def _canonical_records(
    identity: PublishedSkillVersionId,
    records: tuple[_RecordT, ...],
) -> tuple[_RecordT, ...]:
    by_occurrence: dict[ExternalBindingOccurrenceRef, _RecordT] = {}
    for record in records:
        if record.identity != identity:
            raise InvalidSkillExternalBindingHistory()
        if isinstance(record, SkillGovernanceBindingRecord):
            expected_binding_ref = _governance_binding_ref(
                record.identity,
                record.authority_ref,
                record.decision_ref,
                record.decision_kind_ref,
                record.policy_ref,
            )
            family = "governance"
        else:
            expected_binding_ref = _intelligence_binding_ref(
                record.identity,
                record.authority_ref,
                record.fact_ref,
                record.fact_kind_ref,
                record.profile_ref,
                record.analysis_ref,
            )
            family = "intelligence"
        expected_occurrence_ref = _binding_occurrence_ref(
            family,
            expected_binding_ref,
            record.binder_ref,
            record.bound_at,
        )
        if (
            record.binding_ref != expected_binding_ref
            or record.occurrence_ref != expected_occurrence_ref
        ):
            raise InvalidSkillExternalBindingHistory()
        existing = by_occurrence.get(record.occurrence_ref)
        if existing is not None and existing != record:
            raise InvalidSkillExternalBindingHistory()
        by_occurrence[record.occurrence_ref] = record
    return tuple(
        sorted(
            by_occurrence.values(),
            key=lambda record: (record.bound_at, str(record.occurrence_ref)),
        )
    )


def _unique_sorted(values: Iterable[_ReferenceT]) -> tuple[_ReferenceT, ...]:
    return tuple(sorted(dict.fromkeys(values), key=str))
