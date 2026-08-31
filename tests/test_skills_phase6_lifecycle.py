from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.skills.phase2_models import (
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillContentKind,
    SkillContentRef,
    SkillId,
    SkillLogicalPath,
    SkillManifestFormatVersion,
    SkillProvenance,
    SkillPublicationScope,
    SkillSemanticReference,
    SkillVersion,
)
from synapse.skills.phase3_contracts import (
    SkillLifecycleHistory,
    SkillStoreWriteOutcome,
)
from synapse.skills.phase3_errors import (
    InvalidSkillStoreRecord,
    SkillStoreDivergentDuplicate,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillActivationRecord,
    SkillLifecycleKind,
    SkillLifecycleReason,
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
    MissingLifecycleDecisionReference,
    RevokedSkillVersion,
    SkillLifecycleConflict,
    SkillLifecycleStoreUnavailable,
    SkillVersionNotPublished,
)
from synapse.skills.phase6_lifecycle import SkillLifecycleService
from synapse.skills.phase6_models import (
    DeactivateSkillVersionRequest,
    DeprecateSkillVersionRequest,
    ReenableSkillVersionRequest,
    RevokeSkillVersionRequest,
    RollbackSkillVersionRequest,
    SkillActivationState,
    SkillLifecycleOutcome,
    SkillSelectionState,
    SupersedeSkillVersionRequest,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
ACTOR = SkillSemanticReference("actor:lifecycle-test")
REASON = SkillLifecycleReason.OPERATOR
DECISION = SkillSemanticReference("governance:lifecycle-decision")


def _published(
    version: str = "1.0.0",
    skill_id: str = "lifecycle-skill",
    *,
    content_digest: str = "b",
) -> PublishedSkillVersionRecord:
    content = SkillContentRef(
        SkillLogicalPath("SKILL.md"),
        SkillContentFingerprint("a" * 64),
        SkillContentKind.INSTRUCTIONS,
        "text/markdown",
        10,
    )
    manifest = PublishedSkillManifest(
        format_version=SkillManifestFormatVersion(1),
        skill_id=SkillId(skill_id),
        version=SkillVersion.parse(version),
        display_name="Lifecycle skill",
        summary="Lifecycle service fixture.",
        description="An immutable publication used by lifecycle tests.",
        provenance=SkillProvenance(SkillSemanticReference("publisher:synapse")),
        scopes=(SkillPublicationScope.SYSTEM,),
        content=(content,),
    )
    return PublishedSkillVersionRecord(
        identity=PublishedSkillVersionId.from_manifest(
            manifest, SkillContentFingerprint(content_digest * 64)
        ),
        manifest=manifest,
        recorded_at=NOW,
        actor_ref=ACTOR,
        publication_ref=SkillSemanticReference("publication:lifecycle-test"),
    )


def _timestamp(record: object) -> datetime:
    for name in ("occurred_at", "activated_at", "revoked_at"):
        if hasattr(record, name):
            return getattr(record, name)
    raise AssertionError("unknown record")


class FakeCatalog:
    def __init__(self, *records: PublishedSkillVersionRecord) -> None:
        self.records = {record.identity: record for record in records}
        self.unavailable = False

    def save_version(
        self, record: PublishedSkillVersionRecord
    ) -> SkillStoreWriteOutcome:
        raise AssertionError("lifecycle never publishes")

    def get_version(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        if self.unavailable:
            raise SkillStoreUnavailable()
        try:
            return self.records[identity]
        except KeyError:
            raise SkillStoreNotFound() from None

    def list_versions(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        raise AssertionError("lifecycle never selects a version")


class FakeLifecycle:
    def __init__(self) -> None:
        self.records: dict[
            SkillStoreRecordId,
            SkillLifecycleRecord | SkillActivationRecord | SkillRevocationRecord,
        ] = {}
        self.unavailable = False
        self.fail_after_append = False
        self.complete = True
        self.reverse_history = False

    def _append(self, record):
        if self.unavailable:
            raise SkillStoreUnavailable()
        existing = self.records.get(record.record_id)
        if existing is None:
            self.records[record.record_id] = record
            if self.fail_after_append:
                self.fail_after_append = False
                raise SkillStoreUnavailable()
            return SkillStoreWriteOutcome.CREATED
        if existing == record:
            return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
        raise SkillStoreDivergentDuplicate()

    def append_lifecycle(self, record: SkillLifecycleRecord):
        return self._append(record)

    def append_activation(self, record: SkillActivationRecord):
        return self._append(record)

    def append_revocation(self, record: SkillRevocationRecord):
        return self._append(record)

    def history(self, identity, limit):
        if self.unavailable:
            raise SkillStoreUnavailable()
        records = sorted(
            (
                record
                for record in self.records.values()
                if record.identity == identity
            ),
            key=lambda item: (_timestamp(item), str(item.record_id)),
            reverse=self.reverse_history,
        )
        return SkillLifecycleHistory(
            records=tuple(records[: limit.limit]),
            complete=self.complete,
        )


class FakeActivationParents:
    def __init__(self) -> None:
        self.valid = True

    def is_valid_parent(self, identity, installation_id):
        return (
            self.valid
            and isinstance(identity, PublishedSkillVersionId)
            and installation_id
            == SkillStoreRecordId("installation:verified-parent")
        )


def _service(*records: PublishedSkillVersionRecord):
    store = FakeLifecycle()
    catalog = FakeCatalog(*records)
    parents = FakeActivationParents()
    return SkillLifecycleService(catalog, store, parents), store, catalog


def _fields(
    identity: PublishedSkillVersionId,
    minute: int,
    event: str,
    *,
    actor: SkillSemanticReference = ACTOR,
    reason: SkillLifecycleReason = REASON,
):
    return {
        "identity": identity,
        "actor_ref": actor,
        "reason": reason,
        "occurred_at": NOW + timedelta(minutes=minute),
        "event_ref": SkillSemanticReference(f"event:{event}"),
    }


def _seed_activation(
    store: FakeLifecycle,
    identity: PublishedSkillVersionId,
    minute: int = 1,
) -> SkillActivationRecord:
    record = SkillActivationRecord(
        record_id=SkillStoreRecordId(f"activation:seed-{minute}"),
        identity=identity,
        installation_id=SkillStoreRecordId("installation:verified-parent"),
        activated_at=NOW + timedelta(minutes=minute),
        actor_ref=ACTOR,
        reason=REASON,
    )
    store.records[record.record_id] = record
    return record


def _deactivate(service: SkillLifecycleService, identity, minute: int, event: str):
    return service.deactivate(
        DeactivateSkillVersionRequest(**_fields(identity, minute, event))
    )


def _deprecate(service: SkillLifecycleService, identity, minute: int, event: str):
    return service.deprecate(
        DeprecateSkillVersionRequest(**_fields(identity, minute, event))
    )


def _reenable(service: SkillLifecycleService, identity, minute: int, event: str):
    return service.reenable(
        ReenableSkillVersionRequest(**_fields(identity, minute, event))
    )


def _supersede(
    service: SkillLifecycleService,
    identity,
    target,
    minute: int,
    event: str,
):
    return service.supersede(
        SupersedeSkillVersionRequest(
            **_fields(identity, minute, event),
            replacement=target,
        )
    )


def _rollback(
    service: SkillLifecycleService,
    identity,
    target,
    minute: int,
    event: str,
):
    return service.rollback(
        RollbackSkillVersionRequest(
            **_fields(identity, minute, event),
            target=target,
            decision_ref=DECISION,
        )
    )


def _revoke(service: SkillLifecycleService, identity, minute: int, event: str):
    return service.revoke(
        RevokeSkillVersionRequest(
            **_fields(identity, minute, event),
            decision_ref=DECISION,
        )
    )


def test_initial_projection_has_orthogonal_baseline_dimensions() -> None:
    publication = _published()
    service, _, _ = _service(publication)
    projection = service.projection(publication.identity)
    assert projection.activation_state is SkillActivationState.NEVER_ACTIVATED
    assert projection.selection_state is SkillSelectionState.ELIGIBLE
    assert projection.activatable and projection.resolvable
    assert not projection.active


def test_slice6_exposes_only_validated_record_activation_boundary() -> None:
    publication = _published()
    service, _, _ = _service(publication)
    assert "activate" in dir(service)
    assert service.projection(publication.identity).activatable


def test_unverified_activation_parent_never_projects_active() -> None:
    publication = _published()
    service, store, _ = _service(publication)
    record = SkillActivationRecord(
        record_id=SkillStoreRecordId("activation:unverified"),
        identity=publication.identity,
        installation_id=SkillStoreRecordId("installation:arbitrary"),
        activated_at=NOW + timedelta(minutes=1),
        actor_ref=ACTOR,
        reason=REASON,
    )
    store.records[record.record_id] = record
    with pytest.raises(InvalidSkillActivationParent):
        service.projection(publication.identity)


@pytest.mark.parametrize(
    ("scenario", "operation", "allowed"),
    (
        *(
            ("published", event, event in {"deprecate", "supersede", "rollback", "revoke"})
            for event in ("deactivate", "deprecate", "reenable", "supersede", "rollback", "revoke")
        ),
        *(
            ("active", event, event in {"deactivate", "deprecate", "supersede", "rollback", "revoke"})
            for event in ("deactivate", "deprecate", "reenable", "supersede", "rollback", "revoke")
        ),
        *(
            ("inactive", event, event in {"deprecate", "supersede", "rollback", "revoke"})
            for event in ("deactivate", "deprecate", "reenable", "supersede", "rollback", "revoke")
        ),
        *(
            ("deprecated", event, event in {"reenable", "supersede", "rollback", "revoke"})
            for event in ("deactivate", "deprecate", "reenable", "supersede", "rollback", "revoke")
        ),
        *(
            ("superseded", event, event in {"rollback", "revoke"})
            for event in ("deactivate", "deprecate", "reenable", "supersede", "rollback", "revoke")
        ),
        *(
            ("rollback", event, event in {"deprecate", "supersede", "revoke"})
            for event in ("deactivate", "deprecate", "reenable", "supersede", "rollback", "revoke")
        ),
        *(
            ("revoked", event, False)
            for event in ("deactivate", "deprecate", "reenable", "supersede", "rollback", "revoke")
        ),
    ),
)
def test_complete_transition_matrix(
    scenario: str,
    operation: str,
    allowed: bool,
) -> None:
    source = _published("1.0.0")
    target = _published("2.0.0")
    rollback_target = _published("0.9.0")
    service, store, _ = _service(source, target, rollback_target)
    identity = source.identity
    if scenario in {"active", "inactive"}:
        _seed_activation(store, identity)
    if scenario == "inactive":
        _deactivate(service, identity, 2, "setup-inactive")
    elif scenario == "deprecated":
        _deprecate(service, identity, 2, "setup-deprecated")
    elif scenario == "superseded":
        _supersede(service, identity, target.identity, 2, "setup-superseded")
    elif scenario == "rollback":
        _rollback(service, identity, rollback_target.identity, 2, "setup-rollback")
    elif scenario == "revoked":
        _revoke(service, identity, 2, "setup-revoked")

    action = {
        "deactivate": lambda: _deactivate(service, identity, 10, "matrix-deactivate"),
        "deprecate": lambda: _deprecate(service, identity, 10, "matrix-deprecate"),
        "reenable": lambda: _reenable(service, identity, 10, "matrix-reenable"),
        "supersede": lambda: _supersede(
            service, identity, target.identity, 10, "matrix-supersede"
        ),
        "rollback": lambda: _rollback(
            service, identity, rollback_target.identity, 10, "matrix-rollback"
        ),
        "revoke": lambda: _revoke(service, identity, 10, "matrix-revoke"),
    }[operation]
    if allowed:
        assert action().outcome is SkillLifecycleOutcome.CREATED
    else:
        with pytest.raises(
            (InvalidSkillLifecycleTransition, RevokedSkillVersion)
        ):
            action()


@pytest.mark.parametrize(
    "scenario",
    ("published", "active", "inactive", "deprecated", "superseded", "rollback"),
)
def test_revocation_dominates_every_valid_projection(scenario: str) -> None:
    source = _published("1.0.0")
    target = _published("2.0.0")
    service, store, _ = _service(source, target)
    identity = source.identity
    if scenario in {"active", "inactive"}:
        _seed_activation(store, identity)
    if scenario == "inactive":
        _deactivate(service, identity, 2, "inactive")
    elif scenario == "deprecated":
        _deprecate(service, identity, 2, "deprecated")
    elif scenario == "superseded":
        _supersede(service, identity, target.identity, 2, "superseded")
    elif scenario == "rollback":
        _rollback(service, identity, target.identity, 2, "rollback")
    request = RevokeSkillVersionRequest(
        **_fields(identity, 5, f"revoke-{scenario}"),
        decision_ref=DECISION,
    )
    result = service.revoke(request)
    projection = result.projection
    assert projection.revoked
    assert not projection.active
    assert not projection.activatable
    assert not projection.resolvable
    assert projection.selection_state is SkillSelectionState.REVOKED
    assert service.revoke(request).outcome is SkillLifecycleOutcome.IDEMPOTENT_REPLAY
    with pytest.raises(RevokedSkillVersion):
        _revoke(service, identity, 6, f"second-revoke-{scenario}")


def test_divergent_revocation_with_same_record_id_conflicts() -> None:
    source = _published()
    service, store, _ = _service(source)
    request = RevokeSkillVersionRequest(
        **_fields(source.identity, 1, "revoke-conflict"),
        decision_ref=DECISION,
    )
    created = service.revoke(request).record
    assert isinstance(created, SkillRevocationRecord)
    store.records[created.record_id] = replace(
        created, reason=SkillLifecycleReason.SECURITY
    )
    with pytest.raises(SkillLifecycleConflict):
        service.revoke(request)


@pytest.mark.parametrize(
    ("start", "expected"),
    (
        ("published", SkillActivationState.NEVER_ACTIVATED),
        ("active", SkillActivationState.ACTIVE),
        ("inactive", SkillActivationState.INACTIVE),
    ),
)
def test_reenable_only_clears_deprecation(
    start: str, expected: SkillActivationState
) -> None:
    source = _published()
    service, store, _ = _service(source)
    if start in {"active", "inactive"}:
        _seed_activation(store, source.identity)
    if start == "inactive":
        _deactivate(service, source.identity, 2, "inactive")
    _deprecate(service, source.identity, 3, "deprecate")
    result = _reenable(service, source.identity, 4, "reenable")
    assert not result.projection.deprecated
    assert result.projection.activation_state is expected


def test_reenable_does_not_revert_deactivation_or_supersession() -> None:
    source = _published("1.0.0")
    target = _published("2.0.0")
    service, store, _ = _service(source, target)
    _seed_activation(store, source.identity)
    _deprecate(service, source.identity, 2, "deprecated-active")
    _deactivate(service, source.identity, 3, "deactivated-while-deprecated")
    inactive = _reenable(service, source.identity, 4, "reenable-inactive")
    assert inactive.projection.activation_state is SkillActivationState.INACTIVE

    service, store, _ = _service(source, target)
    _seed_activation(store, source.identity)
    _deprecate(service, source.identity, 2, "deprecated-before-supersede")
    _supersede(service, source.identity, target.identity, 3, "supersede")
    superseded = _reenable(service, source.identity, 4, "reenable-superseded")
    assert superseded.projection.selection_state is SkillSelectionState.SUPERSEDED
    assert not superseded.projection.deprecated
    assert not superseded.projection.active_selection_eligible


def test_reenable_rejects_duplicate_layers_and_supports_multiple_cycles() -> None:
    source = _published()
    service, _, _ = _service(source)
    _deprecate(service, source.identity, 1, "dep-1")
    with pytest.raises(InvalidSkillLifecycleTransition):
        _deprecate(service, source.identity, 2, "dep-duplicate")
    _reenable(service, source.identity, 3, "reenable-1")
    with pytest.raises(InvalidSkillLifecycleTransition):
        _reenable(service, source.identity, 4, "reenable-duplicate")
    _deprecate(service, source.identity, 5, "dep-2")
    result = _reenable(service, source.identity, 6, "reenable-2")
    assert not result.projection.deprecated


def test_supersession_is_relational_and_accepts_lower_build_and_advisory_targets() -> None:
    source = _published("2.0.0")
    lower = _published("1.0.0+build.2")
    next_target = _published("3.0.0")
    service, _, _ = _service(source, lower, next_target)
    _deprecate(service, lower.identity, 1, "deprecated-target")
    result = _supersede(service, source.identity, lower.identity, 2, "lower-target")
    assert result.projection.superseded_by == lower.identity
    assert result.projection.selection_state is SkillSelectionState.SUPERSEDED
    assert service.projection(lower.identity).deprecated

    service, _, _ = _service(source, lower, next_target)
    _supersede(service, lower.identity, next_target.identity, 1, "target-chain")
    chained = _supersede(service, source.identity, lower.identity, 2, "source-chain")
    assert chained.projection.superseded_by == lower.identity


def test_supersession_detects_self_direct_and_long_cycles() -> None:
    a = _published("1.0.0")
    b = _published("2.0.0")
    c = _published("3.0.0")
    service, _, _ = _service(a, b, c)
    with pytest.raises(InvalidSkillSupersessionTarget):
        _supersede(service, a.identity, a.identity, 1, "self")
    _supersede(service, a.identity, b.identity, 1, "a-b")
    with pytest.raises(InvalidSkillSupersessionTarget):
        _supersede(service, b.identity, a.identity, 2, "b-a")

    service, _, _ = _service(a, b, c)
    _supersede(service, a.identity, b.identity, 1, "chain-a-b")
    _supersede(service, b.identity, c.identity, 2, "chain-b-c")
    with pytest.raises(InvalidSkillSupersessionTarget):
        _supersede(service, c.identity, a.identity, 3, "chain-c-a")


def test_revoked_targets_are_rejected_but_deprecated_rollback_target_is_allowed() -> None:
    source = _published("1.0.0")
    target = _published("2.0.0")
    service, _, _ = _service(source, target)
    _revoke(service, target.identity, 1, "revoke-target")
    with pytest.raises(InvalidSkillSupersessionTarget):
        _supersede(service, source.identity, target.identity, 2, "bad-supersede")
    with pytest.raises(InvalidSkillRollbackTarget):
        _rollback(service, source.identity, target.identity, 2, "bad-rollback")

    service, _, _ = _service(source, target)
    _deprecate(service, target.identity, 1, "deprecated-target")
    result = _rollback(
        service, source.identity, target.identity, 2, "explicit-deprecated-rollback"
    )
    assert result.projection.rollback_target == target.identity


def test_rollback_is_only_a_relation_and_decision_reference() -> None:
    current = _published("2.0.0")
    target = _published("1.0.0")
    service, store, _ = _service(current, target)
    _seed_activation(store, current.identity)
    result = _rollback(service, current.identity, target.identity, 2, "rollback")
    assert result.projection.rollback_target == target.identity
    assert result.projection.rollback_decision_ref == DECISION
    assert result.projection.selection_state is SkillSelectionState.ELIGIBLE
    assert result.projection.active
    target_projection = service.projection(target.identity)
    assert target_projection.activation_state is SkillActivationState.NEVER_ACTIVATED
    assert not any(
        isinstance(record, SkillActivationRecord)
        and record.identity == target.identity
        for record in store.records.values()
    )


def test_publication_prerequisite_is_exact_for_source_and_targets() -> None:
    source = _published("1.0.0")
    target = _published("2.0.0")
    divergent = _published("2.0.0", content_digest="c")
    service, _, _ = _service()
    with pytest.raises(SkillVersionNotPublished):
        _deprecate(service, source.identity, 1, "missing-source")

    service, _, _ = _service(source)
    for missing in (target.identity, divergent.identity):
        with pytest.raises(InvalidSkillSupersessionTarget):
            _supersede(service, source.identity, missing, 1, "missing-target")
        with pytest.raises(InvalidSkillRollbackTarget):
            _rollback(service, source.identity, missing, 1, "missing-rollback")


def test_catalog_and_lifecycle_unavailability_are_safe() -> None:
    source = _published()
    service, store, catalog = _service(source)
    catalog.unavailable = True
    with pytest.raises(SkillLifecycleStoreUnavailable):
        service.projection(source.identity)
    catalog.unavailable = False
    store.unavailable = True
    with pytest.raises(SkillLifecycleStoreUnavailable):
        service.projection(source.identity)


def test_history_completeness_is_explicit_not_inferred_from_count() -> None:
    source = _published()
    service, store, _ = _service(source)
    for index in range(100):
        minute = index * 2 + 1
        dep = SkillLifecycleRecord(
            SkillStoreRecordId(f"lifecycle:dep-{index}"),
            source.identity,
            SkillLifecycleKind.DEPRECATED,
            REASON,
            NOW + timedelta(minutes=minute),
            ACTOR,
        )
        enabled = SkillLifecycleRecord(
            SkillStoreRecordId(f"lifecycle:enable-{index}"),
            source.identity,
            SkillLifecycleKind.REENABLED,
            REASON,
            NOW + timedelta(minutes=minute + 1),
            ACTOR,
        )
        store.records[dep.record_id] = dep
        store.records[enabled.record_id] = enabled
    assert len(service.history(source.identity)) == 200
    assert not service.projection(source.identity).deprecated
    store.complete = False
    with pytest.raises(IncompleteSkillLifecycleHistory):
        service.history(source.identity)


def test_equal_timestamp_is_rejected_even_when_lexical_order_exists() -> None:
    source = _published()
    service, store, _ = _service(source)
    first = SkillLifecycleRecord(
        SkillStoreRecordId("lifecycle:a"),
        source.identity,
        SkillLifecycleKind.DEPRECATED,
        REASON,
        NOW + timedelta(minutes=1),
        ACTOR,
    )
    second = replace(
        first,
        record_id=SkillStoreRecordId("lifecycle:z"),
        kind=SkillLifecycleKind.REENABLED,
    )
    store.records[first.record_id] = first
    store.records[second.record_id] = second
    with pytest.raises(AmbiguousSkillLifecycleOrdering):
        service.projection(source.identity)


def test_backdated_equal_future_replay_and_unordered_history_policy() -> None:
    source = _published()
    service, store, _ = _service(source)
    request = DeprecateSkillVersionRequest(**_fields(source.identity, 2, "first"))
    first = service.deprecate(request)
    assert service.deprecate(request).outcome is SkillLifecycleOutcome.IDEMPOTENT_REPLAY
    with pytest.raises(InvalidSkillLifecycleTransition):
        _reenable(service, source.identity, 1, "micro-earlier")
    with pytest.raises(AmbiguousSkillLifecycleOrdering):
        _reenable(service, source.identity, 2, "same-time")
    store.reverse_history = True
    future = _reenable(service, source.identity, 60 * 24, "future")
    assert not future.projection.deprecated
    assert first.record in service.history(source.identity)


def test_event_identity_uses_full_canonical_semantic_projection() -> None:
    source = _published()

    def record_id(**changes):
        service, _, _ = _service(source)
        fields = _fields(source.identity, 1, "semantic")
        fields.update(changes)
        return service.deprecate(DeprecateSkillVersionRequest(**fields)).record.record_id

    baseline = record_id()
    assert baseline == record_id()
    assert len(
        {
            baseline,
            record_id(actor_ref=SkillSemanticReference("actor:other")),
            record_id(reason=SkillLifecycleReason.POLICY),
            record_id(occurred_at=NOW + timedelta(minutes=2)),
            record_id(event_ref=SkillSemanticReference("event:other")),
        }
    ) == 5

    target = _published("2.0.0")
    other = _published("3.0.0")
    service, _, _ = _service(source, target)
    first = service.rollback(
        RollbackSkillVersionRequest(
            **_fields(source.identity, 1, "rollback-id"),
            target=target.identity,
            decision_ref=DECISION,
        )
    ).record.record_id
    service, _, _ = _service(source, other)
    second = service.rollback(
        RollbackSkillVersionRequest(
            **_fields(source.identity, 1, "rollback-id"),
            target=other.identity,
            decision_ref=SkillSemanticReference("governance:other"),
        )
    ).record.record_id
    assert first != second


def test_lost_response_is_reconciled_by_semantic_retry() -> None:
    source = _published()
    service, store, _ = _service(source)
    store.fail_after_append = True
    request = DeprecateSkillVersionRequest(**_fields(source.identity, 1, "retry"))
    with pytest.raises(SkillLifecycleStoreUnavailable):
        service.deprecate(request)
    assert service.deprecate(request).outcome is SkillLifecycleOutcome.IDEMPOTENT_REPLAY


def test_phase3_records_reject_impossible_field_combinations() -> None:
    source = _published()
    with pytest.raises(InvalidSkillStoreRecord):
        SkillLifecycleRecord(
            SkillStoreRecordId("lifecycle:bad-decision"),
            source.identity,
            SkillLifecycleKind.DEPRECATED,
            REASON,
            NOW,
            ACTOR,
            decision_ref=DECISION,
        )
    with pytest.raises(InvalidSkillStoreRecord):
        SkillLifecycleRecord(
            SkillStoreRecordId("lifecycle:missing-decision"),
            source.identity,
            SkillLifecycleKind.ROLLBACK_REFERENCED,
            REASON,
            NOW,
            ACTOR,
            related_version=replace(
                source.identity, version=SkillVersion.parse("2.0.0")
            ),
        )


def test_missing_decision_references_fail_before_store() -> None:
    source = _published("1.0.0")
    target = _published("2.0.0")
    with pytest.raises(MissingLifecycleDecisionReference):
        RollbackSkillVersionRequest(
            **_fields(source.identity, 1, "rollback-no-decision"),
            target=target.identity,
        )
    with pytest.raises(MissingLifecycleDecisionReference):
        RevokeSkillVersionRequest(**_fields(source.identity, 1, "revoke-no-decision"))


def test_corrupted_identity_and_post_revocation_history_are_rejected() -> None:
    source = _published("1.0.0")
    other = _published("2.0.0")
    service, store, _ = _service(source, other)
    invalid = SkillLifecycleRecord(
        SkillStoreRecordId("lifecycle:wrong-identity"),
        other.identity,
        SkillLifecycleKind.DEPRECATED,
        REASON,
        NOW + timedelta(minutes=1),
        ACTOR,
    )
    store.records[invalid.record_id] = invalid
    # The exact-version query excludes the unrelated record.
    assert service.projection(source.identity).resolvable

    revocation = _revoke(service, source.identity, 2, "revoke").record
    later = SkillLifecycleRecord(
        SkillStoreRecordId("lifecycle:after-revoke"),
        source.identity,
        SkillLifecycleKind.DEPRECATED,
        REASON,
        NOW + timedelta(minutes=3),
        ACTOR,
    )
    store.records[later.record_id] = later
    assert isinstance(revocation, SkillRevocationRecord)
    with pytest.raises(CorruptedSkillLifecycleHistory):
        service.projection(source.identity)


def test_models_are_frozen_and_public_surface_is_narrow() -> None:
    source = _published()
    request = DeprecateSkillVersionRequest(**_fields(source.identity, 1, "frozen"))
    with pytest.raises(FrozenInstanceError):
        request.identity = source.identity  # type: ignore[misc]

    import synapse.skills as skills

    assert {
        "DeactivateSkillVersionRequest",
        "SkillActivationState",
        "SkillActivationParentVerificationPort",
        "SkillSelectionState",
        "SkillLifecycleProjection",
        "SkillLifecycleService",
        "IncompleteSkillLifecycleHistory",
        "AmbiguousSkillLifecycleOrdering",
    }.issubset(skills.__all__)
    assert {
        "ActivateSkillVersionRequest",
        "SkillLifecycleState",
        "_project_skill_lifecycle",
        "_event_order",
        "FakeLifecycle",
    }.isdisjoint(skills.__all__)


def test_service_has_no_progression_or_external_runtime_surface() -> None:
    forbidden = {
        "install",
        "execute",
        "evaluate",
        "approve",
        "resolve",
        "start_sandbox",
        "auto_rollback",
    }
    assert forbidden.isdisjoint(dir(SkillLifecycleService))
