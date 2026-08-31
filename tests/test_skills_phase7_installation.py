from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillSemanticReference,
)
from synapse.skills.phase3_contracts import (
    SkillInstallationHistory,
    SkillLifecycleHistory,
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
    SkillLifecycleReason,
    SkillLifecycleRecord,
    SkillRevocationRecord,
)
from synapse.skills.phase3_values import SkillStoreRecordId
from synapse.skills.phase4_verification import SkillPackageVerifier
from synapse.skills.phase6_errors import (
    CorruptedSkillLifecycleHistory,
    IncompleteSkillLifecycleHistory,
    SkillLifecycleStoreUnavailable,
)
from synapse.skills.phase6_lifecycle import SkillLifecycleService
from synapse.skills.phase6_models import (
    DeprecateSkillVersionRequest,
    RevokeSkillVersionRequest,
    SkillLifecycleOutcome,
    SupersedeSkillVersionRequest,
)
from synapse.skills.phase7_errors import (
    ActiveSkillInstallationTerminationForbidden,
    AmbiguousSkillInstallationOrdering,
    IncompleteSkillInstallationHistory,
    InvalidOperationalActivationParent,
    InvalidOperationalActivationTransition,
    InvalidSkillInstallationRequest,
    SkillInstallationConflict,
    SkillInstallationCorrupted,
    SkillInstallationNotFound,
    SkillInstallationSnapshotMismatch,
    SkillInstallationStoreUnavailable,
    SkillInstallationTerminated,
    SkillInstallationVersionNotPublished,
)
from synapse.skills.phase7_installation import (
    SkillActivationService,
    SkillInstallationParentVerifier,
    SkillInstallationService,
    SkillInstallationTerminationService,
)
from synapse.skills.phase7_models import (
    ActivateInstalledSkillVersionRequest,
    DeactivateInstalledSkillVersionRequest,
    InstalledSkillContentRef,
    InstallVerifiedSkillVersionRequest,
    SkillInstallationOutcome,
    TerminateSkillInstallationRequest,
)

NOW = datetime(2026, 7, 27, 14, 0, tzinfo=UTC)
ACTOR = SkillSemanticReference("actor:installer")
REASON = SkillLifecycleReason.OPERATOR


