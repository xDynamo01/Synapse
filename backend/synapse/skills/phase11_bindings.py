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
from synapse.skills.phase11_contracts import SkillPrivateEvalBindingStore
from synapse.skills.phase11_errors import (
    IncompleteSkillPrivateEvalBindingHistory,
    InvalidSkillPrivateEvalBindingHistory,
    SkillPrivateEvalBindingCorrespondenceMismatch,
    SkillPrivateEvalBindingDivergentDuplicate,
    SkillPrivateEvalBindingStoreUnavailable,
    SkillPrivateEvalBindingSubjectNotPublished,
)
from synapse.skills.phase11_identity import (
    _private_eval_binding_ref,
    _private_eval_occurrence_ref,
)
from synapse.skills.phase11_models import (
    BindSkillPrivateEvalResultRequest,
    SkillPrivateEvalBindingHistory,
    SkillPrivateEvalBindingOutcome,
    SkillPrivateEvalBindingProjection,
    SkillPrivateEvalBindingRecord,
    SkillPrivateEvalBindingResult,
)
from synapse.skills.phase11_projection import (
    _canonical_private_eval_history,
    _private_eval_projection,
)
from synapse.skills.phase11_refs import PrivateEvalBindingOccurrenceRef


class SkillPrivateEvalBindingService:
    """Binds opaque Private Evals facts without interpreting their result."""

    def __init__(
        self,
        catalog: SkillCatalogStore,
        bindings: SkillPrivateEvalBindingStore,
        history_limit: SkillStoreQueryLimit,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._history_limit = history_limit

    def bind(
        self, request: BindSkillPrivateEvalResultRequest
    ) -> SkillPrivateEvalBindingResult:
        publication = self._published(request.identity)
        if request.bound_at < publication.recorded_at:
            raise SkillPrivateEvalBindingCorrespondenceMismatch()
        binding_ref = _private_eval_binding_ref(request)
        candidate = SkillPrivateEvalBindingRecord(
            binding_ref=binding_ref,
            occurrence_ref=_private_eval_occurrence_ref(
                binding_ref,
                request.binder_ref,
                request.bound_at,
            ),
            identity=request.identity,
            granularity=request.granularity,
            run_ref=request.run_ref,
            result_ref=request.result_ref,
            verdict_ref=request.verdict_ref,
            suite_ref=request.suite_ref,
            case_ref=request.case_ref,
            profile_ref=request.profile_ref,
            baseline_ref=request.baseline_ref,
            comparison_ref=request.comparison_ref,
            regression_ref=request.regression_ref,
            evidence_refs=request.evidence_refs,
            binder_ref=request.binder_ref,
            evaluated_at=request.evaluated_at,
            bound_at=request.bound_at,
        )
        history = self.history(request.identity)
        if not history.complete:
            raise IncompleteSkillPrivateEvalBindingHistory()
        if any(
            record.run_ref == candidate.run_ref
            and record.result_ref == candidate.result_ref
            and record.evaluated_at != candidate.evaluated_at
            for record in history.records
        ):
            raise SkillPrivateEvalBindingDivergentDuplicate()
        existing = _record_by_occurrence(history, candidate.occurrence_ref)
        if existing is not None:
            if existing != candidate:
                raise SkillPrivateEvalBindingDivergentDuplicate()
            return SkillPrivateEvalBindingResult(
                request.identity,
                existing,
                SkillPrivateEvalBindingOutcome.IDEMPOTENT_REPLAY,
                _private_eval_projection(request.identity, history),
            )
        try:
            outcome = self._bindings.append_private_eval(candidate)
        except SkillStoreDivergentDuplicate as exc:
            raise SkillPrivateEvalBindingDivergentDuplicate() from exc
        except SkillStoreUnavailable as exc:
            raise SkillPrivateEvalBindingStoreUnavailable() from exc
        if not isinstance(outcome, SkillStoreWriteOutcome):
            raise InvalidSkillPrivateEvalBindingHistory()
        refreshed = self.history(request.identity)
        if not refreshed.complete:
            raise IncompleteSkillPrivateEvalBindingHistory()
        persisted = _record_by_occurrence(refreshed, candidate.occurrence_ref)
        if persisted != candidate:
            raise SkillPrivateEvalBindingDivergentDuplicate()
        return SkillPrivateEvalBindingResult(
            request.identity,
            persisted,
            SkillPrivateEvalBindingOutcome(outcome.value),
            _private_eval_projection(request.identity, refreshed),
        )

    def history(self, identity: PublishedSkillVersionId) -> SkillPrivateEvalBindingHistory:
        self._published(identity)
        try:
            history = self._bindings.list_private_evals_for_version(
                identity,
                self._history_limit,
            )
        except SkillStoreUnavailable as exc:
            raise SkillPrivateEvalBindingStoreUnavailable() from exc
        return _canonical_private_eval_history(identity, history, self._history_limit)

    def projection(
        self, identity: PublishedSkillVersionId
    ) -> SkillPrivateEvalBindingProjection:
        return _private_eval_projection(identity, self.history(identity))

    def _published(self, identity: PublishedSkillVersionId) -> PublishedSkillVersionRecord:
        if not isinstance(identity, PublishedSkillVersionId):
            raise SkillPrivateEvalBindingSubjectNotPublished()
        try:
            record = self._catalog.get_version(identity)
        except SkillStoreNotFound as exc:
            raise SkillPrivateEvalBindingSubjectNotPublished() from exc
        except SkillStoreUnavailable as exc:
            raise SkillPrivateEvalBindingStoreUnavailable() from exc
        if not isinstance(record, PublishedSkillVersionRecord) or record.identity != identity:
            raise SkillPrivateEvalBindingCorrespondenceMismatch()
        return record


def _record_by_occurrence(
    history: SkillPrivateEvalBindingHistory,
    occurrence_ref: PrivateEvalBindingOccurrenceRef,
) -> SkillPrivateEvalBindingRecord | None:
    return next(
        (record for record in history.records if record.occurrence_ref == occurrence_ref),
        None,
    )
