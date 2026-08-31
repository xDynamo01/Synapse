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
    _governance_binding_ref as _binding_ref_from_values,
)
from synapse.skills.phase10_models import (
    BindSkillGovernanceDecisionRequest,
    SkillExternalBindingOutcome,
    SkillGovernanceBindingHistory,
    SkillGovernanceBindingProjection,
    SkillGovernanceBindingRecord,
    SkillGovernanceBindingResult,
)
from synapse.skills.phase10_projection import (
    _canonical_governance_history,
    _governance_projection,
)
from synapse.skills.phase10_refs import ExternalBindingOccurrenceRef, ExternalBindingRef


class SkillGovernanceBindingService:
    """Binds opaque Governance references without interpreting a decision."""

    def __init__(
        self,
        catalog: SkillCatalogStore,
        bindings: SkillExternalBindingStore,
        history_limit: SkillStoreQueryLimit,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._history_limit = history_limit

    def bind(self, request: BindSkillGovernanceDecisionRequest) -> SkillGovernanceBindingResult:
        publication = self._published(request.identity)
        if request.bound_at < publication.recorded_at:
            raise SkillExternalBindingCorrespondenceMismatch()
        candidate = SkillGovernanceBindingRecord(
            binding_ref=_governance_binding_ref(request),
            occurrence_ref=_governance_occurrence_ref(request),
            identity=request.identity,
            decision_ref=request.decision_ref,
            decision_kind_ref=request.decision_kind_ref,
            policy_ref=request.policy_ref,
            authority_ref=request.authority_ref,
            binder_ref=request.binder_ref,
            bound_at=request.bound_at,
        )
        history = self.history(request.identity)
        if not history.complete:
            raise IncompleteSkillExternalBindingHistory()
        existing = _record_by_occurrence(history, candidate.occurrence_ref)
        if existing is not None:
            if existing != candidate:
                raise SkillExternalBindingDivergentDuplicate()
            return SkillGovernanceBindingResult(
                request.identity,
                existing,
                SkillExternalBindingOutcome.IDEMPOTENT_REPLAY,
                _governance_projection(request.identity, history),
            )
        try:
            outcome = self._bindings.append_governance(candidate)
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
        return SkillGovernanceBindingResult(
            request.identity,
            persisted,
            SkillExternalBindingOutcome(outcome.value),
            _governance_projection(request.identity, refreshed),
        )

    def history(self, identity: PublishedSkillVersionId) -> SkillGovernanceBindingHistory:
        self._published(identity)
        try:
            history = self._bindings.list_governance_for_version(identity, self._history_limit)
        except SkillStoreUnavailable as exc:
            raise SkillExternalBindingStoreUnavailable() from exc
        return _canonical_governance_history(identity, history, self._history_limit)

    def projection(self, identity: PublishedSkillVersionId) -> SkillGovernanceBindingProjection:
        return _governance_projection(identity, self.history(identity))

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


def _governance_binding_ref(
    request: BindSkillGovernanceDecisionRequest,
) -> ExternalBindingRef:
    return _binding_ref_from_values(
        request.identity,
        request.authority_ref,
        request.decision_ref,
        request.decision_kind_ref,
        request.policy_ref,
    )


def _governance_occurrence_ref(
    request: BindSkillGovernanceDecisionRequest,
) -> ExternalBindingOccurrenceRef:
    return _binding_occurrence_ref(
        "governance",
        _governance_binding_ref(request),
        request.binder_ref,
        request.bound_at,
    )


def _record_by_occurrence(
    history: SkillGovernanceBindingHistory,
    occurrence_ref: ExternalBindingOccurrenceRef,
) -> SkillGovernanceBindingRecord | None:
    return next(
        (record for record in history.records if record.occurrence_ref == occurrence_ref),
        None,
    )
