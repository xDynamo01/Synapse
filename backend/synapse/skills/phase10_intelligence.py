from __future__ import annotations

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase3_contracts import SkillCatalogStore, SkillStoreWriteOutcome
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase10_contracts import SkillExternalBindingStore
from synapse.skills.phase10_errors import (
    IncompleteSkillExternalBindingHistory,
    InvalidSkillExternalBindingHistory,
    SkillExternalBindingCorrespondenceMismatch,
    SkillExternalBindingDivergentDuplicate,
    SkillExternalBindingStoreUnavailable,
    SkillExternalBindingSubjectNotPublished,
)
from synapse.skills.phase10_identity import (
    _binding_occurrence_ref,
)
from synapse.skills.phase10_identity import (
    _intelligence_binding_ref as _binding_ref_from_values,
)
from synapse.skills.phase10_models import (
    BindSkillIntelligenceFactRequest,
    SkillExternalBindingOutcome,
    SkillIntelligenceBindingHistory,
    SkillIntelligenceBindingProjection,
    SkillIntelligenceBindingRecord,
    SkillIntelligenceBindingResult,
)
from synapse.skills.phase10_projection import (
    _canonical_intelligence_history,
    _intelligence_projection,
)
from synapse.skills.phase10_refs import ExternalBindingOccurrenceRef, ExternalBindingRef


class SkillIntelligenceBindingService:
    """Binds opaque Intelligence facts without asserting that they are true."""

    def __init__(
        self,
        catalog: SkillCatalogStore,
        bindings: SkillExternalBindingStore,
        history_limit: SkillStoreQueryLimit,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._history_limit = history_limit

    def bind(self, request: BindSkillIntelligenceFactRequest) -> SkillIntelligenceBindingResult:
        publication = self._published(request.identity)
        if request.bound_at < publication.recorded_at:
            raise SkillExternalBindingCorrespondenceMismatch()
        candidate = SkillIntelligenceBindingRecord(
            binding_ref=_intelligence_binding_ref(request),
            occurrence_ref=_intelligence_occurrence_ref(request),
            identity=request.identity,
            fact_ref=request.fact_ref,
            analysis_ref=request.analysis_ref,
            fact_kind_ref=request.fact_kind_ref,
            profile_ref=request.profile_ref,
            authority_ref=request.authority_ref,
            binder_ref=request.binder_ref,
            observed_at=request.observed_at,
            bound_at=request.bound_at,
        )
        history = self.history(request.identity)
        if not history.complete:
            raise IncompleteSkillExternalBindingHistory()
        if any(
            record.authority_ref == candidate.authority_ref
            and record.fact_ref == candidate.fact_ref
            and record.observed_at != candidate.observed_at
            for record in history.records
        ):
            raise SkillExternalBindingDivergentDuplicate()
        existing = _record_by_occurrence(history, candidate.occurrence_ref)
        if existing is not None:
            if existing != candidate:
                raise SkillExternalBindingDivergentDuplicate()
            return SkillIntelligenceBindingResult(
                request.identity,
                existing,
                SkillExternalBindingOutcome.IDEMPOTENT_REPLAY,
                _intelligence_projection(request.identity, history),
            )
        try:
            outcome = self._bindings.append_intelligence(candidate)
        except SkillStoreDivergentDuplicate as exc:
            raise SkillExternalBindingDivergentDuplicate() from exc
        except SkillStoreUnavailable as exc:
            raise SkillExternalBindingStoreUnavailable() from exc
        if not isinstance(outcome, SkillStoreWriteOutcome):
            raise InvalidSkillExternalBindingHistory()
        refreshed = self.history(request.identity)
        if not refreshed.complete:
            raise IncompleteSkillExternalBindingHistory()
        persisted = _record_by_occurrence(refreshed, candidate.occurrence_ref)
        if persisted != candidate:
            raise SkillExternalBindingDivergentDuplicate()
        return SkillIntelligenceBindingResult(
            request.identity,
            persisted,
            SkillExternalBindingOutcome(outcome.value),
            _intelligence_projection(request.identity, refreshed),
        )

    def history(self, identity: PublishedSkillVersionId) -> SkillIntelligenceBindingHistory:
        self._published(identity)
        try:
            history = self._bindings.list_intelligence_for_version(identity, self._history_limit)
        except SkillStoreUnavailable as exc:
            raise SkillExternalBindingStoreUnavailable() from exc
        return _canonical_intelligence_history(identity, history, self._history_limit)

    def projection(self, identity: PublishedSkillVersionId) -> SkillIntelligenceBindingProjection:
        return _intelligence_projection(identity, self.history(identity))

    def _published(self, identity: PublishedSkillVersionId) -> PublishedSkillVersionRecord:
        if not isinstance(identity, PublishedSkillVersionId):
            raise SkillExternalBindingSubjectNotPublished()
        try:
            record = self._catalog.get_version(identity)
        except SkillStoreNotFound as exc:
            raise SkillExternalBindingSubjectNotPublished() from exc
        except SkillStoreUnavailable as exc:
            raise SkillExternalBindingStoreUnavailable() from exc
        if not isinstance(record, PublishedSkillVersionRecord) or record.identity != identity:
            raise SkillExternalBindingCorrespondenceMismatch()
        return record


def _intelligence_binding_ref(
    request: BindSkillIntelligenceFactRequest,
) -> ExternalBindingRef:
    return _binding_ref_from_values(
        request.identity,
        request.authority_ref,
        request.fact_ref,
        request.fact_kind_ref,
        request.profile_ref,
        request.analysis_ref,
    )


def _intelligence_occurrence_ref(
    request: BindSkillIntelligenceFactRequest,
) -> ExternalBindingOccurrenceRef:
    return _binding_occurrence_ref(
        "intelligence",
        _intelligence_binding_ref(request),
        request.binder_ref,
        request.bound_at,
    )


def _record_by_occurrence(
    history: SkillIntelligenceBindingHistory,
    occurrence_ref: ExternalBindingOccurrenceRef,
) -> SkillIntelligenceBindingRecord | None:
    return next(
        (record for record in history.records if record.occurrence_ref == occurrence_ref),
        None,
    )
