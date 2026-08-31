from __future__ import annotations

import hashlib
from datetime import datetime

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
)
from synapse.skills.phase2_serialization import canonical_json_bytes
from synapse.skills.phase3_contracts import (
    SkillCatalogStore,
    SkillInstallationHistory,
    SkillInstallationStore,
    SkillStoreWriteOutcome,
)
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreInvalidParentReference,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillActivationRecord,
    SkillInstallationRecord,
    SkillInstallationTerminationReason,
    SkillInstallationTerminationRecord,
    SkillLifecycleRecord,
)
from synapse.skills.phase3_values import SkillStoreQueryLimit, SkillStoreRecordId
from synapse.skills.phase4_models import (
    VerifiedSkillContentSnapshot,
    content_fingerprint,
)
from synapse.skills.phase6_errors import (
    InvalidSkillActivationParent,
    InvalidSkillLifecycleTransition,
    RevokedSkillVersion,
    SkillLifecycleConflict,
)
from synapse.skills.phase6_lifecycle import SkillLifecycleService
from synapse.skills.phase6_models import (
    DeactivateSkillVersionRequest,
    SkillActivationParentVerificationPort,
)
from synapse.skills.phase7_errors import (
    ActiveSkillInstallationTerminationForbidden,
    AmbiguousSkillInstallationOrdering,
    CorruptedSkillInstallationHistory,
    IncompleteSkillInstallationHistory,
    InvalidOperationalActivationParent,
    InvalidOperationalActivationTransition,
    SkillInstallationConflict,
    SkillInstallationCorrupted,
    SkillInstallationNotFound,
    SkillInstallationSnapshotMismatch,
    SkillInstallationStoreUnavailable,
    SkillInstallationTerminated,
    SkillInstallationVersionNotPublished,
)
from synapse.skills.phase7_models import (
    ActivateInstalledSkillVersionRequest,
    DeactivateInstalledSkillVersionRequest,
    InstallationFact,
    InstalledSkillContentRef,
    InstallVerifiedSkillVersionRequest,
    SkillActivationResult,
    SkillInstallationOutcome,
    SkillInstallationProjection,
    SkillInstallationResult,
    SkillInstallationTerminationResult,
    SkillOperationalProjection,
    TerminateSkillInstallationRequest,
)

_HISTORY_LIMIT = SkillStoreQueryLimit(200)


