from __future__ import annotations

import hashlib
from datetime import datetime

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillSemanticReference,
)
from synapse.skills.phase2_serialization import canonical_json_bytes
from synapse.skills.phase3_contracts import (
    SkillCatalogStore,
    SkillLifecycleHistory,
    SkillLifecycleStore,
    SkillStoreWriteOutcome,
)
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillActivationRecord,
    SkillLifecycleKind,
    SkillLifecycleRecord,
    SkillRevocationRecord,
)
from synapse.skills.phase3_values import SkillStoreQueryLimit, SkillStoreRecordId
from synapse.skills.phase6_errors import (
    AmbiguousSkillLifecycleOrdering,
    CorruptedSkillLifecycleHistory,
    IncompleteSkillLifecycleHistory,
    InvalidSkillActivationParent,
    InvalidSkillLifecycleTransition,
    InvalidSkillRollbackTarget,
    InvalidSkillSupersessionTarget,
    RevokedSkillVersion,
    SkillLifecycleConflict,
    SkillLifecycleStoreUnavailable,
    SkillVersionNotPublished,
)
from synapse.skills.phase6_models import (
    DeactivateSkillVersionRequest,
    DeprecateSkillVersionRequest,
    LifecycleEventRecord,
    ReenableSkillVersionRequest,
    RevokeSkillVersionRequest,
    RollbackSkillVersionRequest,
    SkillActivationParentVerificationPort,
    SkillActivationState,
    SkillLifecycleOutcome,
    SkillLifecycleProjection,
    SkillLifecycleResult,
    SkillSelectionState,
    SupersedeSkillVersionRequest,
    _BaseRequest,
)

_HISTORY_LIMIT = SkillStoreQueryLimit(200)


def _project_skill_lifecycle(
    publication: PublishedSkillVersionRecord,
    history: tuple[LifecycleEventRecord, ...],
    verified_activation_ids: frozenset[SkillStoreRecordId],
) -> SkillLifecycleProjection:
    """Pure replay into orthogonal activation, selection and advisory dimensions."""
    if not isinstance(publication, PublishedSkillVersionRecord) or not isinstance(
        history, tuple
    ):
        raise CorruptedSkillLifecycleHistory()
    ordered = _canonical_history(publication, history)
    activation = SkillActivationState.NEVER_ACTIVATED
    selection = SkillSelectionState.ELIGIBLE
    deprecated = False
    superseded_by: PublishedSkillVersionId | None = None
    rollback_target: PublishedSkillVersionId | None = None
    rollback_decision_ref: SkillSemanticReference | None = None
    last_record_id: SkillStoreRecordId | None = None
    active_installation_id: SkillStoreRecordId | None = None

    for record in ordered:
        if selection is SkillSelectionState.REVOKED:
            raise CorruptedSkillLifecycleHistory()
        last_record_id = record.record_id

        if isinstance(record, SkillActivationRecord):
            if (
                record.record_id not in verified_activation_ids
                or
                selection is not SkillSelectionState.ELIGIBLE
                or deprecated
                or activation is SkillActivationState.ACTIVE
            ):
                raise CorruptedSkillLifecycleHistory()
            activation = SkillActivationState.ACTIVE
            active_installation_id = record.installation_id
            continue

        if isinstance(record, SkillRevocationRecord):
            selection = SkillSelectionState.REVOKED
            activation = SkillActivationState.INACTIVE
            active_installation_id = None
            deprecated = False
            continue

        if record.kind is SkillLifecycleKind.DEACTIVATED:
            if activation is not SkillActivationState.ACTIVE:
                raise CorruptedSkillLifecycleHistory()
            activation = SkillActivationState.INACTIVE
            active_installation_id = None
        elif record.kind is SkillLifecycleKind.DEPRECATED:
            if deprecated or selection is not SkillSelectionState.ELIGIBLE:
                raise CorruptedSkillLifecycleHistory()
            deprecated = True
        elif record.kind is SkillLifecycleKind.REENABLED:
            if not deprecated:
                raise CorruptedSkillLifecycleHistory()
            deprecated = False
        elif record.kind is SkillLifecycleKind.SUPERSEDED:
            if selection is not SkillSelectionState.ELIGIBLE:
                raise CorruptedSkillLifecycleHistory()
            selection = SkillSelectionState.SUPERSEDED
            superseded_by = record.related_version
        elif record.kind is SkillLifecycleKind.ROLLBACK_REFERENCED:
            if rollback_target is not None:
                raise CorruptedSkillLifecycleHistory()
            rollback_target = record.related_version
            rollback_decision_ref = record.decision_ref
        else:
            raise CorruptedSkillLifecycleHistory()

    revoked = selection is SkillSelectionState.REVOKED
    superseded = selection is SkillSelectionState.SUPERSEDED
    active = activation is SkillActivationState.ACTIVE and not revoked
    resolvable = selection is SkillSelectionState.ELIGIBLE
    activatable = (
        selection is SkillSelectionState.ELIGIBLE
        and not deprecated
        and activation is not SkillActivationState.ACTIVE
    )
    return SkillLifecycleProjection(
        identity=publication.identity,
        activation_state=activation,
        selection_state=selection,
        deprecated=deprecated,
        revoked=revoked,
        superseded=superseded,
        resolvable=resolvable,
        activatable=activatable,
        active=active,
        active_selection_eligible=active and resolvable and not deprecated,
        active_installation_id=active_installation_id,
        superseded_by=superseded_by,
        rollback_target=rollback_target,
        rollback_decision_ref=rollback_decision_ref,
        last_record_id=last_record_id,
    )


