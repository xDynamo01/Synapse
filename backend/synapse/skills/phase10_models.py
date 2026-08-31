from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_values import validate_store_timestamp
from synapse.skills.phase10_errors import InvalidSkillExternalBindingRequest
from synapse.skills.phase10_refs import (
    ExternalAuthorityRef,
    ExternalBinderRef,
    ExternalBindingOccurrenceRef,
    ExternalBindingRef,
    GovernanceDecisionKindRef,
    GovernanceDecisionRef,
    GovernancePolicyRef,
    IntelligenceAnalysisRef,
    IntelligenceFactKindRef,
    IntelligenceFactRef,
    IntelligenceProfileRef,
)


class SkillExternalBindingOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"


class SkillExternalBindingDiagnosticKind(StrEnum):
    MULTIPLE_AUTHORITY_REFERENCES = "multiple_authority_references"
    MULTIPLE_DECISION_REFERENCES = "multiple_decision_references"
    MULTIPLE_DECISION_KIND_REFERENCES = "multiple_decision_kind_references"
    MULTIPLE_POLICY_REFERENCES = "multiple_policy_references"
    MULTIPLE_FACT_REFERENCES = "multiple_fact_references"
    MULTIPLE_FACT_KIND_REFERENCES = "multiple_fact_kind_references"
    MULTIPLE_PROFILE_REFERENCES = "multiple_profile_references"
    MULTIPLE_ANALYSIS_REFERENCES = "multiple_analysis_references"
    INCOMPLETE_HISTORY = "incomplete_history"


@dataclass(frozen=True)
class SkillExternalBindingDiagnostic:
    kind: SkillExternalBindingDiagnosticKind
    occurrences: tuple[ExternalBindingOccurrenceRef, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, SkillExternalBindingDiagnosticKind)
            or not _tuple_of(self.occurrences, ExternalBindingOccurrenceRef)
            or len(set(self.occurrences)) != len(self.occurrences)
            or tuple(sorted(self.occurrences)) != self.occurrences
        ):
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True, kw_only=True)
class BindSkillGovernanceDecisionRequest:
    identity: PublishedSkillVersionId
    decision_ref: GovernanceDecisionRef
    decision_kind_ref: GovernanceDecisionKindRef
    policy_ref: GovernancePolicyRef
    authority_ref: ExternalAuthorityRef
    binder_ref: ExternalBinderRef
    bound_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.decision_ref, GovernanceDecisionRef)
            or not isinstance(self.decision_kind_ref, GovernanceDecisionKindRef)
            or not isinstance(self.policy_ref, GovernancePolicyRef)
            or not isinstance(self.authority_ref, ExternalAuthorityRef)
            or not isinstance(self.binder_ref, ExternalBinderRef)
        ):
            raise InvalidSkillExternalBindingRequest()
        _validate_time(self.bound_at)


@dataclass(frozen=True, kw_only=True)
class BindSkillIntelligenceFactRequest:
    identity: PublishedSkillVersionId
    fact_ref: IntelligenceFactRef
    analysis_ref: IntelligenceAnalysisRef | None
    fact_kind_ref: IntelligenceFactKindRef
    profile_ref: IntelligenceProfileRef
    authority_ref: ExternalAuthorityRef
    binder_ref: ExternalBinderRef
    observed_at: datetime
    bound_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.fact_ref, IntelligenceFactRef)
            or (
                self.analysis_ref is not None
                and not isinstance(self.analysis_ref, IntelligenceAnalysisRef)
            )
            or not isinstance(self.fact_kind_ref, IntelligenceFactKindRef)
            or not isinstance(self.profile_ref, IntelligenceProfileRef)
            or not isinstance(self.authority_ref, ExternalAuthorityRef)
            or not isinstance(self.binder_ref, ExternalBinderRef)
        ):
            raise InvalidSkillExternalBindingRequest()
        _validate_time(self.observed_at)
        _validate_time(self.bound_at)
        if self.observed_at > self.bound_at:
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True)
class SkillGovernanceBindingRecord:
    binding_ref: ExternalBindingRef
    occurrence_ref: ExternalBindingOccurrenceRef
    identity: PublishedSkillVersionId
    decision_ref: GovernanceDecisionRef
    decision_kind_ref: GovernanceDecisionKindRef
    policy_ref: GovernancePolicyRef
    authority_ref: ExternalAuthorityRef
    binder_ref: ExternalBinderRef
    bound_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.binding_ref, ExternalBindingRef)
            or self.binding_ref.family != "governance-binding"
            or not isinstance(self.occurrence_ref, ExternalBindingOccurrenceRef)
            or self.occurrence_ref.family != "governance-binding-occurrence"
            or not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.decision_ref, GovernanceDecisionRef)
            or not isinstance(self.decision_kind_ref, GovernanceDecisionKindRef)
            or not isinstance(self.policy_ref, GovernancePolicyRef)
            or not isinstance(self.authority_ref, ExternalAuthorityRef)
            or not isinstance(self.binder_ref, ExternalBinderRef)
        ):
            raise InvalidSkillExternalBindingRequest()
        _validate_time(self.bound_at)