class SkillInstallationService:
    """Registers verified content-address metadata; never asserts physical custody."""

    def __init__(
        self,
        catalog: SkillCatalogStore,
        installations: SkillInstallationStore,
    ) -> None:
        self._catalog = catalog
        self._installations = installations

    def install(
        self, request: InstallVerifiedSkillVersionRequest
    ) -> SkillInstallationResult:
        publication = self._published(request.identity)
        self._validate_correspondence(publication, request)
        if request.installed_at < publication.recorded_at:
            raise SkillInstallationSnapshotMismatch()
        record = SkillInstallationRecord(
            record_id=_installation_id(
                request.identity,
                request.local_content,
            ),
            identity=request.identity,
            content_fingerprint=request.local_content.content_fingerprint,
            content_ref=request.local_content.content_ref,
            storage_profile_ref=request.local_content.storage_profile_ref,
            installed_at=request.installed_at,
            actor_ref=request.actor_ref,
            registration_ref=request.registration_ref,
        )
        history = self.history(request.identity)
        existing = _record_by_id(history, record.record_id)
        if existing is not None:
            if not isinstance(existing, SkillInstallationRecord) or not (
                _installation_semantics(existing) == _installation_semantics(record)
            ):
                raise SkillInstallationConflict()
            return SkillInstallationResult(
                identity=request.identity,
                record=existing,
                outcome=SkillInstallationOutcome.IDEMPOTENT_REPLAY,
                projection=_project_installations(publication, history),
            )
        _validate_new_fact_time(history, record.installed_at)
        try:
            outcome = self._installations.append_installation(record)
        except SkillStoreDivergentDuplicate as exc:
            raise SkillInstallationConflict() from exc
        except SkillStoreUnavailable as exc:
            raise SkillInstallationStoreUnavailable() from exc
        if outcome is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY:
            history = self.history(request.identity)
            persisted = _record_by_id(history, record.record_id)
            if not isinstance(persisted, SkillInstallationRecord) or not (
                _installation_semantics(persisted) == _installation_semantics(record)
            ):
                raise SkillInstallationConflict()
            record = persisted
        else:
            history = (*history, record)
        return SkillInstallationResult(
            identity=request.identity,
            record=record,
            outcome=SkillInstallationOutcome(outcome.value),
            projection=_project_installations(publication, history),
        )

    def history(
        self, identity: PublishedSkillVersionId
    ) -> tuple[InstallationFact, ...]:
        publication = self._published(identity)
        try:
            result = self._installations.history(identity, _HISTORY_LIMIT)
        except SkillStoreUnavailable as exc:
            raise SkillInstallationStoreUnavailable() from exc
        if not isinstance(result, SkillInstallationHistory):
            raise CorruptedSkillInstallationHistory()
        if not result.complete:
            raise IncompleteSkillInstallationHistory()
        return _canonical_installation_history(publication, result.records)

    def projection(
        self, identity: PublishedSkillVersionId
    ) -> SkillInstallationProjection:
        publication = self._published(identity)
        return _project_installations(publication, self.history(identity))

    def get_installation(
        self,
        identity: PublishedSkillVersionId,
        installation_id: SkillStoreRecordId,
    ) -> SkillInstallationRecord:
        if not isinstance(installation_id, SkillStoreRecordId):
            raise SkillInstallationNotFound()
        record = _record_by_id(self.history(identity), installation_id)
        if not isinstance(record, SkillInstallationRecord):
            raise SkillInstallationNotFound()
        return record

    def _published(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        if not isinstance(identity, PublishedSkillVersionId):
            raise SkillInstallationVersionNotPublished()
        try:
            record = self._catalog.get_version(identity)
        except SkillStoreNotFound as exc:
            raise SkillInstallationVersionNotPublished() from exc
        except SkillStoreUnavailable as exc:
            raise SkillInstallationStoreUnavailable() from exc
        if not isinstance(record, PublishedSkillVersionRecord) or record.identity != identity:
            raise SkillInstallationConflict()
        return record

    @staticmethod
    def _validate_correspondence(
        publication: PublishedSkillVersionRecord,
        request: InstallVerifiedSkillVersionRequest,
    ) -> None:
        snapshot = request.snapshot
        try:
            snapshot.__post_init__()
        except (AttributeError, ValueError) as exc:
            raise SkillInstallationSnapshotMismatch() from exc
        if (
            not isinstance(snapshot, VerifiedSkillContentSnapshot)
            or publication.identity != request.identity
            or publication.manifest != snapshot.manifest
            or request.identity
            != PublishedSkillVersionId.from_manifest(
                snapshot.manifest, snapshot.content_fingerprint
            )
            or snapshot.technical_identity
            != (
                request.identity.manifest_fingerprint,
                request.identity.content_fingerprint,
            )
            or content_fingerprint(snapshot.assets) != snapshot.content_fingerprint
            or request.local_content.content_fingerprint
            != snapshot.content_fingerprint
            or not _manifest_assets_correspond(snapshot)
        ):
            raise SkillInstallationSnapshotMismatch()


class SkillInstallationParentVerifier(SkillActivationParentVerificationPort):
    """Concrete domain verifier over complete installation facts."""

    def __init__(self, installations: SkillInstallationService) -> None:
        self._installations = installations

    def is_valid_parent(
        self,
        identity: PublishedSkillVersionId,
        installation_id: SkillStoreRecordId,
    ) -> bool:
        try:
            self.validate_parent(identity, installation_id)
        except (
            SkillInstallationCorrupted,
            SkillInstallationNotFound,
            SkillInstallationTerminated,
        ):
            return False
        return True

    def validate_parent(
        self,
        identity: PublishedSkillVersionId,
        installation_id: SkillStoreRecordId,
    ) -> SkillInstallationRecord:
        record = self._installations.get_installation(identity, installation_id)
        projection = self._installations.projection(identity)
        if installation_id in projection.corrupted_installation_ids:
            raise SkillInstallationCorrupted()
        if installation_id in projection.terminated_installation_ids:
            raise SkillInstallationTerminated()
        if record not in projection.current_registrations:
            raise InvalidOperationalActivationParent()
        if (
            record.identity != identity
            or record.content_fingerprint != identity.content_fingerprint
        ):
            raise InvalidOperationalActivationParent()
        return record


class SkillInstallationTerminationService:
    """Terminates an inactive exact installation without hidden deactivation."""

    def __init__(
        self,
        installation_service: SkillInstallationService,
        installation_store: SkillInstallationStore,
        lifecycle: SkillLifecycleService,
    ) -> None:
        self._service = installation_service
        self._store = installation_store
        self._lifecycle = lifecycle

    def terminate(
        self, request: TerminateSkillInstallationRequest
    ) -> SkillInstallationTerminationResult:
        parent = self._service.get_installation(
            request.identity, request.installation_id
        )
        history = self._service.history(request.identity)
        record = SkillInstallationTerminationRecord(
            record_id=_termination_id(request),
            installation_id=request.installation_id,
            identity=request.identity,
            terminated_at=request.occurred_at,
            actor_ref=request.actor_ref,
            reason=request.reason,
            replacement_installation_id=request.replacement_installation_id,
            integrity_observation_ref=request.integrity_observation_ref,
        )
        existing = _record_by_id(history, record.record_id)
        if existing is not None:
            if existing != record:
                raise SkillInstallationConflict()
            return SkillInstallationTerminationResult(
                request.identity,
                record,
                SkillInstallationOutcome.IDEMPOTENT_REPLAY,
                _project_installations(self._service._published(request.identity), history),
            )
        projection = _project_installations(
            self._service._published(request.identity), history
        )
        if request.installation_id in projection.terminated_installation_ids:
            if request.installation_id in projection.corrupted_installation_ids:
                raise SkillInstallationCorrupted()
            raise SkillInstallationTerminated()
        lifecycle = self._lifecycle.projection(request.identity)
        if lifecycle.active_installation_id == request.installation_id:
            raise ActiveSkillInstallationTerminationForbidden()
        if request.occurred_at <= parent.installed_at:
            raise AmbiguousSkillInstallationOrdering()
        _validate_new_fact_time(history, request.occurred_at)
        if request.replacement_installation_id is not None:
            replacement = self._service.get_installation(
                request.identity, request.replacement_installation_id
            )
            if (
                replacement.record_id == parent.record_id
                or replacement not in projection.current_registrations
            ):
                raise SkillInstallationConflict()
        try:
            outcome = self._store.append_termination(record)
        except SkillStoreInvalidParentReference as exc:
            raise SkillInstallationNotFound() from exc
        except SkillStoreDivergentDuplicate as exc:
            raise SkillInstallationConflict() from exc
        except SkillStoreUnavailable as exc:
            raise SkillInstallationStoreUnavailable() from exc
        if outcome is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY:
            history = self._service.history(request.identity)
            persisted = _record_by_id(history, record.record_id)
            if persisted != record:
                raise SkillInstallationConflict()
        else:
            history = (*history, record)
        return SkillInstallationTerminationResult(
            identity=request.identity,
            record=record,
            outcome=SkillInstallationOutcome(outcome.value),
            projection=_project_installations(
                self._service._published(request.identity), history
            ),
        )


class SkillActivationService:
    """Coordinates operational selection over a current registration."""

    def __init__(
        self,
        installations: SkillInstallationService,
        parent_verifier: SkillInstallationParentVerifier,
        lifecycle: SkillLifecycleService,
    ) -> None:
        self._installations = installations
        self._parents = parent_verifier
        self._lifecycle = lifecycle

    def activate(
        self, request: ActivateInstalledSkillVersionRequest
    ) -> SkillActivationResult:
        parent = self._parents.validate_parent(
            request.identity, request.installation_id
        )
        if request.occurred_at <= parent.installed_at:
            raise InvalidOperationalActivationTransition()
        record = SkillActivationRecord(
            record_id=_activation_id(request),
            identity=request.identity,
            installation_id=request.installation_id,
            activated_at=request.occurred_at,
            actor_ref=request.actor_ref,
            reason=request.reason,
        )
        try:
            result = self._lifecycle.activate(record)
        except (
            InvalidSkillActivationParent,
            InvalidSkillLifecycleTransition,
            RevokedSkillVersion,
            SkillLifecycleConflict,
        ) as exc:
            raise InvalidOperationalActivationTransition() from exc
        if not isinstance(result.record, SkillActivationRecord):
            raise SkillInstallationConflict()
        return SkillActivationResult(
            identity=request.identity,
            record=result.record,
            outcome=result.outcome,
            projection=self.projection(request.identity),
        )

    def deactivate(
        self, request: DeactivateInstalledSkillVersionRequest
    ) -> SkillActivationResult:
        try:
            result = self._lifecycle.deactivate(
                DeactivateSkillVersionRequest(
                    identity=request.identity,
                    actor_ref=request.actor_ref,
                    reason=request.reason,
                    occurred_at=request.occurred_at,
                    event_ref=request.deactivation_ref,
                )
            )
        except (InvalidSkillLifecycleTransition, RevokedSkillVersion) as exc:
            raise InvalidOperationalActivationTransition() from exc
        if not isinstance(result.record, SkillLifecycleRecord):
            raise SkillInstallationConflict()
        return SkillActivationResult(
            identity=request.identity,
            record=result.record,
            outcome=result.outcome,
            projection=self.projection(request.identity),
        )

    def projection(
        self, identity: PublishedSkillVersionId
    ) -> SkillOperationalProjection:
        installation = self._installations.projection(identity)
        try:
            lifecycle = self._lifecycle.projection(identity)
        except InvalidSkillActivationParent as exc:
            raise InvalidOperationalActivationParent() from exc
        return SkillOperationalProjection(
            identity=identity,
            installation=installation,
            lifecycle=lifecycle,
            has_current_registration=installation.has_current_registration,
            activation_eligible=(
                installation.has_current_registration and lifecycle.activatable
            ),
            operationally_active=lifecycle.active,
        )


def _project_installations(
    publication: PublishedSkillVersionRecord,
    history: tuple[InstallationFact, ...],
) -> SkillInstallationProjection:
    ordered = _canonical_installation_history(publication, history)
    installations: dict[SkillStoreRecordId, SkillInstallationRecord] = {}
    terminations: dict[SkillStoreRecordId, SkillInstallationTerminationRecord] = {}
    for fact in ordered:
        if isinstance(fact, SkillInstallationRecord):
            if fact.record_id in installations:
                raise CorruptedSkillInstallationHistory()
            installations[fact.record_id] = fact
            continue
        parent = installations.get(fact.installation_id)
        if (
            parent is None
            or fact.installation_id in terminations
            or fact.terminated_at <= parent.installed_at
        ):
            raise CorruptedSkillInstallationHistory()
        if fact.replacement_installation_id is not None:
            replacement = installations.get(fact.replacement_installation_id)
            if (
                replacement is None
                or replacement.record_id == parent.record_id
                or replacement.installed_at > fact.terminated_at
            ):
                raise CorruptedSkillInstallationHistory()
        terminations[fact.installation_id] = fact
    current = tuple(
        record
        for record in installations.values()
        if record.record_id not in terminations
    )
    termination_records = tuple(terminations.values())
    return SkillInstallationProjection(
        identity=publication.identity,
        installations=tuple(installations.values()),
        current_registrations=current,
        terminations=termination_records,
        terminated_installation_ids=tuple(terminations),
        corrupted_installation_ids=tuple(
            installation_id
            for installation_id, termination in terminations.items()
            if termination.reason is SkillInstallationTerminationReason.CORRUPTED
        ),
        has_current_registration=bool(current),
        last_fact=ordered[-1] if ordered else None,
        complete=True,
    )


def _canonical_installation_history(
    publication: PublishedSkillVersionRecord,
    history: tuple[InstallationFact, ...],
) -> tuple[InstallationFact, ...]:
    by_id: dict[SkillStoreRecordId, InstallationFact] = {}
    for record in history:
        if (
            not isinstance(
                record,
                (SkillInstallationRecord, SkillInstallationTerminationRecord),
            )
            or record.identity != publication.identity
            or _installation_timestamp(record) < publication.recorded_at
        ):
            raise CorruptedSkillInstallationHistory()
        existing = by_id.get(record.record_id)
        if existing is not None and existing != record:
            raise CorruptedSkillInstallationHistory()
        by_id[record.record_id] = record
    ordered = tuple(
        sorted(
            by_id.values(),
            key=lambda record: (_installation_timestamp(record), str(record.record_id)),
        )
    )
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if _installation_timestamp(previous) == _installation_timestamp(current):
            raise AmbiguousSkillInstallationOrdering()
    return ordered


def _installation_timestamp(record: InstallationFact) -> datetime:
    if isinstance(record, SkillInstallationRecord):
        return record.installed_at
    return record.terminated_at


def _validate_new_fact_time(
    history: tuple[InstallationFact, ...],
    occurred_at: datetime,
) -> None:
    if not history:
        return
    maximum = max(_installation_timestamp(record) for record in history)
    if occurred_at < maximum:
        raise CorruptedSkillInstallationHistory()
    if occurred_at == maximum:
        raise AmbiguousSkillInstallationOrdering()


def _record_by_id(
    history: tuple[InstallationFact, ...],
    record_id: SkillStoreRecordId,
) -> InstallationFact | None:
    return next((record for record in history if record.record_id == record_id), None)


def _installation_semantics(record: SkillInstallationRecord) -> tuple[object, ...]:
    return (
        record.identity,
        record.content_fingerprint,
        record.content_ref,
        record.storage_profile_ref,
    )


def _installation_id(
    identity: PublishedSkillVersionId,
    content: InstalledSkillContentRef,
) -> SkillStoreRecordId:
    projection = (
        identity.to_canonical_text(),
        content.content_ref.to_canonical_text(),
        content.content_fingerprint.to_canonical_text(),
        content.storage_profile_ref.to_canonical_text(),
    )
    return _semantic_id("installation", projection)


def _termination_id(
    request: TerminateSkillInstallationRequest,
) -> SkillStoreRecordId:
    projection = (
        request.identity.to_canonical_text(),
        str(request.installation_id),
        request.reason.value,
        request.actor_ref.to_canonical_text(),
        request.event_ref.to_canonical_text(),
        request.occurred_at.isoformat(timespec="microseconds"),
        (
            str(request.replacement_installation_id)
            if request.replacement_installation_id is not None
            else ""
        ),
        (
            request.integrity_observation_ref.to_canonical_text()
            if request.integrity_observation_ref is not None
            else ""
        ),
    )
    return _semantic_id("installation-end", projection)


def _activation_id(
    request: ActivateInstalledSkillVersionRequest,
) -> SkillStoreRecordId:
    projection = (
        request.identity.to_canonical_text(),
        str(request.installation_id),
        request.actor_ref.to_canonical_text(),
        request.reason.value,
        request.occurred_at.isoformat(timespec="microseconds"),
    )
    return _semantic_id("activation", projection)


def _semantic_id(namespace: str, projection: tuple[object, ...]) -> SkillStoreRecordId:
    digest = hashlib.sha256(canonical_json_bytes(projection)).hexdigest()
    return SkillStoreRecordId(f"{namespace}:{digest}")


def _manifest_assets_correspond(snapshot: VerifiedSkillContentSnapshot) -> bool:
    declared = {item.logical_path: item for item in snapshot.manifest.content}
    verified = {item.logical_path: item for item in snapshot.assets}
    if len(declared) != len(snapshot.manifest.content) or set(declared) != set(verified):
        return False
    return all(
        declaration.fingerprint.value == verified[path].checksum.value
        and declaration.kind is verified[path].kind
        and declaration.media_type == verified[path].media_type
        and declaration.size_bytes == verified[path].size_bytes
        and declaration.role == verified[path].role
        for path, declaration in declared.items()
    )