class SkillLifecycleService:
    """Optimistic local authority for published-version lifecycle facts."""

    def __init__(
        self,
        catalog: SkillCatalogStore,
        lifecycle: SkillLifecycleStore,
        activation_parents: SkillActivationParentVerificationPort,
    ) -> None:
        self._catalog = catalog
        self._lifecycle = lifecycle
        self._activation_parents = activation_parents

    def deactivate(
        self, request: DeactivateSkillVersionRequest
    ) -> SkillLifecycleResult:
        return self._apply(
            request.identity,
            self._lifecycle_record(request, SkillLifecycleKind.DEACTIVATED),
        )

    def activate(self, record: SkillActivationRecord) -> SkillLifecycleResult:
        if not isinstance(record, SkillActivationRecord):
            raise InvalidSkillLifecycleTransition()
        return self._apply(record.identity, record)

    def deprecate(
        self, request: DeprecateSkillVersionRequest
    ) -> SkillLifecycleResult:
        return self._apply(
            request.identity,
            self._lifecycle_record(request, SkillLifecycleKind.DEPRECATED),
        )

    def reenable(
        self, request: ReenableSkillVersionRequest
    ) -> SkillLifecycleResult:
        return self._apply(
            request.identity,
            self._lifecycle_record(request, SkillLifecycleKind.REENABLED),
        )

    def supersede(
        self, request: SupersedeSkillVersionRequest
    ) -> SkillLifecycleResult:
        self._validate_supersession_target(request.identity, request.replacement)
        return self._apply(
            request.identity,
            self._lifecycle_record(
                request,
                SkillLifecycleKind.SUPERSEDED,
                related=request.replacement,
                decision_ref=request.decision_ref,
            ),
        )

    def rollback(
        self, request: RollbackSkillVersionRequest
    ) -> SkillLifecycleResult:
        self._validate_rollback_target(request.identity, request.target)
        assert request.decision_ref is not None
        return self._apply(
            request.identity,
            self._lifecycle_record(
                request,
                SkillLifecycleKind.ROLLBACK_REFERENCED,
                related=request.target,
                decision_ref=request.decision_ref,
            ),
        )

    def revoke(self, request: RevokeSkillVersionRequest) -> SkillLifecycleResult:
        assert request.decision_ref is not None
        record = SkillRevocationRecord(
            record_id=self._record_id(
                "revocation",
                "revoked",
                request,
                decision_ref=request.decision_ref,
                evidence_ref=request.evidence_ref,
            ),
            identity=request.identity,
            revoked_at=request.occurred_at,
            actor_ref=request.actor_ref,
            reason=request.reason,
            revocation_ref=request.decision_ref,
            evidence_ref=request.evidence_ref,
        )
        return self._apply(request.identity, record)

    def projection(
        self, identity: PublishedSkillVersionId
    ) -> SkillLifecycleProjection:
        publication = self._published(identity)
        return self._project(publication, self.history(identity))

    def history(
        self, identity: PublishedSkillVersionId
    ) -> tuple[LifecycleEventRecord, ...]:
        self._published(identity)
        try:
            result = self._lifecycle.history(identity, _HISTORY_LIMIT)
        except SkillStoreUnavailable as exc:
            raise SkillLifecycleStoreUnavailable() from exc
        if not isinstance(result, SkillLifecycleHistory):
            raise CorruptedSkillLifecycleHistory()
        if not result.complete:
            raise IncompleteSkillLifecycleHistory()
        return _canonical_history(self._published(identity), result.records)

    def _apply(
        self,
        identity: PublishedSkillVersionId,
        candidate: LifecycleEventRecord,
    ) -> SkillLifecycleResult:
        publication = self._published(identity)
        history = self.history(identity)
        for existing in history:
            if existing.record_id == candidate.record_id:
                if existing != candidate:
                    raise SkillLifecycleConflict()
                return SkillLifecycleResult(
                    identity=identity,
                    record=existing,
                    outcome=SkillLifecycleOutcome.IDEMPOTENT_REPLAY,
                    projection=self._project(publication, history),
                )
        if history:
            candidate_time = _event_timestamp(candidate)
            maximum = max(_event_timestamp(record) for record in history)
            if candidate_time < maximum:
                raise InvalidSkillLifecycleTransition()
            if candidate_time == maximum:
                raise AmbiguousSkillLifecycleOrdering()
        try:
            projected = self._project(publication, (*history, candidate))
        except CorruptedSkillLifecycleHistory as exc:
            current = self._project(publication, history)
            if current.revoked:
                raise RevokedSkillVersion() from exc
            raise InvalidSkillLifecycleTransition() from exc
        try:
            outcome = self._append(candidate)
        except SkillStoreDivergentDuplicate as exc:
            raise SkillLifecycleConflict() from exc
        except SkillStoreUnavailable as exc:
            raise SkillLifecycleStoreUnavailable() from exc
        if outcome is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY:
            refreshed = self.history(identity)
            reconciled = next(
                (
                    record
                    for record in refreshed
                    if record.record_id == candidate.record_id
                ),
                None,
            )
            if reconciled != candidate:
                raise SkillLifecycleConflict()
            projected = self._project(publication, refreshed)
        return SkillLifecycleResult(
            identity=identity,
            record=candidate,
            outcome=SkillLifecycleOutcome(outcome.value),
            projection=projected,
        )

    def _validate_supersession_target(
        self,
        source: PublishedSkillVersionId,
        target: PublishedSkillVersionId,
    ) -> None:
        self._validate_distinct_compatible_target(
            source, target, InvalidSkillSupersessionTarget
        )
        visited = {source}
        current = target
        while True:
            if current in visited:
                raise InvalidSkillSupersessionTarget()
            visited.add(current)
            projection = self.projection(current)
            if projection.revoked:
                raise InvalidSkillSupersessionTarget()
            if projection.superseded_by is None:
                return
            current = projection.superseded_by

    def _validate_rollback_target(
        self,
        source: PublishedSkillVersionId,
        target: PublishedSkillVersionId,
    ) -> None:
        self._validate_distinct_compatible_target(
            source, target, InvalidSkillRollbackTarget
        )
        if self.projection(target).revoked:
            raise InvalidSkillRollbackTarget()

    def _validate_distinct_compatible_target(
        self,
        source: PublishedSkillVersionId,
        target: PublishedSkillVersionId,
        error: type[InvalidSkillSupersessionTarget | InvalidSkillRollbackTarget],
    ) -> None:
        self._published(source)
        if (
            not isinstance(target, PublishedSkillVersionId)
            or target == source
            or target.skill_id != source.skill_id
        ):
            raise error()
        try:
            self._published(target)
        except SkillVersionNotPublished as exc:
            raise error() from exc

    def _published(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        if not isinstance(identity, PublishedSkillVersionId):
            raise SkillVersionNotPublished()
        try:
            record = self._catalog.get_version(identity)
        except SkillStoreNotFound as exc:
            raise SkillVersionNotPublished() from exc
        except SkillStoreUnavailable as exc:
            raise SkillLifecycleStoreUnavailable() from exc
        if not isinstance(record, PublishedSkillVersionRecord) or record.identity != identity:
            raise SkillLifecycleConflict()
        return record

    def _project(
        self,
        publication: PublishedSkillVersionRecord,
        history: tuple[LifecycleEventRecord, ...],
    ) -> SkillLifecycleProjection:
        activation_ids = frozenset(
            record.record_id
            for record in history
            if isinstance(record, SkillActivationRecord)
        )
        projection = _project_skill_lifecycle(
            publication, history, activation_ids
        )
        if (
            projection.active_installation_id is not None
            and not self._activation_parents.is_valid_parent(
                publication.identity, projection.active_installation_id
            )
        ):
            raise InvalidSkillActivationParent()
        return projection

    def _append(self, record: LifecycleEventRecord) -> SkillStoreWriteOutcome:
        if isinstance(record, SkillActivationRecord):
            return self._lifecycle.append_activation(record)
        if isinstance(record, SkillRevocationRecord):
            return self._lifecycle.append_revocation(record)
        return self._lifecycle.append_lifecycle(record)

    @classmethod
    def _lifecycle_record(
        cls,
        request: (
            DeactivateSkillVersionRequest
            | DeprecateSkillVersionRequest
            | ReenableSkillVersionRequest
            | SupersedeSkillVersionRequest
            | RollbackSkillVersionRequest
        ),
        kind: SkillLifecycleKind,
        *,
        related: PublishedSkillVersionId | None = None,
        decision_ref: SkillSemanticReference | None = None,
    ) -> SkillLifecycleRecord:
        return SkillLifecycleRecord(
            record_id=cls._record_id(
                "lifecycle",
                kind.value,
                request,
                related=related,
                decision_ref=decision_ref,
            ),
            identity=request.identity,
            kind=kind,
            reason=request.reason,
            occurred_at=request.occurred_at,
            actor_ref=request.actor_ref,
            related_version=related,
            decision_ref=decision_ref,
        )

    @staticmethod
    def _record_id(
        namespace: str,
        operation: str,
        request: _BaseRequest,
        *,
        related: PublishedSkillVersionId | None = None,
        decision_ref: SkillSemanticReference | None = None,
        evidence_ref: SkillSemanticReference | None = None,
    ) -> SkillStoreRecordId:
        semantic_projection = (
            namespace,
            operation,
            request.identity.to_canonical_text(),
            request.actor_ref.to_canonical_text(),
            request.reason.value,
            request.occurred_at.isoformat(timespec="microseconds"),
            request.event_ref.to_canonical_text(),
            related.to_canonical_text() if related is not None else "",
            decision_ref.to_canonical_text() if decision_ref is not None else "",
            evidence_ref.to_canonical_text() if evidence_ref is not None else "",
        )
        digest = hashlib.sha256(canonical_json_bytes(semantic_projection)).hexdigest()
        return SkillStoreRecordId(f"{namespace}:{digest}")


def _canonical_history(
    publication: PublishedSkillVersionRecord,
    history: tuple[LifecycleEventRecord, ...],
) -> tuple[LifecycleEventRecord, ...]:
    by_id: dict[SkillStoreRecordId, LifecycleEventRecord] = {}
    for record in history:
        if (
            not isinstance(
                record,
                (SkillLifecycleRecord, SkillActivationRecord, SkillRevocationRecord),
            )
            or record.identity != publication.identity
            or _event_timestamp(record) < publication.recorded_at
        ):
            raise CorruptedSkillLifecycleHistory()
        existing = by_id.get(record.record_id)
        if existing is not None and existing != record:
            raise CorruptedSkillLifecycleHistory()
        by_id[record.record_id] = record
    ordered = tuple(sorted(by_id.values(), key=_event_order))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if _event_timestamp(previous) == _event_timestamp(current):
            raise AmbiguousSkillLifecycleOrdering()
    return ordered


def _event_timestamp(record: LifecycleEventRecord) -> datetime:
    if isinstance(record, SkillActivationRecord):
        return record.activated_at
    if isinstance(record, SkillRevocationRecord):
        return record.revoked_at
    return record.occurred_at


def _event_order(record: LifecycleEventRecord) -> tuple[datetime, str]:
    return _event_timestamp(record), str(record.record_id)
