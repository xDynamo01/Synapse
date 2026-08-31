from __future__ import annotations

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId
from synapse.skills.phase3_contracts import SkillCatalogStore, SkillStoreWriteOutcome
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase4_models import (
    SkillVerificationMetadata,
    SkillVerificationPolicyVersion,
    VerifiedSkillContentSnapshot,
    content_fingerprint,
)
from synapse.skills.phase5_errors import (
    PublishedSkillVersionNotFound,
    SkillPublicationCatalogUnavailable,
    SkillPublicationConflict,
    SkillPublicationSnapshotMismatch,
)
from synapse.skills.phase5_models import (
    PublishVerifiedSkillVersionRequest,
    SkillPublicationOutcome,
    SkillPublicationResult,
)


class SkillPublicationService:
    """Publishes verified immutable versions and exposes exact catalog queries."""

    def __init__(self, catalog: SkillCatalogStore) -> None:
        self._catalog = catalog

    def publish(
        self, request: PublishVerifiedSkillVersionRequest
    ) -> SkillPublicationResult:
        snapshot = request.snapshot
        identity = self._identity_from_snapshot(snapshot)
        record = PublishedSkillVersionRecord(
            identity=identity,
            manifest=snapshot.manifest,
            recorded_at=request.published_at,
            actor_ref=request.actor_ref,
            publication_ref=request.publication_ref,
        )
        try:
            outcome = self._catalog.save_version(record)
            persisted = (
                record
                if outcome is SkillStoreWriteOutcome.CREATED
                else self._catalog.get_version(identity)
            )
        except SkillStoreDivergentDuplicate as exc:
            raise SkillPublicationConflict() from exc
        except SkillStoreUnavailable as exc:
            raise SkillPublicationCatalogUnavailable() from exc
        if (
            persisted.identity != identity
            or persisted.manifest != snapshot.manifest
        ):
            raise SkillPublicationConflict()
        return SkillPublicationResult(
            record=persisted,
            identity=identity,
            outcome=SkillPublicationOutcome(outcome.value),
        )

    def get_exact(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        if not isinstance(identity, PublishedSkillVersionId):
            raise PublishedSkillVersionNotFound()
        try:
            record = self._catalog.get_version(identity)
        except SkillStoreNotFound as exc:
            raise PublishedSkillVersionNotFound() from exc
        except SkillStoreUnavailable as exc:
            raise SkillPublicationCatalogUnavailable() from exc
        if record.identity != identity:
            raise SkillPublicationConflict()
        return record

    def list_versions(
        self,
        skill_id: SkillId,
        limit: SkillStoreQueryLimit,
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        if not isinstance(skill_id, SkillId) or not isinstance(limit, SkillStoreQueryLimit):
            raise PublishedSkillVersionNotFound()
        try:
            records = self._catalog.list_versions(skill_id, limit)
        except SkillStoreUnavailable as exc:
            raise SkillPublicationCatalogUnavailable() from exc
        if (
            not isinstance(records, tuple)
            or len(records) > limit.limit
            or any(
                not isinstance(record, PublishedSkillVersionRecord)
                or record.identity.skill_id != skill_id
                for record in records
            )
        ):
            raise SkillPublicationConflict()
        return tuple(sorted(records, key=_version_order))

    @staticmethod
    def _identity_from_snapshot(
        snapshot: VerifiedSkillContentSnapshot,
    ) -> PublishedSkillVersionId:
        if not isinstance(snapshot, VerifiedSkillContentSnapshot):
            raise SkillPublicationSnapshotMismatch()
        try:
            snapshot.policy_version.__post_init__()
            snapshot.verification.__post_init__()
        except (AttributeError, ValueError):
            raise SkillPublicationSnapshotMismatch() from None
        if (
            not isinstance(snapshot.policy_version, SkillVerificationPolicyVersion)
            or not isinstance(snapshot.verification, SkillVerificationMetadata)
            or snapshot.manifest.fingerprint() != snapshot.manifest_fingerprint
            or snapshot.technical_identity
            != (snapshot.manifest_fingerprint, snapshot.content_fingerprint)
            or content_fingerprint(snapshot.assets) != snapshot.content_fingerprint
            or not _manifest_assets_correspond(snapshot)
        ):
            raise SkillPublicationSnapshotMismatch()
        identity = PublishedSkillVersionId.from_manifest(
            snapshot.manifest,
            snapshot.content_fingerprint,
        )
        if (
            identity.skill_id != snapshot.manifest.skill_id
            or identity.version != snapshot.manifest.version
            or identity.manifest_fingerprint != snapshot.manifest_fingerprint
            or identity.content_fingerprint != snapshot.content_fingerprint
        ):
            raise SkillPublicationSnapshotMismatch()
        return identity


def _version_order(
    record: PublishedSkillVersionRecord,
) -> tuple[object, str, str]:
    return (
        record.identity.version.precedence_key(),
        str(record.identity.version),
        record.identity.to_canonical_text(),
    )


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