def _manifest_bytes(content: bytes, version: str = "1.0.0") -> bytes:
    digest = hashlib.sha256(content).hexdigest()
    return f"""format_version: 1
skill_id: installation-skill
version: {version}
display_name: Installation skill
summary: Installation authority test.
description: A verified snapshot used by installation service tests.
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
    content: bytes = b"# Installation",
):
    root.mkdir(parents=True)
    (root / "SKILL.md").write_bytes(content)
    (root / "manifest.yaml").write_bytes(_manifest_bytes(content, version))
    return SkillPackageVerifier().verify(root)


def _published(snapshot) -> PublishedSkillVersionRecord:
    identity = PublishedSkillVersionId.from_manifest(
        snapshot.manifest, snapshot.content_fingerprint
    )
    return PublishedSkillVersionRecord(
        identity=identity,
        manifest=snapshot.manifest,
        recorded_at=NOW,
        actor_ref=ACTOR,
        publication_ref=SkillSemanticReference("publication:installation-test"),
    )


def _timestamp(record):
    for name in ("installed_at", "terminated_at", "activated_at", "occurred_at", "revoked_at"):
        if hasattr(record, name):
            return getattr(record, name)
    raise AssertionError("unknown record")


def _append(records, record):
    existing = records.get(record.record_id)
    if existing is None:
        records[record.record_id] = record
        return SkillStoreWriteOutcome.CREATED
    if existing == record:
        return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    raise SkillStoreDivergentDuplicate()


class FakeCatalog:
    def __init__(self, *records: PublishedSkillVersionRecord) -> None:
        self.records = {record.identity: record for record in records}
        self.unavailable = False

    def save_version(self, record):
        raise AssertionError("installation never publishes")

    def get_version(self, identity):
        if self.unavailable:
            raise SkillStoreUnavailable()
        try:
            return self.records[identity]
        except KeyError:
            raise SkillStoreNotFound() from None

    def list_versions(self, skill_id, limit):
        raise AssertionError("installation never selects versions")


class FakeInstallationStore:
    def __init__(self) -> None:
        self.installations: dict[SkillStoreRecordId, SkillInstallationRecord] = {}
        self.terminations: dict[
            SkillStoreRecordId, SkillInstallationTerminationRecord
        ] = {}
        self.complete = True
        self.unavailable = False
        self.reverse_history = False
        self.fail_after_install = False
        self.fail_after_termination = False

    def append_installation(self, record):
        if self.unavailable:
            raise SkillStoreUnavailable()
        outcome = _append(self.installations, record)
        if outcome is SkillStoreWriteOutcome.CREATED and self.fail_after_install:
            self.fail_after_install = False
            raise SkillStoreUnavailable()
        return outcome

    def append_termination(self, record):
        if self.unavailable:
            raise SkillStoreUnavailable()
        parent = self.installations.get(record.installation_id)
        if parent is None or parent.identity != record.identity:
            raise SkillStoreInvalidParentReference()
        outcome = _append(self.terminations, record)
        if outcome is SkillStoreWriteOutcome.CREATED and self.fail_after_termination:
            self.fail_after_termination = False
            raise SkillStoreUnavailable()
        return outcome

    def history(self, identity, limit):
        if self.unavailable:
            raise SkillStoreUnavailable()
        records = [
            record
            for record in (*self.installations.values(), *self.terminations.values())
            if record.identity == identity
        ]
        records.sort(
            key=lambda record: (_timestamp(record), str(record.record_id)),
            reverse=self.reverse_history,
        )
        return SkillInstallationHistory(
            records=tuple(records[: limit.limit]),
            complete=self.complete,
        )


class FakeLifecycleStore:
    def __init__(self) -> None:
        self.records: dict[
            SkillStoreRecordId,
            SkillLifecycleRecord | SkillActivationRecord | SkillRevocationRecord,
        ] = {}
        self.complete = True
        self.fail_after_activation = False

    def append_lifecycle(self, record):
        return _append(self.records, record)

    def append_activation(self, record):
        outcome = _append(self.records, record)
        if outcome is SkillStoreWriteOutcome.CREATED and self.fail_after_activation:
            self.fail_after_activation = False
            raise SkillStoreUnavailable()
        return outcome

    def append_revocation(self, record):
        return _append(self.records, record)

    def history(self, identity, limit):
        records = sorted(
            (
                record
                for record in self.records.values()
                if record.identity == identity
            ),
            key=lambda record: (_timestamp(record), str(record.record_id)),
        )
        return SkillLifecycleHistory(tuple(records[: limit.limit]), self.complete)


def _content(snapshot, suffix: str = "main") -> InstalledSkillContentRef:
    return InstalledSkillContentRef(
        content_ref=SkillSemanticReference(f"content:{suffix}"),
        content_fingerprint=snapshot.content_fingerprint,
        storage_profile_ref=SkillSemanticReference("storage-profile:local"),
    )


def _install_request(
    publication,
    snapshot,
    *,
    suffix: str = "main",
    minute: int = 1,
):
    return InstallVerifiedSkillVersionRequest(
        identity=publication.identity,
        snapshot=snapshot,
        local_content=_content(snapshot, suffix),
        actor_ref=ACTOR,
        registration_ref=SkillSemanticReference(f"registration:{suffix}"),
        idempotency_ref=SkillSemanticReference(f"idempotency:{suffix}"),
        installed_at=NOW + timedelta(minutes=minute),
    )


def _harness(publication):
    catalog = FakeCatalog(publication)
    installation_store = FakeInstallationStore()
    installations = SkillInstallationService(catalog, installation_store)
    parents = SkillInstallationParentVerifier(installations)
    lifecycle_store = FakeLifecycleStore()
    lifecycle = SkillLifecycleService(catalog, lifecycle_store, parents)
    termination = SkillInstallationTerminationService(
        installations, installation_store, lifecycle
    )
    activation = SkillActivationService(installations, parents, lifecycle)
    return (
        installations,
        termination,
        activation,
        lifecycle,
        installation_store,
        lifecycle_store,
        catalog,
    )


def _activate_request(identity, installation_id, minute: int = 2, suffix: str = "main"):
    return ActivateInstalledSkillVersionRequest(
        identity=identity,
        installation_id=installation_id,
        actor_ref=ACTOR,
        reason=REASON,
        idempotency_ref=SkillSemanticReference(f"idempotency:activation-{suffix}"),
        occurred_at=NOW + timedelta(minutes=minute),
    )


def _deactivate_request(identity, minute: int = 3, suffix: str = "main"):
    return DeactivateInstalledSkillVersionRequest(
        identity=identity,
        actor_ref=ACTOR,
        reason=REASON,
        deactivation_ref=SkillSemanticReference(f"deactivation-ref:{suffix}"),
        idempotency_ref=SkillSemanticReference(f"idempotency:deactivation-{suffix}"),
        occurred_at=NOW + timedelta(minutes=minute),
    )


def _terminate_request(
    identity,
    installation_id,
    reason,
    *,
    minute: int = 4,
    replacement=None,
):
    return TerminateSkillInstallationRequest(
        identity=identity,
        installation_id=installation_id,
        reason=reason,
        actor_ref=ACTOR,
        event_ref=SkillSemanticReference(f"termination:{reason.value}"),
        idempotency_ref=SkillSemanticReference(f"idempotency:{reason.value}"),
        occurred_at=NOW + timedelta(minutes=minute),
        replacement_installation_id=replacement,
        integrity_observation_ref=(
            SkillSemanticReference(f"integrity-observation:{reason.value}")
            if reason is SkillInstallationTerminationReason.CORRUPTED
            else None
        ),
    )


def test_valid_install_registers_reference_without_activation_or_copy(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, _, store, lifecycle_store, _ = _harness(publication)
    result = installations.install(_install_request(publication, snapshot))
    assert result.outcome is SkillInstallationOutcome.CREATED
    assert result.projection.has_current_registration
    assert result.record.content_fingerprint == publication.identity.content_fingerprint
    assert len(store.installations) == 1
    assert lifecycle_store.records == {}
    assert not activation.projection(publication.identity).operationally_active
    assert not hasattr(result.projection, "locally_available")
    for forbidden in ("path", "payload", "trust", "approval", "active"):
        assert not hasattr(result.record, forbidden)


def test_publication_and_snapshot_correspondence_are_exact(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    missing_service = SkillInstallationService(FakeCatalog(), FakeInstallationStore())
    with pytest.raises(SkillInstallationVersionNotPublished):
        missing_service.install(_install_request(publication, snapshot))

    installations, *_ = _harness(publication)
    bad_content = replace(
        _content(snapshot),
        content_fingerprint=SkillContentFingerprint("f" * 64),
    )
    with pytest.raises(SkillInstallationSnapshotMismatch):
        installations.install(
            replace(_install_request(publication, snapshot), local_content=bad_content)
        )


def test_local_reference_namespaces_are_closed_and_non_locator_based(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    with pytest.raises(InvalidSkillInstallationRequest):
        InstalledSkillContentRef(
            content_ref=SkillSemanticReference("locator:opaque"),
            content_fingerprint=snapshot.content_fingerprint,
            storage_profile_ref=SkillSemanticReference("storage-profile:local"),
        )
    with pytest.raises(InvalidSkillInstallationRequest):
        InstalledSkillContentRef(
            content_ref=SkillSemanticReference("content:main"),
            content_fingerprint=snapshot.content_fingerprint,
            storage_profile_ref=SkillSemanticReference("storage:local"),
        )
    publication = _published(snapshot)
    with pytest.raises(InvalidSkillInstallationRequest):
        replace(
            _install_request(publication, snapshot),
            registration_ref=SkillSemanticReference("request:opaque"),
        )


def test_structurally_divergent_exact_identity_is_not_partial_fallback(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    divergent = replace(
        publication.identity,
        content_fingerprint=SkillContentFingerprint("f" * 64),
    )
    installations, *_ = _harness(publication)
    with pytest.raises(SkillInstallationVersionNotPublished):
        installations.projection(divergent)


def test_install_replay_ignores_request_scoped_observations(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, _, _, store, _, _ = _harness(publication)
    request = _install_request(publication, snapshot)
    first = installations.install(request)
    replay = installations.install(
        replace(
            request,
            actor_ref=SkillSemanticReference("actor:retry"),
            registration_ref=SkillSemanticReference("registration:retry"),
            idempotency_ref=SkillSemanticReference("idempotency:retry"),
            installed_at=NOW + timedelta(minutes=10),
        )
    )
    assert replay.outcome is SkillInstallationOutcome.IDEMPOTENT_REPLAY
    assert replay.record is first.record
    assert replay.record.registration_ref == request.registration_ref
    assert len(store.installations) == 1


def test_divergent_installation_duplicate_conflicts(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, _, _, store, _, _ = _harness(publication)
    request = _install_request(publication, snapshot)
    result = installations.install(request)
    store.installations[result.record.record_id] = replace(
        result.record,
        content_ref=SkillSemanticReference("content:divergent"),
    )
    with pytest.raises(SkillInstallationConflict):
        installations.install(request)


def test_multiple_installations_require_distinct_semantic_local_reference(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, *_ = _harness(publication)
    first = installations.install(_install_request(publication, snapshot))
    second = installations.install(
        _install_request(publication, snapshot, suffix="replica", minute=2)
    )
    assert first.record.record_id != second.record.record_id
    assert len(second.projection.current_registrations) == 2
    assert not hasattr(second.projection, "preferred_installation")


def test_storage_profile_is_a_factual_installation_identity_component(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, *_ = _harness(publication)
    request = _install_request(publication, snapshot)
    first = installations.install(request)
    second = installations.install(
        replace(
            request,
            local_content=replace(
                request.local_content,
                storage_profile_ref=SkillSemanticReference(
                    "storage-profile:secondary"
                ),
            ),
            registration_ref=SkillSemanticReference("registration:secondary"),
            installed_at=NOW + timedelta(minutes=2),
        )
    )
    assert first.record.record_id != second.record.record_id
    assert len(second.projection.current_registrations) == 2


def test_semantic_registration_cannot_be_recreated_after_termination(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, termination, *_ = _harness(publication)
    request = _install_request(publication, snapshot)
    first = installations.install(request)
    termination.terminate(
        _terminate_request(
            publication.identity,
            first.record.record_id,
            SkillInstallationTerminationReason.DETACHED,
        )
    )
    replay = installations.install(
        replace(
            request,
            registration_ref=SkillSemanticReference("registration:new-attempt"),
            idempotency_ref=SkillSemanticReference("idempotency:new-attempt"),
            installed_at=NOW + timedelta(minutes=5),
        )
    )
    assert replay.outcome is SkillInstallationOutcome.IDEMPOTENT_REPLAY
    assert replay.record is first.record
    assert not replay.projection.has_current_registration
    assert len(replay.projection.installations) == 1


def test_history_completeness_ordering_and_backdated_policy(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, _, _, store, _, _ = _harness(publication)
    installations.install(_install_request(publication, snapshot, minute=2))
    store.complete = False
    with pytest.raises(IncompleteSkillInstallationHistory):
        installations.history(publication.identity)
    store.complete = True
    with pytest.raises(SkillInstallationSnapshotMismatch):
        installations.install(_install_request(publication, snapshot, suffix="old", minute=-1))
    with pytest.raises(AmbiguousSkillInstallationOrdering):
        installations.install(_install_request(publication, snapshot, suffix="equal", minute=2))
    store.reverse_history = True
    assert len(installations.history(publication.identity)) == 1


@pytest.mark.parametrize(
    "reason",
    (
        SkillInstallationTerminationReason.DETACHED,
        SkillInstallationTerminationReason.UNINSTALLED,
        SkillInstallationTerminationReason.CORRUPTED,
    ),
)
def test_termination_reasons_preserve_original_history(
    tmp_path: Path,
    reason: SkillInstallationTerminationReason,
) -> None:
    snapshot = _snapshot(tmp_path / reason.value)
    publication = _published(snapshot)
    installations, termination, _, _, store, _, _ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    result = termination.terminate(
        _terminate_request(publication.identity, installed.record.record_id, reason)
    )
    assert len(result.projection.installations) == 1
    assert len(result.projection.terminations) == 1
    assert not result.projection.has_current_registration
    assert installed.record.record_id in store.installations


def test_corruption_requires_typed_external_integrity_observation(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, termination, *_ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    request = _terminate_request(
        publication.identity,
        installed.record.record_id,
        SkillInstallationTerminationReason.CORRUPTED,
    )
    with pytest.raises(InvalidSkillInstallationRequest):
        replace(request, integrity_observation_ref=None)
    result = termination.terminate(request)
    assert (
        result.record.integrity_observation_ref
        == request.integrity_observation_ref
    )
    assert not hasattr(termination, "detect_corruption")
    assert not hasattr(termination, "restore")


def test_replacement_termination_requires_usable_exact_replacement(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, termination, *_ = _harness(publication)
    first = installations.install(_install_request(publication, snapshot))
    second = installations.install(
        _install_request(publication, snapshot, suffix="replacement", minute=2)
    )
    result = termination.terminate(
        _terminate_request(
            publication.identity,
            first.record.record_id,
            SkillInstallationTerminationReason.REPLACED,
            minute=3,
            replacement=second.record.record_id,
        )
    )
    assert result.projection.current_registrations == (second.record,)


def test_valid_operational_activation_and_deactivation_are_append_only(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, _, store, lifecycle_store, _ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    activated = activation.activate(
        _activate_request(publication.identity, installed.record.record_id)
    )
    assert activated.projection.operationally_active
    assert activated.projection.lifecycle.active_installation_id == installed.record.record_id
    deactivated = activation.deactivate(_deactivate_request(publication.identity))
    assert not deactivated.projection.operationally_active
    assert deactivated.projection.installation.has_current_registration
    assert len(store.installations) == 1
    assert len(lifecycle_store.records) == 2


def test_activation_replay_conflict_and_lost_response(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, _, _, lifecycle_store, _ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    request = _activate_request(publication.identity, installed.record.record_id)
    lifecycle_store.fail_after_activation = True
    with pytest.raises(SkillLifecycleStoreUnavailable):
        activation.activate(request)
    replay = activation.activate(
        replace(
            request,
            idempotency_ref=SkillSemanticReference("idempotency:new-request"),
        )
    )
    assert replay.outcome is SkillLifecycleOutcome.IDEMPOTENT_REPLAY
    with pytest.raises(InvalidOperationalActivationTransition):
        activation.activate(
            replace(
                request,
                actor_ref=SkillSemanticReference("actor:different"),
                occurred_at=NOW + timedelta(minutes=3),
            )
        )


def test_activation_divergent_duplicate_is_translated_safely(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, _, _, lifecycle_store, _ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    request = _activate_request(publication.identity, installed.record.record_id)
    created = activation.activate(request).record
    assert isinstance(created, SkillActivationRecord)
    lifecycle_store.records[created.record_id] = replace(
        created, reason=SkillLifecycleReason.SECURITY
    )
    with pytest.raises(InvalidOperationalActivationTransition):
        activation.activate(request)


def test_install_lost_response_reconciles_from_complete_history(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, _, _, store, _, _ = _harness(publication)
    store.fail_after_install = True
    request = _install_request(publication, snapshot)
    with pytest.raises(SkillInstallationStoreUnavailable):
        installations.install(request)
    assert installations.install(request).outcome is SkillInstallationOutcome.IDEMPOTENT_REPLAY


def test_activation_rejects_missing_wrong_terminated_and_corrupted_parent(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, termination, activation, _, _, _, catalog = _harness(publication)
    missing = SkillStoreRecordId("installation:missing")
    with pytest.raises(SkillInstallationNotFound):
        activation.activate(_activate_request(publication.identity, missing))

    installed = installations.install(_install_request(publication, snapshot))
    wrong_snapshot = _snapshot(tmp_path / "wrong-version", version="2.0.0")
    wrong_publication = _published(wrong_snapshot)
    catalog.records[wrong_publication.identity] = wrong_publication
    with pytest.raises(SkillInstallationNotFound):
        activation.activate(
            _activate_request(
                wrong_publication.identity, installed.record.record_id
            )
        )

    termination.terminate(
        _terminate_request(
            publication.identity,
            installed.record.record_id,
            SkillInstallationTerminationReason.DETACHED,
        )
    )
    with pytest.raises(SkillInstallationTerminated):
        activation.activate(
            _activate_request(publication.identity, installed.record.record_id, minute=5)
        )

    installations, termination, activation, *_ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    termination.terminate(
        _terminate_request(
            publication.identity,
            installed.record.record_id,
            SkillInstallationTerminationReason.CORRUPTED,
        )
    )
    with pytest.raises(SkillInstallationCorrupted):
        activation.activate(
            _activate_request(publication.identity, installed.record.record_id, minute=5)
        )


def test_activation_rejects_incomplete_installation_history(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, _, store, _, _ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    store.complete = False
    with pytest.raises(IncompleteSkillInstallationHistory):
        activation.activate(
            _activate_request(publication.identity, installed.record.record_id)
        )


def test_activation_rejects_incomplete_lifecycle_and_noncausal_timestamp(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, _, _, lifecycle_store, _ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot, minute=2))
    with pytest.raises(InvalidOperationalActivationTransition):
        activation.activate(
            _activate_request(
                publication.identity,
                installed.record.record_id,
                minute=2,
                suffix="same-time",
            )
        )
    lifecycle_store.complete = False
    with pytest.raises(IncompleteSkillLifecycleHistory):
        activation.activate(
            _activate_request(
                publication.identity,
                installed.record.record_id,
                minute=3,
                suffix="incomplete-lifecycle",
            )
        )


@pytest.mark.parametrize("lifecycle_state", ("deprecated", "superseded", "revoked"))
def test_activation_rejects_lifecycle_ineligible_versions(
    tmp_path: Path,
    lifecycle_state: str,
) -> None:
    snapshot = _snapshot(tmp_path / lifecycle_state)
    publication = _published(snapshot)
    installations, _, activation, lifecycle, _, _, catalog = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    if lifecycle_state == "deprecated":
        lifecycle.deprecate(
            DeprecateSkillVersionRequest(
                identity=publication.identity,
                actor_ref=ACTOR,
                reason=REASON,
                occurred_at=NOW + timedelta(minutes=2),
                event_ref=SkillSemanticReference("event:deprecated"),
            )
        )
    elif lifecycle_state == "revoked":
        lifecycle.revoke(
            RevokeSkillVersionRequest(
                identity=publication.identity,
                actor_ref=ACTOR,
                reason=REASON,
                occurred_at=NOW + timedelta(minutes=2),
                event_ref=SkillSemanticReference("event:revoked"),
                decision_ref=SkillSemanticReference("governance:revoked"),
            )
        )
    else:
        target_snapshot = _snapshot(tmp_path / "target", version="2.0.0")
        target = _published(target_snapshot)
        catalog.records[target.identity] = target
        lifecycle.supersede(
            SupersedeSkillVersionRequest(
                identity=publication.identity,
                actor_ref=ACTOR,
                reason=REASON,
                occurred_at=NOW + timedelta(minutes=2),
                event_ref=SkillSemanticReference("event:superseded"),
                replacement=target.identity,
            )
        )
    with pytest.raises(InvalidOperationalActivationTransition):
        activation.activate(
            _activate_request(publication.identity, installed.record.record_id, minute=3)
        )


def test_active_parent_termination_requires_explicit_deactivation(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, termination, activation, *_ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    activation.activate(_activate_request(publication.identity, installed.record.record_id))
    request = _terminate_request(
        publication.identity,
        installed.record.record_id,
        SkillInstallationTerminationReason.UNINSTALLED,
        minute=3,
    )
    with pytest.raises(ActiveSkillInstallationTerminationForbidden):
        termination.terminate(request)
    activation.deactivate(_deactivate_request(publication.identity, minute=3))
    result = termination.terminate(replace(request, occurred_at=NOW + timedelta(minutes=4)))
    assert not result.projection.has_current_registration


def test_revocation_preserves_local_installation_but_makes_it_unusable(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, lifecycle, store, *_ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    lifecycle.revoke(
        RevokeSkillVersionRequest(
            identity=publication.identity,
            actor_ref=ACTOR,
            reason=REASON,
            occurred_at=NOW + timedelta(minutes=2),
            event_ref=SkillSemanticReference("event:revoke-installed"),
            decision_ref=SkillSemanticReference("governance:revoke-installed"),
        )
    )
    projection = activation.projection(publication.identity)
    assert projection.has_current_registration
    assert not projection.activation_eligible
    assert installed.record.record_id in store.installations


def test_late_activation_after_revocation_is_corrupt_history_and_never_active(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, _, lifecycle, _, lifecycle_store, _ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    lifecycle.revoke(
        RevokeSkillVersionRequest(
            identity=publication.identity,
            actor_ref=ACTOR,
            reason=REASON,
            occurred_at=NOW + timedelta(minutes=2),
            event_ref=SkillSemanticReference("event:race-revocation"),
            decision_ref=SkillSemanticReference("governance:race-revocation"),
        )
    )
    lifecycle_store.append_activation(
        SkillActivationRecord(
            record_id=SkillStoreRecordId("activation:late-after-revocation"),
            identity=publication.identity,
            installation_id=installed.record.record_id,
            activated_at=NOW + timedelta(minutes=3),
            actor_ref=ACTOR,
            reason=REASON,
        )
    )
    with pytest.raises(CorruptedSkillLifecycleHistory):
        lifecycle.projection(publication.identity)


def test_termination_race_preserves_facts_but_invalidates_combined_projection(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, _, activation, _, store, *_ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    activation.activate(
        _activate_request(publication.identity, installed.record.record_id)
    )
    store.append_termination(
        SkillInstallationTerminationRecord(
            record_id=SkillStoreRecordId("installation-end:raced"),
            installation_id=installed.record.record_id,
            identity=publication.identity,
            terminated_at=NOW + timedelta(minutes=3),
            actor_ref=ACTOR,
            reason=SkillInstallationTerminationReason.DETACHED,
        )
    )
    assert len(store.installations) == 1
    assert len(store.terminations) == 1
    with pytest.raises(InvalidOperationalActivationParent):
        activation.projection(publication.identity)


def test_termination_replay_and_lost_response(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, termination, _, _, store, *_ = _harness(publication)
    installed = installations.install(_install_request(publication, snapshot))
    request = _terminate_request(
        publication.identity,
        installed.record.record_id,
        SkillInstallationTerminationReason.DETACHED,
    )
    store.fail_after_termination = True
    with pytest.raises(SkillInstallationStoreUnavailable):
        termination.terminate(request)
    replay = termination.terminate(
        replace(
            request,
            idempotency_ref=SkillSemanticReference("idempotency:termination-retry"),
        )
    )
    assert replay.outcome is SkillInstallationOutcome.IDEMPOTENT_REPLAY


def test_termination_does_not_revoke_and_deactivation_does_not_uninstall(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, termination, activation, lifecycle, store, *_ = _harness(
        publication
    )
    installed = installations.install(_install_request(publication, snapshot))
    activation.activate(_activate_request(publication.identity, installed.record.record_id))
    activation.deactivate(_deactivate_request(publication.identity))
    assert installed.record.record_id in store.installations
    terminated = termination.terminate(
        _terminate_request(
            publication.identity,
            installed.record.record_id,
            SkillInstallationTerminationReason.DETACHED,
        )
    )
    assert not lifecycle.projection(publication.identity).revoked
    assert terminated.record.installation_id in store.installations


def test_errors_are_fixed_and_do_not_leak_semantic_references() -> None:
    secret = "SECRET-LOCAL-LOCATOR"
    captured = SkillInstallationNotFound(secret)
    assert str(captured) == "skill installation was not found"
    assert secret not in str(captured)
    assert secret not in repr(captured)


def test_requests_results_and_projections_are_frozen(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "package")
    publication = _published(snapshot)
    installations, *_ = _harness(publication)
    request = _install_request(publication, snapshot)
    result = installations.install(request)
    with pytest.raises(FrozenInstanceError):
        request.identity = publication.identity  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.projection.has_current_registration = False  # type: ignore[misc]


def test_public_surface_and_no_implicit_progression() -> None:
    import synapse.skills as skills

    assert {
        "SkillInstallationService",
        "SkillInstallationTerminationService",
        "SkillInstallationParentVerifier",
        "SkillActivationService",
        "InstalledSkillContentRef",
        "SkillOperationalProjection",
    }.issubset(skills.__all__)
    assert {
        "_installation_id",
        "_project_installations",
        "FakeInstallationStore",
    }.isdisjoint(skills.__all__)
    forbidden = {
        "copy",
        "download",
        "execute",
        "evaluate",
        "approve",
        "resolve",
        "start_sandbox",
    }
    assert forbidden.isdisjoint(dir(SkillInstallationService))
    assert forbidden.isdisjoint(dir(SkillActivationService))
