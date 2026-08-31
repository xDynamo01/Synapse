from __future__ import annotations

import socket
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.test_search_cache_contracts import (
    extraction_entry,
    policy,
    retrieval_entry,
    search_entry,
)
from tests.test_search_contracts import request
from tests.test_search_provider_contracts import invocation, no_results, successful_results
from tests.test_search_results import PROVIDER, result, result_set
from tests.test_search_retrieval_contracts import (
    artifact,
    extracted,
    extraction_request,
    retrieval_request,
)

from synapse.search import (
    CacheEntryId,
    CacheReadStatus,
    CacheRecordRepetition,
    ExtractionAttemptId,
    PersistedPayloadAvailability,
    PolicyReference,
    RestartReferenceAvailability,
    RetrievalAttemptId,
    SearchFingerprint,
    SearchInvocationId,
    SearchPersistedKind,
    SearchPersistenceConflict,
    SearchPersistenceCorrupt,
    SearchPersistenceDraft,
    SearchPersistenceHealthState,
    SearchPersistenceRecordNotFound,
    SearchPersistenceVersionMismatch,
    SearchRecordCompleteness,
    SearchWriteDisposition,
    assess_search_cache,
)
from synapse.search_adapters import (
    SEARCH_SQLITE_MIGRATION_CHECKSUM_V1,
    SEARCH_SQLITE_MIGRATION_ID_V1,
    SearchSQLiteConfig,
    SearchSQLiteDatabase,
    SQLiteExtractionCacheStore,
    SQLiteRetrievalCacheStore,
    SQLiteSearchCacheStore,
    SQLiteSearchMetadataStore,
)

NOW = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)
PERSISTENCE_POLICY = PolicyReference("policy:search-metadata-retention-v1")


@pytest.fixture
def persistence(tmp_path: Path) -> tuple[SearchSQLiteDatabase, SQLiteSearchMetadataStore]:
    database = SearchSQLiteDatabase(SearchSQLiteConfig((tmp_path / "search-metadata.sqlite3").resolve()))
    database.migrate(NOW)
    return database, SQLiteSearchMetadataStore(database)


def draft(
    store: SQLiteSearchMetadataStore,
    kind: SearchPersistedKind,
    fact,
    *,
    stream: str = "search-stream:one",
    lineage: tuple[SearchFingerprint, ...] = (),
    suffix: str | None = None,
    completeness: SearchRecordCompleteness = SearchRecordCompleteness.COMPLETE,
    availability: PersistedPayloadAvailability = PersistedPayloadAvailability.NOT_APPLICABLE,
) -> SearchPersistenceDraft:
    sequence = store.stream_version(stream) + 1
    token = suffix or f"{kind.value}-{sequence}"
    return SearchPersistenceDraft(
        f"search-record:{token}",
        stream,
        sequence,
        sequence - 1,
        f"search-idempotency:{token}",
        kind,
        fact,
        NOW + timedelta(seconds=sequence),
        NOW + timedelta(seconds=sequence + 1),
        PERSISTENCE_POLICY,
        lineage,
        completeness,
        availability,
    )


def test_schema_creation_version_checksum_and_health(persistence) -> None:
    database, _ = persistence
    with database.connection() as connection:
        version = connection.execute(
            "SELECT schema_version FROM search_schema_metadata WHERE singleton=1"
        ).fetchone()[0]
        migration = connection.execute(
            "SELECT migration_id, checksum FROM search_migration_history"
        ).fetchone()
    assert version == 1
    assert tuple(migration) == (
        SEARCH_SQLITE_MIGRATION_ID_V1,
        SEARCH_SQLITE_MIGRATION_CHECKSUM_V1,
    )
    health = database.health()
    assert health.healthy
    assert health.schema_exists and health.schema_version_compatible
    assert health.migration_checksum_valid and health.append_only_protected
    assert health.database_readable and health.integrity_check_passed and health.replay_capable


