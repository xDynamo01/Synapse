from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_type_hints

import pytest

from synapse.skills.persistence import (
    SkillPersistenceDatabaseCorrupt,
    SkillPersistenceIntegrityChecker,
    SkillPersistenceMigrationChecksumMismatch,
    SkillPersistenceMigrationRequired,
    SkillPersistenceMigrator,
    SkillPersistenceRecordDecodeFailed,
    SkillPersistenceSchemaUnsupported,
    SkillPersistenceSchemaVersion,
    SkillPersistenceUnavailable,
    SkillSQLiteConfig,
    SkillSQLiteConnectionFactory,
    SQLiteSkillAssignmentStore,
    SQLiteSkillBindingStore,
    SQLiteSkillCatalogStore,
    SQLiteSkillExternalBindingStore,
    SQLiteSkillInstallationStore,
    SQLiteSkillLeaseStore,
    SQLiteSkillLifecycleStore,
    SQLiteSkillPrivateEvalBindingStore,
)
from synapse.skills.persistence.codec import decode_record, encode_record
from synapse.skills.phase2_models import (
    CapabilityRequirement,
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillContentKind,
    SkillContentRef,
    SkillExecutionDeclaration,
    SkillExecutionRuntime,
    SkillId,
    SkillLogicalPath,
    SkillManifestFormatVersion,
    SkillProvenance,
    SkillPublicationScope,
    SkillRequirementId,
    SkillResourceRequirement,
    SkillSemanticReference,
    SkillVersion,
)
from synapse.skills.phase3_contracts import (
    SkillAssignmentStore,
    SkillBindingStore,
    SkillCatalogStore,
    SkillInstallationStore,
    SkillLeaseStore,
    SkillLifecycleStore,
    SkillStoreWriteOutcome,
)
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreInvalidParentReference,
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
)
from synapse.skills.phase3_values import (
    SkillStoreQueryLimit,
    SkillStoreRecordFingerprint,
    SkillStoreRecordId,
)
from synapse.skills.phase8_contracts import SkillDependencyCatalogProvider
from synapse.skills.phase10_contracts import SkillExternalBindingStore
from synapse.skills.phase10_governance import SkillGovernanceBindingService
from synapse.skills.phase10_models import (
    BindSkillGovernanceDecisionRequest,
)
from synapse.skills.phase10_models import (
    SkillGovernanceBindingRecord as ExternalGovernanceBindingRecord,
)
from synapse.skills.phase10_refs import (
    ExternalAuthorityRef,
    ExternalBinderRef,
    GovernanceDecisionKindRef,
    GovernanceDecisionRef,
    GovernancePolicyRef,
)
from synapse.skills.phase11_bindings import SkillPrivateEvalBindingService
from synapse.skills.phase11_contracts import SkillPrivateEvalBindingStore
from synapse.skills.phase11_models import (
    BindSkillPrivateEvalResultRequest,
    SkillPrivateEvalBindingGranularity,
)
from synapse.skills.phase11_refs import (
    PrivateEvalProfileRef,
    PrivateEvalResultRef,
    PrivateEvalRunRef,
    PrivateEvalSuiteRef,
    PrivateEvalVerdictRef,
)

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)

_PORT_ADAPTERS = (
    (SkillCatalogStore, SQLiteSkillCatalogStore),
    (SkillDependencyCatalogProvider, SQLiteSkillCatalogStore),
    (SkillLifecycleStore, SQLiteSkillLifecycleStore),
    (SkillInstallationStore, SQLiteSkillInstallationStore),
    (SkillAssignmentStore, SQLiteSkillAssignmentStore),
    (SkillLeaseStore, SQLiteSkillLeaseStore),
    (SkillBindingStore, SQLiteSkillBindingStore),
    (SkillExternalBindingStore, SQLiteSkillExternalBindingStore),
    (SkillPrivateEvalBindingStore, SQLiteSkillPrivateEvalBindingStore),
)


