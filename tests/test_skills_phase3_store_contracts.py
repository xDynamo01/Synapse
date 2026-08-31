from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import TypeVar

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
    SkillAssignmentStore,
    SkillBindingStore,
    SkillCatalogStore,
    SkillInstallationHistory,
    SkillInstallationStore,
    SkillLeaseStore,
    SkillLifecycleHistory,
    SkillLifecycleStore,
    SkillStoreWriteOutcome,
)
from synapse.skills.phase3_errors import (
    InvalidSkillStoreRecord,
    SkillStoreDivergentDuplicate,
    SkillStoreInvalidParentReference,
    SkillStoreNotFound,
)
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillActivationRecord,
    SkillAssignmentRecord,
    SkillAssignmentTerminationReason,
    SkillAssignmentTerminationRecord,
    SkillEvaluationBindingRecord,
    SkillGovernanceBindingRecord,
    SkillInstallationRecord,
    SkillInstallationTerminationReason,
    SkillInstallationTerminationRecord,
    SkillLeaseRecord,
    SkillLeaseTerminationReason,
    SkillLeaseTerminationRecord,
    SkillLifecycleKind,
    SkillLifecycleReason,
    SkillLifecycleRecord,
    SkillRevocationRecord,
)
from synapse.skills.phase3_values import (
    SkillStoreQueryLimit,
    SkillStoreRecordFingerprint,
    SkillStoreRecordId,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
ACTOR = SkillSemanticReference("actor:auditor")
RecordT = TypeVar("RecordT")


def _id(value: str) -> SkillStoreRecordId:
    return SkillStoreRecordId(value)


def _manifest(version: str = "1.0.0") -> PublishedSkillManifest:
    content = SkillContentRef(
        SkillLogicalPath("SKILL.md"),
        SkillContentFingerprint(SHA_A),
        SkillContentKind.INSTRUCTIONS,
        "text/markdown",
        10,
    )
    return PublishedSkillManifest(
        format_version=SkillManifestFormatVersion(1),
        skill_id=SkillId("store-contract"),
        version=SkillVersion.parse(version),
        display_name="Store contract",
        summary="Append-only contract.",
        description="A typed manifest used to prove persistence contracts.",
        provenance=SkillProvenance(SkillSemanticReference("publisher:synapse")),
        scopes=(SkillPublicationScope.SYSTEM,),
        content=(content,),
    )


def _published(version: str = "1.0.0") -> PublishedSkillVersionRecord:
    manifest = _manifest(version)
    identity = PublishedSkillVersionId.from_manifest(
        manifest, SkillContentFingerprint(SHA_B)
    )
    return PublishedSkillVersionRecord(
        identity,
        manifest,
        NOW,
        ACTOR,
        SkillSemanticReference("publication:store-contract"),
    )


def _append(
    records: dict[SkillStoreRecordId, RecordT],
    record_id: SkillStoreRecordId,
    record: RecordT,
) -> SkillStoreWriteOutcome:
    existing = records.get(record_id)
    if existing is None:
        records[record_id] = record
        return SkillStoreWriteOutcome.CREATED
    if existing == record:
        return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    raise SkillStoreDivergentDuplicate()


def _bounded(
    records: tuple[RecordT, ...],
    limit: SkillStoreQueryLimit,
    *,
    key: object,
) -> tuple[RecordT, ...]:
    return tuple(sorted(records, key=key))[: limit.limit]  # type: ignore[arg-type]


def _fact_order(record: object) -> tuple[datetime, str]:
    timestamp = next(
        getattr(record, name)
        for name in (
            "occurred_at",
            "activated_at",
            "revoked_at",
            "installed_at",
            "terminated_at",
            "assigned_at",
            "granted_at",
            "bound_at",
        )
        if hasattr(record, name)
    )
    return timestamp, str(record.record_id)  # type: ignore[attr-defined,return-value]


class FakeCatalog:
    def __init__(self) -> None:
        self.versions: dict[
            tuple[SkillId, SkillVersion], PublishedSkillVersionRecord
        ] = {}

    def save_version(
        self, record: PublishedSkillVersionRecord
    ) -> SkillStoreWriteOutcome:
        key = (record.identity.skill_id, record.identity.version)
        existing = self.versions.get(key)
        if existing is None:
            self.versions[key] = record
            return SkillStoreWriteOutcome.CREATED
        if existing.identity == record.identity and existing.manifest == record.manifest:
            return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
        raise SkillStoreDivergentDuplicate()

    def get_version(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        try:
            record = self.versions[(identity.skill_id, identity.version)]
        except KeyError:
            raise SkillStoreNotFound() from None
        if record.identity != identity:
            raise SkillStoreNotFound()
        return record

    def list_versions(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        records = tuple(
            record
            for record in self.versions.values()
            if record.identity.skill_id == skill_id
        )
        return _bounded(
            records,
            limit,
            key=lambda item: (
                item.identity.version.precedence_key(),
                str(item.identity.version),
                item.identity.to_canonical_text(),
            ),
        )


class FakeLifecycle:
    def __init__(self) -> None:
        self.records: dict[
            SkillStoreRecordId,
            SkillLifecycleRecord | SkillActivationRecord | SkillRevocationRecord,
        ] = {}

    def append_lifecycle(
        self, record: SkillLifecycleRecord
    ) -> SkillStoreWriteOutcome:
        return _append(self.records, record.record_id, record)

    def append_activation(
        self, record: SkillActivationRecord
    ) -> SkillStoreWriteOutcome:
        return _append(self.records, record.record_id, record)

    def append_revocation(
        self, record: SkillRevocationRecord
    ) -> SkillStoreWriteOutcome:
        return _append(self.records, record.record_id, record)

    def history(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillLifecycleHistory:
        return SkillLifecycleHistory(
            _bounded(
                tuple(
                    record
                    for record in self.records.values()
                    if record.identity == identity
                ),
                limit,
                key=_fact_order,
            ),
            complete=True,
        )


class FakeInstallation:
    def __init__(self) -> None:
        self.installations: dict[SkillStoreRecordId, SkillInstallationRecord] = {}
        self.terminations: dict[
            SkillStoreRecordId, SkillInstallationTerminationRecord
        ] = {}

    def append_installation(
        self, record: SkillInstallationRecord
    ) -> SkillStoreWriteOutcome:
        return _append(self.installations, record.record_id, record)

    def append_termination(
        self, record: SkillInstallationTerminationRecord
    ) -> SkillStoreWriteOutcome:
        parent = self.installations.get(record.installation_id)
        if parent is None or parent.identity != record.identity:
            raise SkillStoreInvalidParentReference()
        return _append(self.terminations, record.record_id, record)

    def history(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillInstallationHistory:
        records = tuple(
            record
            for record in (*self.installations.values(), *self.terminations.values())
            if record.identity == identity
        )
        return SkillInstallationHistory(
            _bounded(records, limit, key=_fact_order),
            complete=True,
        )


class FakeAssignment:
    def __init__(self) -> None:
        self.assignments: dict[SkillStoreRecordId, SkillAssignmentRecord] = {}
        self.terminations: dict[
            SkillStoreRecordId, SkillAssignmentTerminationRecord
        ] = {}

    def append_assignment(
        self, record: SkillAssignmentRecord
    ) -> SkillStoreWriteOutcome:
        return _append(self.assignments, record.record_id, record)

    def append_termination(
        self, record: SkillAssignmentTerminationRecord
    ) -> SkillStoreWriteOutcome:
        parent = self.assignments.get(record.assignment_id)
        if parent is None or parent.identity != record.identity:
            raise SkillStoreInvalidParentReference()
        return _append(self.terminations, record.record_id, record)

    def history_for_subject(
        self, subject_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillAssignmentRecord | SkillAssignmentTerminationRecord, ...]:
        parents = {
            record.record_id
            for record in self.assignments.values()
            if record.subject_ref == subject_ref
        }
        records: tuple[
            SkillAssignmentRecord | SkillAssignmentTerminationRecord, ...
        ] = tuple(
            record for record in self.assignments.values() if record.record_id in parents
        ) + tuple(
            record
            for record in self.terminations.values()
            if record.assignment_id in parents
        )
        return _bounded(records, limit, key=_fact_order)


class FakeLease:
    def __init__(self) -> None:
        self.leases: dict[SkillStoreRecordId, SkillLeaseRecord] = {}
        self.terminations: dict[SkillStoreRecordId, SkillLeaseTerminationRecord] = {}

    def append_lease(self, record: SkillLeaseRecord) -> SkillStoreWriteOutcome:
        return _append(self.leases, record.record_id, record)

    def append_termination(
        self, record: SkillLeaseTerminationRecord
    ) -> SkillStoreWriteOutcome:
        parent = self.leases.get(record.lease_id)
        if parent is None or parent.identity != record.identity:
            raise SkillStoreInvalidParentReference()
        return _append(self.terminations, record.record_id, record)

    def history_for_agent(
        self, agent_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        return self._history("agent_ref", agent_ref, limit)

    def history_for_task(
        self, task_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        return self._history("task_ref", task_ref, limit)

    def history_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        parent_ids = {
            record.record_id
            for record in self.leases.values()
            if record.identity == identity
        }
        return self._records_for(parent_ids, limit)

    def _history(
        self,
        field: str,
        reference: SkillSemanticReference,
        limit: SkillStoreQueryLimit,
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        parent_ids = {
            record.record_id
            for record in self.leases.values()
            if getattr(record, field) == reference
        }
        return self._records_for(parent_ids, limit)

    def _records_for(
        self, parent_ids: set[SkillStoreRecordId], limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        records: tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...] = tuple(
            record for record in self.leases.values() if record.record_id in parent_ids
        ) + tuple(
            record
            for record in self.terminations.values()
            if record.lease_id in parent_ids
        )
        return _bounded(records, limit, key=_fact_order)


class FakeBinding:
    def __init__(self) -> None:
        self.governance: dict[SkillStoreRecordId, SkillGovernanceBindingRecord] = {}
        self.evaluations: dict[SkillStoreRecordId, SkillEvaluationBindingRecord] = {}

    def append_governance(
        self, record: SkillGovernanceBindingRecord
    ) -> SkillStoreWriteOutcome:
        return _append(self.governance, record.record_id, record)

    def append_evaluation(
        self, record: SkillEvaluationBindingRecord
    ) -> SkillStoreWriteOutcome:
        return _append(self.evaluations, record.record_id, record)

    def list_governance_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillGovernanceBindingRecord, ...]:
        return _bounded(
            tuple(record for record in self.governance.values() if record.identity == identity),
            limit,
            key=_fact_order,
        )

    def list_evaluations_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillEvaluationBindingRecord, ...]:
        return _bounded(
            tuple(record for record in self.evaluations.values() if record.identity == identity),
            limit,
            key=_fact_order,
        )


def test_fakes_satisfy_only_the_six_narrow_protocol_shapes() -> None:
    catalog: SkillCatalogStore = FakeCatalog()
    lifecycle: SkillLifecycleStore = FakeLifecycle()
    installation: SkillInstallationStore = FakeInstallation()
    assignment: SkillAssignmentStore = FakeAssignment()
    lease: SkillLeaseStore = FakeLease()
    binding: SkillBindingStore = FakeBinding()
    assert all(
        port is not None
        for port in (catalog, lifecycle, installation, assignment, lease, binding)
    )


def test_catalog_has_one_authority_and_orders_bounded_versions_by_semver() -> None:
    catalog = FakeCatalog()
    versions = (
        _published("2.0.0"),
        _published("1.0.0+build.2"),
        _published("1.0.0+build.1"),
    )
    for record in versions:
        assert catalog.save_version(record) is SkillStoreWriteOutcome.CREATED
    assert catalog.save_version(versions[0]) is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    with pytest.raises(SkillStoreDivergentDuplicate):
        catalog.save_version(
            replace(
                versions[0],
                identity=replace(
                    versions[0].identity,
                    content_fingerprint=SkillContentFingerprint(SHA_A),
                ),
            )
        )
    assert (
        catalog.save_version(
            replace(versions[0], actor_ref=SkillSemanticReference("actor:other"))
        )
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert catalog.get_version(versions[0].identity) == versions[0]
    ordered = catalog.list_versions(
        versions[0].identity.skill_id, SkillStoreQueryLimit(2)
    )
    assert tuple(str(record.identity.version) for record in ordered) == (
        "1.0.0+build.1",
        "1.0.0+build.2",
    )
    with pytest.raises(SkillStoreNotFound):
        catalog.get_version(_published("3.0.0").identity)
    assert not hasattr(catalog, "save_publication")
    assert not hasattr(catalog, "delete")


def test_lifecycle_facts_are_separate_without_transition_or_parent_authority() -> None:
    lifecycle = FakeLifecycle()
    version = _published()
    activation = SkillActivationRecord(
        _id("activation:local-v1"),
        version.identity,
        _id("installation:local-v1"),
        NOW,
        ACTOR,
        SkillLifecycleReason.OPERATOR,
    )
    disabled = SkillLifecycleRecord(
        _id("lifecycle:disable-v1"),
        version.identity,
        SkillLifecycleKind.DEACTIVATED,
        SkillLifecycleReason.POLICY,
        NOW + timedelta(minutes=1),
        ACTOR,
    )
    revocation = SkillRevocationRecord(
        _id("revocation:v1"),
        version.identity,
        NOW + timedelta(minutes=2),
        ACTOR,
        SkillLifecycleReason.SECURITY,
        SkillSemanticReference("revocation:security-review"),
    )
    assert lifecycle.append_activation(activation) is SkillStoreWriteOutcome.CREATED
    lifecycle.append_lifecycle(disabled)
    lifecycle.append_revocation(revocation)
    assert lifecycle.history(version.identity, SkillStoreQueryLimit()).records.__eq__(
        (activation, disabled, revocation)
    )
    assert not hasattr(lifecycle, "latest")
    assert not hasattr(lifecycle, "transition")


def test_family_terminations_reference_local_parents_without_deleting_history() -> None:
    version = _published()
    installations = FakeInstallation()
    installation = SkillInstallationRecord(
        _id("installation:local-v1"),
        version.identity,
        version.identity.content_fingerprint,
        SkillSemanticReference("content:verified-package"),
        SkillSemanticReference("storage-profile:local"),
        NOW,
        ACTOR,
        SkillSemanticReference("registration:local-v1"),
    )
    installations.append_installation(installation)
    installation_end = SkillInstallationTerminationRecord(
        _id("installation-end:local-v1"),
        installation.record_id,
        version.identity,
        NOW + timedelta(minutes=1),
        ACTOR,
        SkillInstallationTerminationReason.UNINSTALLED,
    )
    assert installations.append_termination(
        installation_end
    ) is SkillStoreWriteOutcome.CREATED
    assert installations.append_termination(
        installation_end
    ) is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY

    assignments = FakeAssignment()
    assignment = SkillAssignmentRecord(
        _id("assignment:agent-v1"),
        version.identity,
        SkillSemanticReference("agent:researcher"),
        SkillPublicationScope.AGENT,
        NOW,
        ACTOR,
        SkillSemanticReference("reason:explicit"),
    )
    assignments.append_assignment(assignment)
    assignment_end = SkillAssignmentTerminationRecord(
        _id("assignment-end:agent-v1"),
        assignment.record_id,
        version.identity,
        NOW + timedelta(minutes=1),
        ACTOR,
        SkillAssignmentTerminationReason.REVOKED,
    )
    assignments.append_termination(assignment_end)

    leases = FakeLease()
    lease = SkillLeaseRecord(
        _id("lease:task-v1"),
        assignment.record_id,
        version.identity,
        SkillSemanticReference("agent:researcher"),
        SkillSemanticReference("task:review"),
        NOW,
        NOW + timedelta(minutes=5),
        ACTOR,
    )
    leases.append_lease(lease)
    lease_end = SkillLeaseTerminationRecord(
        _id("lease-end:task-v1"),
        lease.record_id,
        version.identity,
        lease.expires_at,
        ACTOR,
        SkillLeaseTerminationReason.EXPIRED,
    )
    leases.append_termination(lease_end)
    assert len(
        leases.history_for_version(version.identity, SkillStoreQueryLimit())
    ) == 2
    assert not hasattr(installations, "delete")
    assert not hasattr(assignments, "delete")
    assert not hasattr(leases, "cleanup")
    with pytest.raises(SkillStoreInvalidParentReference):
        leases.append_termination(
            replace(lease_end, record_id=_id("lease-end:missing"), lease_id=_id("lease:missing"))
        )


def test_bindings_share_a_protocol_but_never_a_union_method_or_external_payload() -> None:
    bindings = FakeBinding()
    version = _published()
    governance = SkillGovernanceBindingRecord(
        _id("governance-binding:v1"),
        version.identity,
        SkillSemanticReference("governance:rfc-1"),
        SkillStoreRecordFingerprint(SHA_A),
        NOW,
        ACTOR,
    )
    evaluation = SkillEvaluationBindingRecord(
        _id("evaluation-binding:v1"),
        version.identity,
        SkillSemanticReference("evaluation:run-1"),
        SkillStoreRecordFingerprint(SHA_B),
        NOW,
        ACTOR,
    )
    bindings.append_governance(governance)
    bindings.append_evaluation(evaluation)
    assert bindings.list_governance_for_version(
        version.identity, SkillStoreQueryLimit()
    ) == (governance,)
    assert bindings.list_evaluations_for_version(
        version.identity, SkillStoreQueryLimit()
    ) == (evaluation,)
    assert not hasattr(bindings, "list_for_version")
    for record in (governance, evaluation):
        for forbidden in ("payload", "evidence", "approval", "trusted", "permission"):
            assert not hasattr(record, forbidden)


def test_namespaced_identities_and_structural_replay_are_family_specific() -> None:
    version = _published()
    with pytest.raises(InvalidSkillStoreRecord):
        SkillActivationRecord(
            _id("lease:wrong-family"),
            version.identity,
            _id("installation:local-v1"),
            NOW,
            ACTOR,
            SkillLifecycleReason.OPERATOR,
        )
    lifecycle = FakeLifecycle()
    first = SkillLifecycleRecord(
        _id("lifecycle:policy-v1"),
        version.identity,
        SkillLifecycleKind.DEACTIVATED,
        SkillLifecycleReason.POLICY,
        NOW,
        ACTOR,
    )
    assert lifecycle.append_lifecycle(first) is SkillStoreWriteOutcome.CREATED
    assert lifecycle.append_lifecycle(first) is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    with pytest.raises(SkillStoreDivergentDuplicate):
        lifecycle.append_lifecycle(
            replace(first, reason=SkillLifecycleReason.SECURITY)
        )


def test_timestamps_are_caller_supplied_utc_facts_and_order_history() -> None:
    version = _published()
    lifecycle = FakeLifecycle()
    later = SkillLifecycleRecord(
        _id("lifecycle:later"),
        version.identity,
        SkillLifecycleKind.DEACTIVATED,
        SkillLifecycleReason.POLICY,
        NOW + timedelta(minutes=2),
        ACTOR,
    )
    earlier = replace(
        later,
        record_id=_id("lifecycle:earlier"),
        occurred_at=NOW,
        kind=SkillLifecycleKind.DEPRECATED,
    )
    lifecycle.append_lifecycle(later)
    lifecycle.append_lifecycle(earlier)
    assert lifecycle.history(version.identity, SkillStoreQueryLimit()).records == (
        earlier,
        later,
    )
    with pytest.raises(InvalidSkillStoreRecord):
        replace(earlier, occurred_at=NOW.replace(tzinfo=None))
    with pytest.raises(FrozenInstanceError):
        earlier.actor_ref = SkillSemanticReference("actor:other")  # type: ignore[misc]
    with pytest.raises(InvalidSkillStoreRecord):
        SkillStoreQueryLimit(0)


def test_errors_are_fixed_safe_and_removed_contracts_are_absent() -> None:
    raw = "SECRET-RAW-STORE-PAYLOAD"
    with pytest.raises(InvalidSkillStoreRecord) as captured:
        SkillStoreRecordId(raw)
    assert raw not in str(captured.value)
    assert raw not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert raw not in str(SkillStoreDivergentDuplicate(raw))

    import synapse.skills as skills_api
    import synapse.skills.phase3_contracts as contracts
    import synapse.skills.phase3_errors as errors
    import synapse.skills.phase3_records as records
    import synapse.skills.phase3_values as values

    assert not hasattr(records, "SkillPublicationRecord")
    assert not hasattr(records, "SkillContentVerificationRecord")
    assert not hasattr(contracts, "SkillContentVerificationStore")
    assert not hasattr(contracts, "SkillStorePage")
    assert not hasattr(values, "SkillStoreRecordFormatVersion")
    assert not hasattr(errors, "SkillStoreStaleRevision")
    assert {
        "PublishedSkillVersionRecord",
        "SkillAssignmentStore",
        "SkillBindingStore",
        "SkillCatalogStore",
        "SkillInstallationStore",
        "SkillInstallationHistory",
        "SkillLeaseStore",
        "SkillLifecycleStore",
        "SkillLifecycleHistory",
        "SkillStoreWriteOutcome",
        "SkillStoreQueryLimit",
    }.issubset(skills_api.__all__)
    assert {
        "SkillActivationRecord",
        "SkillContentVerificationRecord",
        "SkillLifecycleReason",
        "SkillStoreRecordId",
    }.isdisjoint(skills_api.__all__)