def test_database_path_is_explicit_absolute_and_controlled(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        SearchSQLiteConfig(Path("derived-from-query.sqlite3"))
    missing_parent = (tmp_path / "missing" / "search.sqlite3").resolve()
    with pytest.raises(ValueError, match="controlled"):
        SearchSQLiteConfig(missing_parent)


def test_append_only_triggers_block_update_and_delete(persistence) -> None:
    database, store = persistence
    record = store.append(draft(store, SearchPersistedKind.SEARCH_REQUEST, request())).record
    with database.connection() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE search_request_records SET stream_id=? WHERE record_id=?",
                ("changed", record.record_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM search_request_records WHERE record_id=?", (record.record_id,)
            )


@pytest.mark.parametrize(
    ("kind", "fact"),
    [
        (SearchPersistedKind.SEARCH_REQUEST, request()),
        (SearchPersistedKind.PROVIDER_INVOCATION, invocation()),
        (SearchPersistedKind.PROVIDER_RESULT, successful_results()),
        (SearchPersistedKind.NORMALIZED_RESULT, result()),
        (SearchPersistedKind.RESULT_SET, result_set()),
        (SearchPersistedKind.RETRIEVAL_REQUEST, retrieval_request()),
        (SearchPersistedKind.RETRIEVED_ARTIFACT, artifact()),
        (SearchPersistedKind.EXTRACTION_REQUEST, extraction_request()),
        (SearchPersistedKind.EXTRACTED_CONTENT, extracted()),
        (SearchPersistedKind.SEARCH_CACHE_ENTRY, search_entry()),
        (SearchPersistedKind.RETRIEVAL_CACHE_ENTRY, retrieval_entry()),
        (SearchPersistedKind.EXTRACTION_CACHE_ENTRY, extraction_entry()),
    ],
)
def test_all_metadata_families_round_trip_exactly(persistence, kind, fact) -> None:
    _, store = persistence
    write = store.append(draft(store, kind, fact))
    exact = store.get_exact(write.record.record_id, write.record.factual_fingerprint)
    assert write.disposition is SearchWriteDisposition.APPENDED
    assert exact.fact == fact
    assert exact.canonical_payload == write.record.canonical_payload
    assert exact.occurred_at == NOW + timedelta(seconds=1)


def test_no_results_provider_outcome_round_trip(persistence) -> None:
    _, store = persistence
    fact = no_results()
    record = store.append(draft(store, SearchPersistedKind.PROVIDER_RESULT, fact)).record
    assert record.fact == fact
    assert record.fact.result_set is not None
    assert not record.fact.result_set.results


def test_kind_mismatch_fails_before_storage(persistence) -> None:
    _, store = persistence
    with pytest.raises(Exception, match="does not correspond"):
        draft(store, SearchPersistedKind.RETRIEVED_ARTIFACT, request())


def test_idempotent_duplicate_and_contradictory_identity(persistence) -> None:
    _, store = persistence
    original = draft(store, SearchPersistedKind.SEARCH_REQUEST, request())
    first = store.append(original)
    repeated = store.append(original)
    assert first.disposition is SearchWriteDisposition.APPENDED
    assert repeated.disposition is SearchWriteDisposition.IDEMPOTENT
    contradictory = replace(original, fact=replace(request(), query="different"))
    with pytest.raises(SearchPersistenceConflict, match="contradictory"):
        store.append(contradictory)


def test_optimistic_sequence_and_missing_lineage_fail_closed(persistence) -> None:
    _, store = persistence
    store.append(draft(store, SearchPersistedKind.SEARCH_REQUEST, request()))
    stale = SearchPersistenceDraft(
        "search-record:stale",
        "search-stream:one",
        1,
        0,
        "search-idempotency:stale",
        SearchPersistedKind.SEARCH_REQUEST,
        request(),
        NOW,
        NOW,
        PERSISTENCE_POLICY,
    )
    with pytest.raises(SearchPersistenceConflict, match="sequence"):
        store.append(stale)
    missing = SearchFingerprint("sha256:" + "f" * 64)
    with pytest.raises(SearchPersistenceConflict, match="lineage"):
        store.append(
            draft(store, SearchPersistedKind.PROVIDER_INVOCATION, invocation(), lineage=(missing,))
        )


def test_retries_remain_distinct_ordered_invocations(persistence) -> None:
    _, store = persistence
    first = invocation()
    second = replace(
        first,
        invocation_id=SearchInvocationId("search-invocation:attempt-2"),
    )
    first_record = store.append(draft(store, SearchPersistedKind.PROVIDER_INVOCATION, first)).record
    second_record = store.append(
        draft(
            store,
            SearchPersistedKind.PROVIDER_INVOCATION,
            second,
            lineage=(first_record.factual_fingerprint,),
        )
    ).record
    history = store.history("search-stream:one")
    assert [item.sequence for item in history] == [1, 2]
    assert history[0].fact != history[1].fact
    assert second_record.lineage_fingerprints == (first_record.factual_fingerprint,)


def test_exact_reads_ranges_and_not_found_are_deterministic(persistence) -> None:
    _, store = persistence
    first = store.append(draft(store, SearchPersistedKind.SEARCH_REQUEST, request())).record
    store.append(
        draft(
            store,
            SearchPersistedKind.PROVIDER_INVOCATION,
            invocation(),
            lineage=(first.factual_fingerprint,),
        )
    )
    assert tuple(item.sequence for item in store.history("search-stream:one", 2, 2)) == (2,)
    with pytest.raises(SearchPersistenceRecordNotFound):
        store.get_exact("search-record:missing", SearchFingerprint("sha256:" + "0" * 64))


def test_restart_replay_preserves_facts_without_reexecution_or_timestamp_changes(
    persistence, monkeypatch
) -> None:
    database, store = persistence
    artifact_record = store.append(
        draft(
            store,
            SearchPersistedKind.RETRIEVED_ARTIFACT,
            artifact(),
            availability=PersistedPayloadAvailability.AVAILABLE_AT_WRITE,
        )
    ).record

    def forbidden_network(*args, **kwargs):
        raise AssertionError("external re-execution attempted")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    restarted = SQLiteSearchMetadataStore(
        SearchSQLiteDatabase(SearchSQLiteConfig(database.database_path))
    )
    replay = restarted.replay("search-stream:one")
    restart = restarted.restart_state("search-stream:one", frozenset())
    assert replay.records[0].fact == artifact_record.fact
    assert replay.records[0].occurred_at == artifact_record.occurred_at
    assert restart.reference_facts[0].availability is RestartReferenceAvailability.UNAVAILABLE
    content_reference = artifact().content_reference
    assert content_reference is not None
    assert restart.reference_facts[0].reference == content_reference.value
    assert replay.complete and not replay.reconciliation_required


def test_restart_can_factually_observe_reference_still_available(persistence) -> None:
    _, store = persistence
    fact = extracted()
    store.append(
        draft(
            store,
            SearchPersistedKind.EXTRACTED_CONTENT,
            fact,
            availability=PersistedPayloadAvailability.AVAILABLE_AT_WRITE,
        )
    )
    assert fact.content_reference is not None
    state = store.restart_state(
        "search-stream:one", frozenset({fact.content_reference.value})
    )
    assert state.reference_facts[0].availability is RestartReferenceAvailability.AVAILABLE


def test_three_cache_ports_remain_separate_append_and_lookup(persistence) -> None:
    _, metadata = persistence
    search_store = SQLiteSearchCacheStore(metadata, PERSISTENCE_POLICY)
    search_value = search_entry()
    assert search_store.append(search_value) is CacheRecordRepetition.FIRST
    assert search_store.append(search_value) is CacheRecordRepetition.IDENTICAL
    assert search_store.lookup(search_value.key) == search_value

    retrieval_store = SQLiteRetrievalCacheStore(metadata, PERSISTENCE_POLICY)
    retrieval_value = retrieval_entry()
    assert retrieval_store.append(retrieval_value) is CacheRecordRepetition.FIRST
    assert retrieval_store.append(retrieval_value) is CacheRecordRepetition.IDENTICAL
    assert retrieval_store.lookup(retrieval_value.key) == retrieval_value

    extraction_store = SQLiteExtractionCacheStore(metadata, PERSISTENCE_POLICY)
    extraction_value = extraction_entry()
    assert extraction_store.append(extraction_value) is CacheRecordRepetition.FIRST
    assert extraction_store.append(extraction_value) is CacheRecordRepetition.IDENTICAL
    assert extraction_store.lookup(extraction_value.key) == extraction_value


def test_cache_lookup_selects_latest_compatible_policy_and_available_reference(
    persistence,
) -> None:
    _, metadata = persistence
    search_store = SQLiteSearchCacheStore(metadata, PERSISTENCE_POLICY)
    admitted = search_entry()
    search_store.append(admitted)
    incompatible = replace(
        admitted,
        entry_id=CacheEntryId("cache-entry:search-incompatible"),
        policy_fingerprint=SearchFingerprint("sha256:" + "7" * 64),
    )
    search_store.append(incompatible)
    assert search_store.lookup(admitted.key) == incompatible
    assert (
        search_store.lookup_compatible(
            admitted.key, admitted.policy_reference, admitted.policy_fingerprint
        )
        == admitted
    )

    retrieval_store = SQLiteRetrievalCacheStore(metadata, PERSISTENCE_POLICY)
    retrieval_value = retrieval_entry()
    retrieval_store.append(retrieval_value)
    reference = retrieval_value.artifact.content_reference
    assert reference is not None
    assert (
        retrieval_store.lookup_compatible(
            retrieval_value.key,
            retrieval_value.policy_reference,
            retrieval_value.policy_fingerprint,
            frozenset(),
        )
        is None
    )
    assert (
        retrieval_store.lookup_compatible(
            retrieval_value.key,
            retrieval_value.policy_reference,
            retrieval_value.policy_fingerprint,
            frozenset({reference.value}),
        )
        == retrieval_value
    )


def test_cache_assessment_is_appended_not_destructively_applied(persistence) -> None:
    _, metadata = persistence
    cache_store = SQLiteSearchCacheStore(metadata, PERSISTENCE_POLICY)
    entry = search_entry()
    cache_store.append(entry)
    assessment = assess_search_cache(
        entry,
        request(),
        PROVIDER,
        policy(),
        entry.expires_at + timedelta(seconds=1),
    )
    assert assessment.status is CacheReadStatus.HIT_STALE
    cache_store.record_assessment(assessment)
    replay = metadata.replay(f"cache-assessment:{entry.entry_id.value}")
    assert replay.records[0].fact == assessment


def test_payload_bytes_and_extracted_text_are_not_automatically_persisted(
    persistence,
) -> None:
    database, store = persistence
    store.append(
        draft(
            store,
            SearchPersistedKind.RETRIEVED_ARTIFACT,
            artifact(),
            availability=PersistedPayloadAvailability.AVAILABLE_AT_WRITE,
        )
    )
    store.append(
        draft(
            store,
            SearchPersistedKind.EXTRACTED_CONTENT,
            replace(
                extracted(),
                extraction_attempt_id=ExtractionAttemptId(
                    "search-extraction-attempt:persistence-2"
                ),
                provenance=replace(
                    extracted().provenance,
                    extraction_attempt_id=ExtractionAttemptId(
                        "search-extraction-attempt:persistence-2"
                    ),
                ),
            ),
            stream="search-stream:two",
            availability=PersistedPayloadAvailability.AVAILABLE_AT_WRITE,
        )
    )
    database_bytes = database.database_path.read_bytes()
    assert b"secret raw web body" not in database_bytes
    assert b"secret extracted text" not in database_bytes
    content_reference = artifact().content_reference
    assert content_reference is not None
    assert content_reference.value.encode() in database_bytes


def test_provider_snippet_retention_is_only_existing_result_metadata(persistence) -> None:
    _, store = persistence
    fact = result()
    record = store.append(draft(store, SearchPersistedKind.NORMALIZED_RESULT, fact)).record
    assert record.fact.provider_snippet == fact.provider_snippet
    assert not hasattr(record.fact, "raw_provider_payload")


def test_malformed_record_is_detected_by_read_and_health(persistence) -> None:
    database, store = persistence
    record = store.append(draft(store, SearchPersistedKind.SEARCH_REQUEST, request())).record
    with database.connection() as connection:
        connection.execute("DROP TRIGGER search_request_records_no_update")
        connection.execute(
            "UPDATE search_request_records SET typed_payload=? WHERE record_id=?",
            ("{malformed", record.record_id),
        )
    with pytest.raises(SearchPersistenceCorrupt, match="checksum"):
        store.get_exact(record.record_id, record.factual_fingerprint)
    assert database.health().state is SearchPersistenceHealthState.MALFORMED_RECORD


def test_incompatible_schema_and_migration_checksum_are_blocking(tmp_path: Path) -> None:
    path = (tmp_path / "version.sqlite3").resolve()
    database = SearchSQLiteDatabase(SearchSQLiteConfig(path))
    database.migrate(NOW)
    with database.connection() as connection:
        connection.execute("DROP TRIGGER search_schema_metadata_no_update")
        connection.execute("UPDATE search_schema_metadata SET schema_version=2")
    with pytest.raises(SearchPersistenceVersionMismatch):
        database.verify()

    other = SearchSQLiteDatabase(SearchSQLiteConfig((tmp_path / "checksum.sqlite3").resolve()))
    other.migrate(NOW)
    with other.connection() as connection:
        connection.execute("DROP TRIGGER search_migration_history_no_update")
        connection.execute("UPDATE search_migration_history SET checksum='wrong'")
    with pytest.raises(SearchPersistenceVersionMismatch, match="checksum"):
        other.verify()


def test_missing_append_only_trigger_is_unhealthy(persistence) -> None:
    database, _ = persistence
    with database.connection() as connection:
        connection.execute("DROP TRIGGER search_result_records_no_delete")
    health = database.health()
    assert health.state is SearchPersistenceHealthState.APPEND_ONLY_PROTECTION_MISSING
    assert not health.healthy and not health.append_only_protected


def test_replay_reports_missing_lineage_without_fabricating_success(persistence) -> None:
    database, store = persistence
    parent = store.append(draft(store, SearchPersistedKind.SEARCH_REQUEST, request())).record
    store.append(
        draft(
            store,
            SearchPersistedKind.PROVIDER_INVOCATION,
            invocation(),
            lineage=(parent.factual_fingerprint,),
        )
    )
    with database.connection() as connection:
        connection.execute("DROP TRIGGER search_request_records_no_delete")
        connection.execute(
            "DELETE FROM search_request_records WHERE record_id=?", (parent.record_id,)
        )
    replay = store.replay("search-stream:one")
    assert replay.missing_sequences == (1,)
    assert replay.missing_lineage_fingerprints == (parent.factual_fingerprint,)
    assert not replay.complete and replay.reconciliation_required


def test_artifact_attempt_id_is_persisted_without_collapsing_retry(persistence) -> None:
    _, store = persistence
    first = artifact()
    second_attempt = RetrievalAttemptId("search-retrieval-attempt:persistence-2")
    second = replace(
        first,
        retrieval_attempt_id=second_attempt,
        provenance=replace(first.provenance, retrieval_attempt_id=second_attempt),
    )
    store.append(draft(store, SearchPersistedKind.RETRIEVED_ARTIFACT, first))
    store.append(draft(store, SearchPersistedKind.RETRIEVED_ARTIFACT, second))
    facts = tuple(item.fact for item in store.history("search-stream:one"))
    assert facts == (first, second)


def test_partial_or_unknown_evidence_replays_as_reconciliation_required(persistence) -> None:
    _, store = persistence
    store.append(
        draft(
            store,
            SearchPersistedKind.SEARCH_REQUEST,
            request(),
            completeness=SearchRecordCompleteness.UNKNOWN,
        )
    )
    replay = store.replay("search-stream:one")
    assert not replay.complete
    assert replay.reconciliation_required