def _publication(name: str = "sqlite-skill") -> PublishedSkillVersionRecord:
    instructions_bytes = b"# SQLite"
    entrypoint_bytes = b"opaque"
    instructions = SkillContentRef(
        SkillLogicalPath("SKILL.md"),
        SkillContentFingerprint(hashlib.sha256(instructions_bytes).hexdigest()),
        SkillContentKind.INSTRUCTIONS,
        "text/markdown",
        len(instructions_bytes),
    )
    entrypoint = SkillContentRef(
        SkillLogicalPath("scripts/main.py"),
        SkillContentFingerprint(hashlib.sha256(entrypoint_bytes).hexdigest()),
        SkillContentKind.ENTRYPOINT,
        "text/x-python",
        len(entrypoint_bytes),
    )
    manifest = PublishedSkillManifest(
        SkillManifestFormatVersion(1),
        SkillId(name),
        SkillVersion.parse("1.0.0"),
        "SQLite skill",
        "Durable adapter subject.",
        "A closed persistence test subject.",
        SkillProvenance(SkillSemanticReference("publisher:test")),
        (SkillPublicationScope.PROJECT,),
        (instructions, entrypoint),
        capabilities=(CapabilityRequirement(SkillRequirementId("text.generate")),),
        execution=(
            SkillExecutionDeclaration(
                entrypoint,
                SkillExecutionRuntime.PYTHON,
                SkillSemanticReference("sandbox-profile:restricted"),
                SkillResourceRequirement(30, 128, 100),
            ),
        ),
    )
    identity = PublishedSkillVersionId.from_manifest(
        manifest,
        SkillContentFingerprint(
            hashlib.sha256(instructions_bytes + entrypoint_bytes).hexdigest()
        ),
    )
    return PublishedSkillVersionRecord(
        identity,
        manifest,
        NOW,
        SkillSemanticReference("actor:publisher"),
        SkillSemanticReference("publication:test"),
    )


@pytest.fixture
def database(tmp_path: Path) -> tuple[Path, SkillSQLiteConnectionFactory]:
    path = tmp_path / "skills.sqlite3"
    factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(path))
    SkillPersistenceMigrator(factory, lambda: NOW).migrate()
    return path, factory


@pytest.mark.parametrize(("port", "adapter"), _PORT_ADAPTERS)
def test_adapter_public_methods_match_port_signatures(
    port: type[object], adapter: type[object]
) -> None:
    required = {
        name: value
        for name, value in vars(port).items()
        if callable(value) and not name.startswith("_")
    }
    for name, method in required.items():
        assert hasattr(adapter, name)
        adapter_method = getattr(adapter, name)
        assert tuple(inspect.signature(adapter_method).parameters) == tuple(
            inspect.signature(method).parameters
        )
        assert get_type_hints(adapter_method) == get_type_hints(method)