@dataclass(frozen=True)
class SkillIntelligenceBindingRecord:
    binding_ref: ExternalBindingRef
    occurrence_ref: ExternalBindingOccurrenceRef
    identity: PublishedSkillVersionId
    fact_ref: IntelligenceFactRef
    analysis_ref: IntelligenceAnalysisRef | None
    fact_kind_ref: IntelligenceFactKindRef
    profile_ref: IntelligenceProfileRef
    authority_ref: ExternalAuthorityRef
    binder_ref: ExternalBinderRef
    observed_at: datetime
    bound_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.binding_ref, ExternalBindingRef)
            or self.binding_ref.family != "intelligence-binding"
            or not isinstance(self.occurrence_ref, ExternalBindingOccurrenceRef)
            or self.occurrence_ref.family != "intelligence-binding-occurrence"
            or not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.fact_ref, IntelligenceFactRef)
            or (
                self.analysis_ref is not None
                and not isinstance(self.analysis_ref, IntelligenceAnalysisRef)
            )
            or not isinstance(self.fact_kind_ref, IntelligenceFactKindRef)
            or not isinstance(self.profile_ref, IntelligenceProfileRef)
            or not isinstance(self.authority_ref, ExternalAuthorityRef)
            or not isinstance(self.binder_ref, ExternalBinderRef)
        ):
            raise InvalidSkillExternalBindingRequest()
        _validate_time(self.observed_at)
        _validate_time(self.bound_at)
        if self.observed_at > self.bound_at:
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True)
class SkillGovernanceBindingHistory:
    records: tuple[SkillGovernanceBindingRecord, ...]
    complete: bool

    def __post_init__(self) -> None:
        if not _tuple_of(self.records, SkillGovernanceBindingRecord) or not isinstance(
            self.complete, bool
        ):
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True)
class SkillIntelligenceBindingHistory:
    records: tuple[SkillIntelligenceBindingRecord, ...]
    complete: bool

    def __post_init__(self) -> None:
        if not _tuple_of(self.records, SkillIntelligenceBindingRecord) or not isinstance(
            self.complete, bool
        ):
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True)
class SkillGovernanceBindingProjection:
    identity: PublishedSkillVersionId
    history: SkillGovernanceBindingHistory
    decision_refs: tuple[GovernanceDecisionRef, ...]
    decision_kind_refs: tuple[GovernanceDecisionKindRef, ...]
    policy_refs: tuple[GovernancePolicyRef, ...]
    authority_refs: tuple[ExternalAuthorityRef, ...]
    binder_refs: tuple[ExternalBinderRef, ...]
    binding_refs: tuple[ExternalBindingRef, ...]
    occurrence_refs: tuple[ExternalBindingOccurrenceRef, ...]
    diagnostics: tuple[SkillExternalBindingDiagnostic, ...]
    complete: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.history, SkillGovernanceBindingHistory)
            or not _tuple_of(self.decision_refs, GovernanceDecisionRef)
            or not _tuple_of(self.decision_kind_refs, GovernanceDecisionKindRef)
            or not _tuple_of(self.policy_refs, GovernancePolicyRef)
            or not _tuple_of(self.authority_refs, ExternalAuthorityRef)
            or not _tuple_of(self.binder_refs, ExternalBinderRef)
            or not _tuple_of(self.binding_refs, ExternalBindingRef)
            or not _tuple_of(self.occurrence_refs, ExternalBindingOccurrenceRef)
            or not _tuple_of(self.diagnostics, SkillExternalBindingDiagnostic)
            or not isinstance(self.complete, bool)
            or self.complete != self.history.complete
        ):
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True)
class SkillIntelligenceBindingProjection:
    identity: PublishedSkillVersionId
    history: SkillIntelligenceBindingHistory
    fact_refs: tuple[IntelligenceFactRef, ...]
    analysis_refs: tuple[IntelligenceAnalysisRef, ...]
    fact_kind_refs: tuple[IntelligenceFactKindRef, ...]
    profile_refs: tuple[IntelligenceProfileRef, ...]
    authority_refs: tuple[ExternalAuthorityRef, ...]
    binder_refs: tuple[ExternalBinderRef, ...]
    binding_refs: tuple[ExternalBindingRef, ...]
    occurrence_refs: tuple[ExternalBindingOccurrenceRef, ...]
    diagnostics: tuple[SkillExternalBindingDiagnostic, ...]
    complete: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.history, SkillIntelligenceBindingHistory)
            or not _tuple_of(self.fact_refs, IntelligenceFactRef)
            or not _tuple_of(self.analysis_refs, IntelligenceAnalysisRef)
            or not _tuple_of(self.fact_kind_refs, IntelligenceFactKindRef)
            or not _tuple_of(self.profile_refs, IntelligenceProfileRef)
            or not _tuple_of(self.authority_refs, ExternalAuthorityRef)
            or not _tuple_of(self.binder_refs, ExternalBinderRef)
            or not _tuple_of(self.binding_refs, ExternalBindingRef)
            or not _tuple_of(self.occurrence_refs, ExternalBindingOccurrenceRef)
            or not _tuple_of(self.diagnostics, SkillExternalBindingDiagnostic)
            or not isinstance(self.complete, bool)
            or self.complete != self.history.complete
        ):
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True)
class SkillGovernanceBindingResult:
    identity: PublishedSkillVersionId
    record: SkillGovernanceBindingRecord
    outcome: SkillExternalBindingOutcome
    projection: SkillGovernanceBindingProjection | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.record, SkillGovernanceBindingRecord)
            or not isinstance(self.outcome, SkillExternalBindingOutcome)
            or (
                self.projection is not None
                and not isinstance(self.projection, SkillGovernanceBindingProjection)
            )
            or self.record.identity != self.identity
            or (self.projection is not None and self.projection.identity != self.identity)
        ):
            raise InvalidSkillExternalBindingRequest()


@dataclass(frozen=True)
class SkillIntelligenceBindingResult:
    identity: PublishedSkillVersionId
    record: SkillIntelligenceBindingRecord
    outcome: SkillExternalBindingOutcome
    projection: SkillIntelligenceBindingProjection | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.record, SkillIntelligenceBindingRecord)
            or not isinstance(self.outcome, SkillExternalBindingOutcome)
            or (
                self.projection is not None
                and not isinstance(self.projection, SkillIntelligenceBindingProjection)
            )
            or self.record.identity != self.identity
            or (self.projection is not None and self.projection.identity != self.identity)
        ):
            raise InvalidSkillExternalBindingRequest()


def _validate_time(value: datetime) -> None:
    try:
        validate_store_timestamp(value)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise InvalidSkillExternalBindingRequest() from exc


def _tuple_of(value: object, expected: type[object]) -> bool:
    return isinstance(value, tuple) and all(isinstance(item, expected) for item in value)
