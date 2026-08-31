from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillId,
    SkillSemanticReference,
)
from synapse.skills.phase2_values import SkillContentFingerprint, SkillVersion
from synapse.skills.phase3_contracts import SkillCatalogStore, SkillStoreWriteOutcome
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase4_models import SkillAssetChecksum, content_fingerprint
from synapse.skills.phase4_verification import SkillPackageVerifier
from synapse.skills.phase5_errors import (
    InvalidSkillPublicationRequest,
    PublishedSkillVersionNotFound,
    SkillPublicationCatalogUnavailable,
    SkillPublicationConflict,
    SkillPublicationSnapshotMismatch,
)
from synapse.skills.phase5_models import (
    PublishVerifiedSkillVersionRequest,
    SkillPublicationOutcome,
)
from synapse.skills.phase5_publication import SkillPublicationService

NOW = datetime(2026, 7, 26, 18, 0, tzinfo=UTC)


class FakeCatalog:
    def __init__(self) -> None:
        self.records: dict[
            tuple[SkillId, SkillVersion], PublishedSkillVersionRecord
        ] = {}
        self.unavailable = False
        self.fail_after_save = False

    def save_version(
        self, record: PublishedSkillVersionRecord
    ) -> SkillStoreWriteOutcome:
        if self.unavailable:
            raise SkillStoreUnavailable()
        key = (record.identity.skill_id, record.identity.version)
        existing = self.records.get(key)
        if existing is None:
            self.records[key] = record
            if self.fail_after_save:
                self.fail_after_save = False
                raise SkillStoreUnavailable()
            return SkillStoreWriteOutcome.CREATED
        if existing.identity == record.identity and existing.manifest == record.manifest:
            return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
        raise SkillStoreDivergentDuplicate()

    def get_version(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        if self.unavailable:
            raise SkillStoreUnavailable()
        try:
            record = self.records[(identity.skill_id, identity.version)]
        except KeyError:
            raise SkillStoreNotFound() from None
        if record.identity != identity:
            raise SkillStoreNotFound()
        return record

    def list_versions(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        if self.unavailable:
            raise SkillStoreUnavailable()
        records = (
            record
            for record in self.records.values()
            if record.identity.skill_id == skill_id
        )
        return tuple(
            sorted(
                records,
                key=lambda record: (
                    record.identity.version.precedence_key(),
                    str(record.identity.version),
                    record.identity.to_canonical_text(),
                ),
            )
        )[: limit.limit]


def _manifest_bytes(content: bytes, version: str = "1.0.0") -> bytes:
    digest = hashlib.sha256(content).hexdigest()
    return f"""format_version: 1
skill_id: publication-skill
version: {version}
display_name: Publication skill
summary: Publication service test.
description: A verified snapshot used by the publication service tests.
provenance:
  publisher_ref: publisher:synapse
scopes:
  - project
content:
  - logical_path: SKILL.md
    fingerprint: {digest}
    kind: instructions
    media_type: text/markdown
    size_bytes: {len(content)}
""".encode()


def _snapshot(
    root: Path,
    version: str = "1.0.0",
    content: bytes = b"# Publication",
):
    root.mkdir(parents=True)
    (root / "SKILL.md").write_bytes(content)
    (root / "manifest.yaml").write_bytes(_manifest_bytes(content, version))
    return SkillPackageVerifier().verify(root)


def _request(
    root: Path,
    version: str = "1.0.0",
    content: bytes = b"# Publication",
) -> PublishVerifiedSkillVersionRequest:
    return PublishVerifiedSkillVersionRequest(
        snapshot=_snapshot(root, version, content),
        actor_ref=SkillSemanticReference("actor:publisher"),
        publication_ref=SkillSemanticReference("publication:request-1"),
        idempotency_ref=SkillSemanticReference("idempotency:request-1"),
        published_at=NOW,
    )


def test_fake_conforms_exactly_to_catalog_port() -> None:
    catalog: SkillCatalogStore = FakeCatalog()
    assert catalog is not None
    assert {
        name
        for name in dir(FakeCatalog)
        if not name.startswith("_")
    } == {"get_version", "list_versions", "save_version"}


def test_first_publication_derives_identity_and_creates_only_catalog_record(
    tmp_path: Path,
) -> None:
    catalog = FakeCatalog()
    request = _request(tmp_path / "package")
    result = SkillPublicationService(catalog).publish(request)
    expected = PublishedSkillVersionId.from_manifest(
        request.snapshot.manifest,
        request.snapshot.content_fingerprint,
    )
    assert result.outcome is SkillPublicationOutcome.CREATED
    assert result.identity == expected == result.record.identity
    assert result.record.manifest == request.snapshot.manifest
    assert result.record.recorded_at == NOW
    assert tuple(catalog.records) == ((expected.skill_id, expected.version),)
    assert not hasattr(result.record, "idempotency_ref")
    for forbidden in ("installed", "active", "trusted", "approved", "evaluation"):
        assert not hasattr(result.record, forbidden)


def test_equivalent_replay_returns_existing_record_without_new_fact(tmp_path: Path) -> None:
    catalog = FakeCatalog()
    request = _request(tmp_path / "package")
    service = SkillPublicationService(catalog)
    first = service.publish(request)
    replay = service.publish(request)
    assert replay.outcome is SkillPublicationOutcome.IDEMPOTENT_REPLAY
    assert replay.record is first.record
    assert len(catalog.records) == 1


@pytest.mark.parametrize(
    "change",
    (
        {"published_at": datetime(2026, 7, 26, 18, 1, tzinfo=UTC)},
        {"actor_ref": SkillSemanticReference("actor:other")},
        {"publication_ref": SkillSemanticReference("publication:other")},
        {"idempotency_ref": SkillSemanticReference("idempotency:other")},
    ),
)
def test_same_identity_with_new_request_observations_returns_initial_fact(
    tmp_path: Path, change: dict[str, object]
) -> None:
    catalog = FakeCatalog()
    request = _request(tmp_path / "package")
    service = SkillPublicationService(catalog)
    first = service.publish(request)
    replay = service.publish(replace(request, **change))  # type: ignore[arg-type]
    assert replay.outcome is SkillPublicationOutcome.IDEMPOTENT_REPLAY
    assert replay.record is first.record
    assert len(catalog.records) == 1


def test_same_skill_and_structural_version_with_new_content_conflicts(
    tmp_path: Path,
) -> None:
    catalog = FakeCatalog()
    service = SkillPublicationService(catalog)
    first = _request(tmp_path / "first", content=b"first")
    second = _request(tmp_path / "second", content=b"second")
    service.publish(first)
    with pytest.raises(SkillPublicationConflict):
        service.publish(second)
    assert len(catalog.records) == 1


def test_ambiguous_success_can_be_reconciled_by_retry_and_exact_lookup(
    tmp_path: Path,
) -> None:
    catalog = FakeCatalog()
    catalog.fail_after_save = True
    service = SkillPublicationService(catalog)
    request = _request(tmp_path / "package")
    with pytest.raises(SkillPublicationCatalogUnavailable):
        service.publish(request)
    replay = service.publish(
        replace(
            request,
            published_at=datetime(2026, 7, 26, 19, 0, tzinfo=UTC),
        )
    )
    assert replay.outcome is SkillPublicationOutcome.IDEMPOTENT_REPLAY
    assert replay.record.recorded_at == NOW
    assert service.get_exact(replay.identity) is replay.record


def test_request_and_result_are_frozen_and_timestamp_is_caller_supplied(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path / "package")
    result = SkillPublicationService(FakeCatalog()).publish(request)
    with pytest.raises(FrozenInstanceError):
        request.published_at = datetime.now(UTC)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.outcome = SkillPublicationOutcome.CREATED  # type: ignore[misc]
    assert result.record.recorded_at is NOW


@pytest.mark.parametrize(
    "field",
    ("actor_ref", "publication_ref", "idempotency_ref"),
)
def test_invalid_publication_references_fail_safely(
    tmp_path: Path, field: str
) -> None:
    request = _request(tmp_path / "package")
    with pytest.raises(InvalidSkillPublicationRequest) as captured:
        replace(request, **{field: "unsafe-local-path"})  # type: ignore[arg-type]
    assert "unsafe-local-path" not in str(captured.value)


def test_snapshot_identity_mismatch_fails_before_store(tmp_path: Path) -> None:
    catalog = FakeCatalog()
    request = _request(tmp_path / "package")
    object.__setattr__(
        request.snapshot,
        "content_fingerprint",
        SkillContentFingerprint("0" * 64),
    )
    with pytest.raises(SkillPublicationSnapshotMismatch):
        SkillPublicationService(catalog).publish(request)
    assert catalog.records == {}


@pytest.mark.parametrize(
    "manifest_change",
    (
        {"skill_id": SkillId("different-skill")},
        {"version": SkillVersion.parse("9.0.0")},
    ),
)
def test_manifest_skill_or_version_corruption_fails_before_store(
    tmp_path: Path, manifest_change: dict[str, object]
) -> None:
    catalog = FakeCatalog()
    request = _request(tmp_path / "package")
    object.__setattr__(
        request.snapshot,
        "manifest",
        replace(request.snapshot.manifest, **manifest_change),  # type: ignore[arg-type]
    )
    with pytest.raises(SkillPublicationSnapshotMismatch):
        SkillPublicationService(catalog).publish(request)
    assert catalog.records == {}


def test_manifest_asset_correspondence_mismatch_fails_before_store(
    tmp_path: Path,
) -> None:
    catalog = FakeCatalog()
    request = _request(tmp_path / "package")
    corrupted_assets = (
        replace(
            request.snapshot.assets[0],
            checksum=SkillAssetChecksum("0" * 64),
        ),
    )
    object.__setattr__(request.snapshot, "assets", corrupted_assets)
    object.__setattr__(
        request.snapshot,
        "content_fingerprint",
        content_fingerprint(corrupted_assets),
    )
    with pytest.raises(SkillPublicationSnapshotMismatch):
        SkillPublicationService(catalog).publish(request)
    assert catalog.records == {}


def test_catalog_unavailable_is_translated_without_leaking_store_details(
    tmp_path: Path,
) -> None:
    catalog = FakeCatalog()
    catalog.unavailable = True
    with pytest.raises(SkillPublicationCatalogUnavailable) as captured:
        SkillPublicationService(catalog).publish(_request(tmp_path / "package"))
    assert str(captured.value) == "skill publication catalog is unavailable"


def test_exact_lookup_and_not_found_are_application_typed(tmp_path: Path) -> None:
    catalog = FakeCatalog()
    service = SkillPublicationService(catalog)
    published = service.publish(_request(tmp_path / "package"))
    assert service.get_exact(published.identity) == published.record
    missing = replace(
        published.identity,
        content_fingerprint=SkillContentFingerprint("f" * 64),
    )
    with pytest.raises(PublishedSkillVersionNotFound):
        service.get_exact(missing)


def test_version_listing_is_bounded_ascending_and_deterministic(tmp_path: Path) -> None:
    catalog = FakeCatalog()
    service = SkillPublicationService(catalog)
    versions = ("2.0.0", "1.0.0", "1.0.0-rc.1", "1.0.0+build.2", "1.0.0+build.1")
    for index, version in enumerate(versions):
        request = _request(tmp_path / str(index), version)
        request = replace(
            request,
            publication_ref=SkillSemanticReference(f"publication:request-{index}"),
            idempotency_ref=SkillSemanticReference(f"idempotency:request-{index}"),
        )
        service.publish(request)
    skill_id = SkillId("publication-skill")
    first = service.list_versions(skill_id, SkillStoreQueryLimit(4))
    second = service.list_versions(skill_id, SkillStoreQueryLimit(4))
    assert tuple(str(record.identity.version) for record in first) == (
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.0+build.1",
        "1.0.0+build.2",
    )
    assert first == second


def test_catalog_membership_requires_a_published_record(tmp_path: Path) -> None:
    catalog = FakeCatalog()
    request = _request(tmp_path / "package")
    service = SkillPublicationService(catalog)
    identity = PublishedSkillVersionId.from_manifest(
        request.snapshot.manifest,
        request.snapshot.content_fingerprint,
    )
    with pytest.raises(PublishedSkillVersionNotFound):
        service.get_exact(identity)
    service.publish(request)
    assert service.get_exact(identity).identity == identity


def test_service_has_no_implicit_progression_surface() -> None:
    forbidden = {
        "install",
        "activate",
        "revoke",
        "evaluate",
        "approve",
        "resolve",
        "execute",
        "publish_event",
    }
    assert forbidden.isdisjoint(dir(SkillPublicationService))


def test_phase5_public_surface_is_narrow() -> None:
    import synapse.skills as skills

    assert {
        "PublishVerifiedSkillVersionRequest",
        "SkillPublicationResult",
        "SkillPublicationOutcome",
        "SkillPublicationService",
        "SkillPublicationError",
    }.issubset(skills.__all__)
    assert {
        "_version_order",
        "FakeCatalog",
        "InMemorySkillCatalogStore",
    }.isdisjoint(skills.__all__)