def test_empty_database_migrates_to_v1_and_is_idempotent(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    migrator = SkillPersistenceMigrator(factory, lambda: NOW)
    assert migrator.migrate() is SkillPersistenceSchemaVersion.V1
    assert migrator.verify() is SkillPersistenceSchemaVersion.V1


def test_migration_has_audited_stable_metadata(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    with factory.connection() as connection:
        row = connection.execute(
            "SELECT migration_id, from_version, to_version, checksum, applied_at "
            "FROM skill_migration_history"
        ).fetchone()
    assert tuple(row)[:3] == ("skills-schema-v1", 0, 1)
    assert len(row[3]) == 64
    assert row[4] == "2026-07-29T18:00:00.000000Z"


def test_every_connection_has_hardened_local_configuration(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    with factory.connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
        assert connection.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        assert connection.row_factory is sqlite3.Row
        assert connection.isolation_level is None
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_future_schema_is_rejected(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    with factory.connection() as connection:
        connection.execute("UPDATE skill_schema_metadata SET schema_version = 99")
    with pytest.raises(SkillPersistenceSchemaUnsupported):
        SkillPersistenceMigrator(factory, lambda: NOW).verify()


def test_missing_metadata_is_not_destructively_reset(tmp_path: Path) -> None:
    path = tmp_path / "partial.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(path))
    with pytest.raises(SkillPersistenceMigrationRequired):
        SkillPersistenceMigrator(factory, lambda: NOW).migrate()
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'unrelated'"
        ).fetchone()


def test_migration_checksum_mismatch_is_rejected(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    with factory.connection() as connection:
        connection.execute(
            "UPDATE skill_migration_history SET checksum = ?", ("0" * 64,)
        )
    with pytest.raises(SkillPersistenceMigrationChecksumMismatch):
        SkillPersistenceMigrator(factory, lambda: NOW).verify()


def test_interrupted_migration_rolls_back_and_can_retry(tmp_path: Path) -> None:
    path = tmp_path / "interrupted.sqlite3"
    factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(path))

    def interrupted_clock() -> datetime:
        raise RuntimeError("injected test interruption")

    with pytest.raises(RuntimeError, match="injected test interruption"):
        SkillPersistenceMigrator(factory, interrupted_clock).migrate()
    assert (
        SkillPersistenceMigrator(factory, lambda: NOW).migrate()
        is SkillPersistenceSchemaVersion.V1
    )


def test_duplicate_migration_identity_is_rejected_by_database(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    with factory.connection() as connection:
        row = connection.execute(
            "SELECT migration_id, from_version, to_version, checksum, applied_at "
            "FROM skill_migration_history"
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO skill_migration_history"
                "(migration_id, from_version, to_version, checksum, applied_at) "
                "VALUES (?, ?, ?, ?, ?)",
                tuple(row),
            )


def test_foreign_key_integrity_failure_is_detected(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    with factory.connection() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO lifecycle_records"
            "(record_id, exact_identity, record_kind, occurred_at, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            ("lifecycle:broken", "missing", "lifecycle", "2026-01-01T00:00:00Z", "{}"),
        )
    with pytest.raises(SkillPersistenceDatabaseCorrupt):
        SkillPersistenceMigrator(factory, lambda: NOW).verify()


def test_catalog_round_trip_replay_restart_and_divergence(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    path, factory = database
    record = _publication()
    store = SQLiteSkillCatalogStore(factory)
    assert store.save_version(record) is SkillStoreWriteOutcome.CREATED
    assert store.save_version(record) is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY

    reopened = SQLiteSkillCatalogStore(
        SkillSQLiteConnectionFactory(SkillSQLiteConfig(path))
    )
    assert reopened.get_version(record.identity) == record
    assert reopened.save_version(record) is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    with pytest.raises(SkillStoreDivergentDuplicate):
        reopened.save_version(
            replace(record, publication_ref=SkillSemanticReference("publication:other"))
        )


def test_malformed_canonical_record_fails_closed(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    record = _publication()
    store = SQLiteSkillCatalogStore(factory)
    store.save_version(record)
    with factory.connection() as connection:
        connection.execute("DROP TRIGGER publications_no_update")
        connection.execute(
            "UPDATE publications SET payload = ? WHERE exact_identity = ?",
            ("{}", record.identity.to_canonical_text()),
        )
    with pytest.raises(SkillPersistenceRecordDecodeFailed):
        store.get_version(record.identity)


def test_semantically_equal_noncanonical_json_is_still_replay(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    record = _publication()
    store = SQLiteSkillCatalogStore(factory)
    store.save_version(record)
    reordered = json.dumps(
        json.loads(encode_record(record)),
        ensure_ascii=True,
        separators=(", ", ": "),
        sort_keys=False,
    )
    assert reordered != encode_record(record)
    with factory.connection() as connection:
        connection.execute("DROP TRIGGER publications_no_update")
        connection.execute(
            "UPDATE publications SET payload = ? WHERE exact_identity = ?",
            (reordered, record.identity.to_canonical_text()),
        )
    assert store.save_version(record) is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY


@pytest.mark.parametrize(
    ("path", "invalid"),
    [
        (("manifest", "scopes", 0), "unknown-scope"),
        (("recorded_at",), "not-a-timestamp"),
        (("identity", "content_fingerprint", "value"), "not-a-fingerprint"),
        (("actor_ref", "value"), ""),
    ],
)
def test_typed_decode_rejects_corrupt_domain_values(
    database: tuple[Path, SkillSQLiteConnectionFactory],
    path: tuple[str | int, ...],
    invalid: str,
) -> None:
    _, factory = database
    record = _publication()
    store = SQLiteSkillCatalogStore(factory)
    store.save_version(record)
    value: object = json.loads(encode_record(record))
    target = value
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = invalid  # type: ignore[index]
    with factory.connection() as connection:
        connection.execute("DROP TRIGGER publications_no_update")
        connection.execute(
            "UPDATE publications SET payload = ? WHERE exact_identity = ?",
            (json.dumps(value), record.identity.to_canonical_text()),
        )
    with pytest.raises(SkillPersistenceRecordDecodeFailed):
        store.get_version(record.identity)


@pytest.mark.parametrize(
    "payload",
    [
        '{"identity":1,"identity":2}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":1.25}',
        "[" * 66 + "0" + "]" * 66,
    ],
)
def test_codec_rejects_ambiguous_or_unbounded_json(payload: str) -> None:
    with pytest.raises(SkillPersistenceRecordDecodeFailed):
        decode_record(payload, PublishedSkillVersionRecord)


@pytest.mark.parametrize(
    ("object_type", "object_name"),
    [
        ("table", "leases"),
        ("index", "leases_by_agent"),
        ("trigger", "leases_no_update"),
    ],
)
def test_integrity_checker_detects_missing_schema_objects(
    database: tuple[Path, SkillSQLiteConnectionFactory],
    object_type: str,
    object_name: str,
) -> None:
    _, factory = database
    with factory.connection() as connection:
        connection.execute(f"DROP {object_type} {object_name}")
    with pytest.raises(SkillPersistenceDatabaseCorrupt):
        SkillPersistenceIntegrityChecker(factory).check()


def test_catalog_completeness_uses_an_extra_row(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    store = SQLiteSkillCatalogStore(factory)
    first = _publication()
    second = replace(
        _publication(),
        identity=PublishedSkillVersionId.from_manifest(
            replace(first.manifest, version=SkillVersion.parse("1.1.0")),
            first.identity.content_fingerprint,
        ),
        manifest=replace(first.manifest, version=SkillVersion.parse("1.1.0")),
    )
    store.save_version(first)
    store.save_version(second)
    page = store.list_dependency_candidates(first.identity.skill_id, SkillStoreQueryLimit(1))
    assert len(page.records) == 1
    assert not page.complete
    assert store.list_dependency_candidates(
        first.identity.skill_id, SkillStoreQueryLimit(2)
    ).complete


def test_lifecycle_history_is_ordered_bounded_and_complete(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    publication = _publication()
    SQLiteSkillCatalogStore(factory).save_version(publication)
    store = SQLiteSkillLifecycleStore(factory)
    later = SkillLifecycleRecord(
        SkillStoreRecordId("lifecycle:later"),
        publication.identity,
        SkillLifecycleKind.DEPRECATED,
        SkillLifecycleReason.QUALITY,
        NOW + timedelta(seconds=2),
        SkillSemanticReference("actor:operator"),
    )
    earlier = replace(
        later,
        record_id=SkillStoreRecordId("lifecycle:earlier"),
        kind=SkillLifecycleKind.DEACTIVATED,
        occurred_at=NOW + timedelta(seconds=1),
    )
    store.append_lifecycle(later)
    store.append_lifecycle(earlier)
    assert (
        store.append_lifecycle(earlier)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    truncated = store.history(publication.identity, SkillStoreQueryLimit(1))
    complete = store.history(publication.identity, SkillStoreQueryLimit(2))
    assert truncated.records == (earlier,)
    assert not truncated.complete
    assert complete.records == (earlier, later)
    assert complete.complete


def test_installation_parent_and_append_only_enforcement(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    publication = _publication()
    SQLiteSkillCatalogStore(factory).save_version(publication)
    store = SQLiteSkillInstallationStore(factory)
    installation = SkillInstallationRecord(
        SkillStoreRecordId("installation:one"),
        publication.identity,
        publication.identity.content_fingerprint,
        SkillSemanticReference("content:one"),
        SkillSemanticReference("storage-profile:local"),
        NOW,
        SkillSemanticReference("actor:operator"),
        SkillSemanticReference("registration:one"),
    )
    termination = SkillInstallationTerminationRecord(
        SkillStoreRecordId("installation-end:one"),
        installation.record_id,
        publication.identity,
        NOW + timedelta(seconds=1),
        SkillSemanticReference("actor:operator"),
        SkillInstallationTerminationReason.UNINSTALLED,
    )
    with pytest.raises(SkillStoreInvalidParentReference):
        store.append_termination(termination)
    store.append_installation(installation)
    store.append_termination(termination)
    assert (
        store.append_installation(installation)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert (
        store.append_termination(termination)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert store.history(publication.identity, SkillStoreQueryLimit(10)).records == (
        installation,
        termination,
    )
    with factory.connection() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE installation_records SET payload = ? WHERE record_id = ?",
                ("{}", installation.record_id.value),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM installation_records WHERE record_id = ?",
                (installation.record_id.value,),
            )


def test_missing_publication_and_cross_identity_activation_are_parent_errors(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    missing = _publication("missing-parent")
    lifecycle_record = SkillLifecycleRecord(
        SkillStoreRecordId("lifecycle:missing"),
        missing.identity,
        SkillLifecycleKind.DEPRECATED,
        SkillLifecycleReason.QUALITY,
        NOW,
        SkillSemanticReference("actor:operator"),
    )
    with pytest.raises(SkillStoreInvalidParentReference):
        SQLiteSkillLifecycleStore(factory).append_lifecycle(lifecycle_record)

    first = _publication("first-parent")
    second = _publication("second-parent")
    catalog = SQLiteSkillCatalogStore(factory)
    catalog.save_version(first)
    catalog.save_version(second)
    installation = SkillInstallationRecord(
        SkillStoreRecordId("installation:foreign"),
        first.identity,
        first.identity.content_fingerprint,
        SkillSemanticReference("content:foreign"),
        SkillSemanticReference("storage-profile:local"),
        NOW,
        SkillSemanticReference("actor:operator"),
        SkillSemanticReference("registration:foreign"),
    )
    SQLiteSkillInstallationStore(factory).append_installation(installation)
    activation = SkillActivationRecord(
        SkillStoreRecordId("activation:wrong-parent"),
        second.identity,
        installation.record_id,
        NOW + timedelta(seconds=1),
        SkillSemanticReference("actor:operator"),
        SkillLifecycleReason.OPERATOR,
    )
    with pytest.raises(SkillStoreInvalidParentReference):
        SQLiteSkillLifecycleStore(factory).append_activation(activation)


def test_concurrent_equivalent_publication_has_one_create(database: tuple[Path, SkillSQLiteConnectionFactory]) -> None:
    _, factory = database
    record = _publication()

    def save() -> SkillStoreWriteOutcome:
        return SQLiteSkillCatalogStore(factory).save_version(record)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda _: save(), range(2)))
    assert sorted(outcomes) == sorted(
        (SkillStoreWriteOutcome.CREATED, SkillStoreWriteOutcome.IDEMPOTENT_REPLAY)
    )


def test_concurrent_divergent_publication_has_one_conflict(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    first = _publication()
    second = replace(
        first, publication_ref=SkillSemanticReference("publication:divergent")
    )

    def save(record: PublishedSkillVersionRecord) -> str:
        try:
            return SQLiteSkillCatalogStore(factory).save_version(record).value
        except SkillStoreDivergentDuplicate:
            return "divergent"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(save, (first, second)))
    assert sorted(outcomes) == ["created", "divergent"]


def test_locked_database_fails_bounded_and_safe(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    path, _ = database
    factory = SkillSQLiteConnectionFactory(
        SkillSQLiteConfig(path, busy_timeout_ms=25)
    )
    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(SkillPersistenceUnavailable):
            SQLiteSkillCatalogStore(factory).save_version(_publication())
    finally:
        blocker.rollback()
        blocker.close()


def test_binding_occurrence_races_are_equivalent_or_divergent(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "binding-source.sqlite3"
    source_factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(source_path))
    SkillPersistenceMigrator(source_factory, lambda: NOW).migrate()
    publication = _publication()
    source_catalog = SQLiteSkillCatalogStore(source_factory)
    source_catalog.save_version(publication)
    request = BindSkillGovernanceDecisionRequest(
        identity=publication.identity,
        decision_ref=GovernanceDecisionRef("governance-decision:race"),
        decision_kind_ref=GovernanceDecisionKindRef(
            "governance-decision-kind:review-outcome"
        ),
        policy_ref=GovernancePolicyRef("governance-policy:race"),
        authority_ref=ExternalAuthorityRef("external-authority:governance-race"),
        binder_ref=ExternalBinderRef("external-binder:race"),
        bound_at=NOW + timedelta(minutes=1),
    )
    record = SkillGovernanceBindingService(
        source_catalog,
        SQLiteSkillExternalBindingStore(source_factory),
        SkillStoreQueryLimit(10),
    ).bind(request).record

    equivalent_path = tmp_path / "binding-equivalent.sqlite3"
    equivalent_factory = SkillSQLiteConnectionFactory(
        SkillSQLiteConfig(equivalent_path)
    )
    SkillPersistenceMigrator(equivalent_factory, lambda: NOW).migrate()
    SQLiteSkillCatalogStore(equivalent_factory).save_version(publication)

    def append_equivalent() -> SkillStoreWriteOutcome:
        return SQLiteSkillExternalBindingStore(
            equivalent_factory
        ).append_governance(record)

    with ThreadPoolExecutor(max_workers=2) as executor:
        equivalent = tuple(executor.map(lambda _: append_equivalent(), range(2)))
    assert sorted(equivalent) == sorted(
        (SkillStoreWriteOutcome.CREATED, SkillStoreWriteOutcome.IDEMPOTENT_REPLAY)
    )

    divergent_path = tmp_path / "binding-divergent.sqlite3"
    divergent_factory = SkillSQLiteConnectionFactory(
        SkillSQLiteConfig(divergent_path)
    )
    SkillPersistenceMigrator(divergent_factory, lambda: NOW).migrate()
    SQLiteSkillCatalogStore(divergent_factory).save_version(publication)
    changed = replace(record, binder_ref=ExternalBinderRef("external-binder:other"))

    def append_divergent(candidate: ExternalGovernanceBindingRecord) -> str:
        try:
            return SQLiteSkillExternalBindingStore(
                divergent_factory
            ).append_governance(candidate).value
        except SkillStoreDivergentDuplicate:
            return "divergent"

    with ThreadPoolExecutor(max_workers=2) as executor:
        divergent = tuple(executor.map(append_divergent, (record, changed)))
    assert sorted(divergent) == ["created", "divergent"]


def test_manual_application_authority_wiring_survives_restart(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    path, factory = database
    publication = _publication()
    catalog = SQLiteSkillCatalogStore(factory)
    catalog.save_version(publication)
    external = SQLiteSkillExternalBindingStore(factory)
    governance = SkillGovernanceBindingService(
        catalog, external, SkillStoreQueryLimit(10)
    )
    request = BindSkillGovernanceDecisionRequest(
        identity=publication.identity,
        decision_ref=GovernanceDecisionRef("governance-decision:approved"),
        decision_kind_ref=GovernanceDecisionKindRef(
            "governance-decision-kind:review-outcome"
        ),
        policy_ref=GovernancePolicyRef("governance-policy:policy-a"),
        authority_ref=ExternalAuthorityRef("external-authority:governance-a"),
        binder_ref=ExternalBinderRef("external-binder:binder-a"),
        bound_at=NOW + timedelta(minutes=1),
    )
    created = governance.bind(request)

    reopened_factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(path))
    reopened = SkillGovernanceBindingService(
        SQLiteSkillCatalogStore(reopened_factory),
        SQLiteSkillExternalBindingStore(reopened_factory),
        SkillStoreQueryLimit(10),
    )
    replayed = reopened.bind(request)
    assert created.record == replayed.record
    assert replayed.outcome.value == "idempotent_replay"


def test_private_eval_binding_round_trip_preserves_opaque_refs(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    publication = _publication()
    catalog = SQLiteSkillCatalogStore(factory)
    catalog.save_version(publication)
    service = SkillPrivateEvalBindingService(
        catalog,
        SQLiteSkillPrivateEvalBindingStore(factory),
        SkillStoreQueryLimit(10),
    )
    request = BindSkillPrivateEvalResultRequest(
        identity=publication.identity,
        granularity=SkillPrivateEvalBindingGranularity.SUITE_RESULT,
        run_ref=PrivateEvalRunRef("private-eval-run:run-a"),
        result_ref=PrivateEvalResultRef("private-eval-result:result-a"),
        verdict_ref=PrivateEvalVerdictRef("private-eval-verdict:passed"),
        suite_ref=PrivateEvalSuiteRef("private-eval-suite:suite-a"),
        case_ref=None,
        profile_ref=PrivateEvalProfileRef("private-eval-profile:profile-a"),
        baseline_ref=None,
        comparison_ref=None,
        regression_ref=None,
        evidence_refs=(),
        binder_ref=ExternalBinderRef("external-binder:binder-a"),
        evaluated_at=NOW + timedelta(minutes=1),
        bound_at=NOW + timedelta(minutes=2),
    )
    created = service.bind(request)
    replayed = service.bind(request)
    projection = service.projection(publication.identity)
    assert projection.history.records == (created.record,)
    assert replayed.record == created.record
    assert replayed.outcome.value == "idempotent_replay"
    assert projection.complete


def test_assignment_lease_and_legacy_binding_contracts_round_trip(
    database: tuple[Path, SkillSQLiteConnectionFactory],
) -> None:
    _, factory = database
    publication = _publication()
    SQLiteSkillCatalogStore(factory).save_version(publication)
    subject = SkillSemanticReference("subject:test")
    assignment = SkillAssignmentRecord(
        SkillStoreRecordId("assignment:one"),
        publication.identity,
        subject,
        SkillPublicationScope.PROJECT,
        NOW,
        SkillSemanticReference("actor:operator"),
        SkillSemanticReference("reason:assigned"),
    )
    assignment_end = SkillAssignmentTerminationRecord(
        SkillStoreRecordId("assignment-end:one"),
        assignment.record_id,
        publication.identity,
        NOW + timedelta(minutes=4),
        SkillSemanticReference("actor:operator"),
        SkillAssignmentTerminationReason.REVOKED,
    )
    assignments = SQLiteSkillAssignmentStore(factory)
    assignments.append_assignment(assignment)
    assignments.append_termination(assignment_end)
    assert (
        assignments.append_assignment(assignment)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert (
        assignments.append_termination(assignment_end)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert assignments.history_for_subject(
        subject, SkillStoreQueryLimit(10)
    ) == (assignment, assignment_end)

    lease = SkillLeaseRecord(
        SkillStoreRecordId("lease:one"),
        assignment.record_id,
        publication.identity,
        SkillSemanticReference("agent:test"),
        SkillSemanticReference("task:test"),
        NOW + timedelta(minutes=1),
        NOW + timedelta(hours=1),
        SkillSemanticReference("actor:operator"),
    )
    lease_end = SkillLeaseTerminationRecord(
        SkillStoreRecordId("lease-end:one"),
        lease.record_id,
        publication.identity,
        NOW + timedelta(minutes=3),
        SkillSemanticReference("actor:operator"),
        SkillLeaseTerminationReason.TERMINATED,
    )
    leases = SQLiteSkillLeaseStore(factory)
    leases.append_lease(lease)
    leases.append_termination(lease_end)
    assert leases.append_lease(lease) is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    assert (
        leases.append_termination(lease_end)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert leases.history_for_task(
        lease.task_ref, SkillStoreQueryLimit(10)
    ) == (lease, lease_end)

    governance = SkillGovernanceBindingRecord(
        SkillStoreRecordId("governance-binding:legacy"),
        publication.identity,
        SkillSemanticReference("governance:decision"),
        SkillStoreRecordFingerprint("a" * 64),
        NOW + timedelta(minutes=1),
        SkillSemanticReference("actor:operator"),
    )
    evaluation = SkillEvaluationBindingRecord(
        SkillStoreRecordId("evaluation-binding:legacy"),
        publication.identity,
        SkillSemanticReference("evaluation:result"),
        SkillStoreRecordFingerprint("b" * 64),
        NOW + timedelta(minutes=2),
        SkillSemanticReference("actor:operator"),
    )
    bindings = SQLiteSkillBindingStore(factory)
    bindings.append_governance(governance)
    bindings.append_evaluation(evaluation)
    assert (
        bindings.append_governance(governance)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert (
        bindings.append_evaluation(evaluation)
        is SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
    )
    assert bindings.list_governance_for_version(
        publication.identity, SkillStoreQueryLimit(10)
    ) == (governance,)
    assert bindings.list_evaluations_for_version(
        publication.identity, SkillStoreQueryLimit(10)
    ) == (evaluation,)


@pytest.mark.parametrize(
    "value",
    [
        "relative.sqlite3",
        "",
        r"\\server\share\skills.sqlite3",
        r"C:\CON",
        r"C:\safe\..\skills.sqlite3",
    ],
)
def test_database_path_boundary_rejects_implicit_or_network_paths(value: str) -> None:
    with pytest.raises(ValueError):
        SkillSQLiteConfig(Path(value))
