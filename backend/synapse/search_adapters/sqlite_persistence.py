"""SQLite V1 append-only persistence for Search metadata and factual replay."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Iterator, Mapping, cast

import synapse.search as search
from synapse.search import (
    SEARCH_PERSISTENCE_RECORD_FORMAT_V1,
    SEARCH_PERSISTENCE_SCHEMA_VERSION_V1,
    CachePolicyReference,
    CacheReadAssessmentV1,
    CacheRecordRepetition,
    CacheSemanticKeyV1,
    ExtractionCacheEntryV1,
    ExtractionCachePort,
    PersistableSearchFact,
    PersistedPayloadAvailability,
    PolicyReference,
    RestartReferenceAvailability,
    RetrievalCacheEntryV1,
    RetrievalCachePort,
    SearchCacheEntryV1,
    SearchCachePort,
    SearchFingerprint,
    SearchPersistedKind,
    SearchPersistedRecord,
    SearchPersistenceConflict,
    SearchPersistenceCorrupt,
    SearchPersistenceDraft,
    SearchPersistenceHealth,
    SearchPersistenceHealthState,
    SearchPersistenceRecordNotFound,
    SearchPersistenceUnavailable,
    SearchPersistenceVersionMismatch,
    SearchRecordCompleteness,
    SearchReplay,
    SearchRestartReferenceFact,
    SearchRestartState,
    SearchWriteDisposition,
    SearchWriteResult,
    canonical_json,
)

SEARCH_SQLITE_MIGRATION_ID_V1 = "search-metadata-persistence-v1"

_TABLES = {
    SearchPersistedKind.SEARCH_REQUEST: "search_request_records",
    SearchPersistedKind.PROVIDER_INVOCATION: "search_provider_records",
    SearchPersistedKind.PROVIDER_RESULT: "search_provider_records",
    SearchPersistedKind.NORMALIZED_RESULT: "search_result_records",
    SearchPersistedKind.RESULT_SET: "search_result_records",
    SearchPersistedKind.RETRIEVAL_REQUEST: "search_retrieval_records",
    SearchPersistedKind.RETRIEVED_ARTIFACT: "search_retrieval_records",
    SearchPersistedKind.EXTRACTION_REQUEST: "search_extraction_records",
    SearchPersistedKind.EXTRACTED_CONTENT: "search_extraction_records",
    SearchPersistedKind.SEARCH_CACHE_ENTRY: "search_cache_records",
    SearchPersistedKind.RETRIEVAL_CACHE_ENTRY: "retrieval_cache_records",
    SearchPersistedKind.EXTRACTION_CACHE_ENTRY: "extraction_cache_records",
    SearchPersistedKind.CACHE_ASSESSMENT: "search_cache_assessment_records",
}
_UNIQUE_TABLES = tuple(sorted(set(_TABLES.values())))
_BASE_SCHEMA = """
CREATE TABLE search_schema_metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1), schema_version INTEGER NOT NULL
);
CREATE TABLE search_migration_history (
    migration_id TEXT PRIMARY KEY, from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE TRIGGER search_schema_metadata_no_update BEFORE UPDATE ON search_schema_metadata
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER search_schema_metadata_no_delete BEFORE DELETE ON search_schema_metadata
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER search_migration_history_no_update BEFORE UPDATE ON search_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER search_migration_history_no_delete BEFORE DELETE ON search_migration_history
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_RECORD_SCHEMA = """
CREATE TABLE {table} (
    record_id TEXT PRIMARY KEY,
    factual_fingerprint TEXT NOT NULL UNIQUE,
    stream_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence >= 1),
    idempotency_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    typed_payload TEXT NOT NULL,
    canonical_payload TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    policy_reference TEXT NOT NULL,
    lineage TEXT NOT NULL,
    completeness TEXT NOT NULL,
    payload_availability TEXT NOT NULL,
    format_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    UNIQUE(stream_id, sequence)
);
CREATE INDEX {table}_stream_sequence ON {table}(stream_id, sequence);
CREATE INDEX {table}_kind_stream ON {table}(kind, stream_id, sequence);
CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""
_V1_SQL = _BASE_SCHEMA + "".join(
    _RECORD_SCHEMA.format(table=table) for table in _UNIQUE_TABLES
)
SEARCH_SQLITE_MIGRATION_CHECKSUM_V1 = hashlib.sha256(
    f"id={SEARCH_SQLITE_MIGRATION_ID_V1}\nfrom=0\nto=1\n{' '.join(_V1_SQL.split())}".encode()
).hexdigest()
_RECORD_COLUMNS = (
    "record_id",
    "factual_fingerprint",
    "stream_id",
    "sequence",
    "idempotency_key",
    "kind",
    "typed_payload",
    "canonical_payload",
    "payload_checksum",
    "occurred_at",
    "observed_at",
    "policy_reference",
    "lineage",
    "completeness",
    "payload_availability",
    "format_version",
    "schema_version",
)


@dataclass(frozen=True, slots=True)
class SearchSQLiteConfig:
    database_path: Path
    busy_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        path = self.database_path
        if (
            not isinstance(path, Path)
            or not path.is_absolute()
            or str(path).startswith(("\\\\", "//"))
            or ".." in path.parts
            or path.exists() and path.is_dir()
            or not path.parent.exists()
            or path.parent.is_symlink()
        ):
            raise ValueError("Search database path must be an absolute controlled file path")
        if (
            isinstance(self.busy_timeout_ms, bool)
            or not isinstance(self.busy_timeout_ms, int)
            or not 1 <= self.busy_timeout_ms <= 60_000
        ):
            raise ValueError("Search database timeout is invalid")


@contextmanager
def _existing(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    yield connection


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _checksum(value: str) -> SearchFingerprint:
    return SearchFingerprint("sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest())


def _type_registry() -> dict[str, type[object]]:
    registry: dict[str, type[object]] = {}
    for name in search.__all__:
        candidate = getattr(search, name)
        if isinstance(candidate, type) and (
            is_dataclass(candidate) or issubclass(candidate, Enum)
        ):
            registry[candidate.__name__] = candidate
    return registry


_TYPE_REGISTRY = _type_registry()


def _encode(value: object) -> object:
    if isinstance(value, datetime):
        return {"__datetime__": _timestamp(value)}
    if isinstance(value, Enum):
        return {"__enum__": type(value).__name__, "value": value.value}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__name__,
            "fields": {item.name: _encode(getattr(value, item.name)) for item in fields(value)},
        }
    if isinstance(value, tuple):
        return {"__tuple__": [_encode(item) for item in value]}
    if isinstance(value, Mapping):
        return {
            "__mapping__": [
                [_encode(key), _encode(item)]
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            ]
        }
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise SearchPersistenceCorrupt("unsupported Search persistence value")


def _decode(value: object) -> object:
    if isinstance(value, list):
        raise SearchPersistenceCorrupt("untyped Search persistence sequence")
    if not isinstance(value, dict):
        return value
    if set(value) == {"__datetime__"}:
        raw = value["__datetime__"]
        if not isinstance(raw, str):
            raise SearchPersistenceCorrupt("invalid persisted datetime")
        return datetime.fromisoformat(raw)
    if set(value) == {"__enum__", "value"}:
        name, raw = value["__enum__"], value["value"]
        candidate = _TYPE_REGISTRY.get(str(name))
        if candidate is None or not issubclass(candidate, Enum):
            raise SearchPersistenceCorrupt("unknown persisted enum")
        try:
            return candidate(raw)
        except (TypeError, ValueError) as exc:
            raise SearchPersistenceCorrupt("invalid persisted enum value") from exc
    if set(value) == {"__tuple__"}:
        items = value["__tuple__"]
        if not isinstance(items, list):
            raise SearchPersistenceCorrupt("invalid persisted tuple")
        return tuple(_decode(item) for item in items)
    if set(value) == {"__mapping__"}:
        items = value["__mapping__"]
        if not isinstance(items, list):
            raise SearchPersistenceCorrupt("invalid persisted mapping")
        decoded: dict[object, object] = {}
        for pair in items:
            if not isinstance(pair, list) or len(pair) != 2:
                raise SearchPersistenceCorrupt("invalid persisted mapping entry")
            decoded[_decode(pair[0])] = _decode(pair[1])
        return decoded
    if set(value) == {"__type__", "fields"}:
        name, raw_fields = value["__type__"], value["fields"]
        candidate = _TYPE_REGISTRY.get(str(name))
        if candidate is None or not is_dataclass(candidate) or not isinstance(raw_fields, dict):
            raise SearchPersistenceCorrupt("unknown persisted contract type")
        try:
            return candidate(**{str(key): _decode(item) for key, item in raw_fields.items()})
        except (TypeError, ValueError) as exc:
            raise SearchPersistenceCorrupt("malformed persisted Search contract") from exc
    raise SearchPersistenceCorrupt("malformed persisted Search value")


class SearchSQLiteDatabase:
    def __init__(self, config: SearchSQLiteConfig) -> None:
        self._config = config

    @property
    def database_path(self) -> Path:
        return self._config.database_path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                str(self.database_path),
                timeout=self._config.busy_timeout_ms / 1_000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.enable_load_extension(False)
        except (OSError, sqlite3.Error) as exc:
            raise SearchPersistenceUnavailable() from exc
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self, applied_at: datetime) -> None:
        if applied_at.tzinfo is None or applied_at.utcoffset() is None:
            raise ValueError("migration occurrence must be timezone-aware")
        with self.connection() as connection:
            if not self._tables(connection):
                try:
                    connection.executescript("BEGIN EXCLUSIVE;\n" + _V1_SQL)
                    connection.execute(
                        "INSERT INTO search_schema_metadata VALUES (1, ?)",
                        (SEARCH_PERSISTENCE_SCHEMA_VERSION_V1,),
                    )
                    connection.execute(
                        "INSERT INTO search_migration_history VALUES (?, 0, ?, ?, ?)",
                        (
                            SEARCH_SQLITE_MIGRATION_ID_V1,
                            SEARCH_PERSISTENCE_SCHEMA_VERSION_V1,
                            SEARCH_SQLITE_MIGRATION_CHECKSUM_V1,
                            _timestamp(applied_at),
                        ),
                    )
                    connection.commit()
                except sqlite3.Error as exc:
                    connection.rollback()
                    raise SearchPersistenceCorrupt("Search migration failed") from exc
            self.verify(connection)

    def verify(self, connection: sqlite3.Connection | None = None) -> None:
        manager = self.connection() if connection is None else _existing(connection)
        with manager as active:
            expected_tables = {"search_schema_metadata", "search_migration_history", *_UNIQUE_TABLES}
            if self._tables(active) != expected_tables:
                raise SearchPersistenceCorrupt("Search schema is incomplete")
            version = active.execute(
                "SELECT schema_version FROM search_schema_metadata WHERE singleton=1"
            ).fetchone()
            if version is None or version[0] != SEARCH_PERSISTENCE_SCHEMA_VERSION_V1:
                raise SearchPersistenceVersionMismatch()
            migration = active.execute(
                "SELECT from_version, to_version, checksum FROM search_migration_history WHERE migration_id=?",
                (SEARCH_SQLITE_MIGRATION_ID_V1,),
            ).fetchone()
            if migration is None or tuple(migration) != (
                0,
                SEARCH_PERSISTENCE_SCHEMA_VERSION_V1,
                SEARCH_SQLITE_MIGRATION_CHECKSUM_V1,
            ):
                raise SearchPersistenceVersionMismatch("Search migration checksum mismatch")
            objects = active.execute(
                "SELECT type, name FROM sqlite_master WHERE type IN ('index', 'trigger')"
            ).fetchall()
            indexes = {row[1] for row in objects if row[0] == "index" and not row[1].startswith("sqlite_")}
            triggers = {row[1] for row in objects if row[0] == "trigger"}
            expected_indexes = {
                f"{table}_{suffix}"
                for table in _UNIQUE_TABLES
                for suffix in ("stream_sequence", "kind_stream")
            }
            expected_triggers = {
                f"{table}_no_{operation}"
                for table in _UNIQUE_TABLES
                for operation in ("update", "delete")
            } | {
                "search_schema_metadata_no_update",
                "search_schema_metadata_no_delete",
                "search_migration_history_no_update",
                "search_migration_history_no_delete",
            }
            if indexes != expected_indexes or triggers != expected_triggers:
                raise SearchPersistenceCorrupt("Search append-only protections are incomplete")
            for table in _UNIQUE_TABLES:
                columns = tuple(row[1] for row in active.execute(f"PRAGMA table_info({table})"))
                if columns != _RECORD_COLUMNS:
                    raise SearchPersistenceCorrupt("Search record schema is invalid")
            if active.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SearchPersistenceCorrupt("Search database integrity check failed")

    def health(self) -> SearchPersistenceHealth:
        try:
            with self.connection() as connection:
                tables = self._tables(connection)
                schema_exists = bool(tables)
                if not schema_exists:
                    return SearchPersistenceHealth(SearchPersistenceHealthState.SCHEMA_MISMATCH, False, False, False, False, True, False, False)
                version = connection.execute(
                    "SELECT schema_version FROM search_schema_metadata WHERE singleton=1"
                ).fetchone()
                version_ok = bool(version and version[0] == SEARCH_PERSISTENCE_SCHEMA_VERSION_V1)
                migration = connection.execute(
                    "SELECT checksum FROM search_migration_history WHERE migration_id=?",
                    (SEARCH_SQLITE_MIGRATION_ID_V1,),
                ).fetchone()
                migration_ok = bool(migration and migration[0] == SEARCH_SQLITE_MIGRATION_CHECKSUM_V1)
                trigger_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='trigger'"
                    )
                }
                expected_trigger_names = {
                    f"{table}_no_{operation}"
                    for table in _UNIQUE_TABLES
                    for operation in ("update", "delete")
                } | {
                    "search_schema_metadata_no_update",
                    "search_schema_metadata_no_delete",
                    "search_migration_history_no_update",
                    "search_migration_history_no_delete",
                }
                protected = trigger_names == expected_trigger_names
                integrity_ok = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                state = SearchPersistenceHealthState.HEALTHY
                if not version_ok:
                    state = SearchPersistenceHealthState.SCHEMA_MISMATCH
                elif not migration_ok:
                    state = SearchPersistenceHealthState.MIGRATION_MISMATCH
                elif not protected:
                    state = SearchPersistenceHealthState.APPEND_ONLY_PROTECTION_MISSING
                elif not integrity_ok:
                    state = SearchPersistenceHealthState.INTEGRITY_FAILED
                for table in _UNIQUE_TABLES:
                    for row in connection.execute(
                        f"SELECT typed_payload, payload_checksum FROM {table}"
                    ):
                        if _checksum(row[0]).value != row[1]:
                            state = SearchPersistenceHealthState.MALFORMED_RECORD
                            break
                        try:
                            _decode(json.loads(row[0]))
                        except (json.JSONDecodeError, SearchPersistenceCorrupt):
                            state = SearchPersistenceHealthState.MALFORMED_RECORD
                            break
                    if state is SearchPersistenceHealthState.MALFORMED_RECORD:
                        break
                return SearchPersistenceHealth(state, True, version_ok, migration_ok, protected, True, integrity_ok, state is SearchPersistenceHealthState.HEALTHY)
        except sqlite3.DatabaseError:
            return SearchPersistenceHealth(SearchPersistenceHealthState.INTEGRITY_FAILED, False, False, False, False, False, False, False)
        except (OSError, SearchPersistenceUnavailable):
            return SearchPersistenceHealth(SearchPersistenceHealthState.UNAVAILABLE, False, False, False, False, False, False, False)

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not str(row[0]).startswith("sqlite_")
        }


class SQLiteSearchMetadataStore:
    def __init__(self, database: SearchSQLiteDatabase) -> None:
        self._database = database

    def stream_version(self, stream_id: str) -> int:
        with self._database.connection() as connection:
            return max(
                int(
                    connection.execute(
                        f"SELECT COALESCE(MAX(sequence), 0) FROM {table} WHERE stream_id=?",
                        (stream_id,),
                    ).fetchone()[0]
                )
                for table in _UNIQUE_TABLES
            )

    def append(self, draft: SearchPersistenceDraft) -> SearchWriteResult:
        table = _TABLES[draft.kind]
        typed_payload = canonical_json(_encode(draft.fact))
        canonical_payload = canonical_json(draft.fact)
        payload_checksum = _checksum(typed_payload)
        values = (
            draft.record_id,
            draft.factual_fingerprint.value,
            draft.stream_id,
            draft.sequence,
            draft.idempotency_key,
            draft.kind.value,
            typed_payload,
            canonical_payload,
            payload_checksum.value,
            _timestamp(draft.occurred_at),
            _timestamp(draft.observed_at),
            draft.policy_reference.value,
            canonical_json(draft.lineage_fingerprints),
            draft.completeness.value,
            draft.payload_availability.value,
            SEARCH_PERSISTENCE_RECORD_FORMAT_V1,
            SEARCH_PERSISTENCE_SCHEMA_VERSION_V1,
        )
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._find_identity(connection, draft.record_id, draft.idempotency_key)
            if existing:
                if len(existing) == 1 and existing[0]["factual_fingerprint"] == draft.factual_fingerprint.value:
                    connection.rollback()
                    return SearchWriteResult(SearchWriteDisposition.IDEMPOTENT, self._decode(connection, existing[0]))
                connection.rollback()
                raise SearchPersistenceConflict("contradictory Search persistence identity")
            current = self._stream_version(connection, draft.stream_id)
            if current != draft.expected_stream_version:
                connection.rollback()
                raise SearchPersistenceConflict("Search persistence optimistic sequence conflict")
            known = self._known_fingerprints(connection)
            if any(item.value not in known for item in draft.lineage_fingerprints):
                connection.rollback()
                raise SearchPersistenceConflict("Search persistence lineage is missing")
            try:
                connection.execute(
                    f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise SearchPersistenceConflict("Search persistence append conflict") from exc
        return SearchWriteResult(
            SearchWriteDisposition.APPENDED,
            self.get_exact(draft.record_id, draft.factual_fingerprint),
        )

    def get_exact(self, record_id: str, fingerprint: SearchFingerprint) -> SearchPersistedRecord:
        with self._database.connection() as connection:
            rows = [
                row
                for table in _UNIQUE_TABLES
                if (
                    row := connection.execute(
                        f"SELECT * FROM {table} WHERE record_id=? AND factual_fingerprint=?",
                        (record_id, fingerprint.value),
                    ).fetchone()
                )
                is not None
            ]
            if len(rows) != 1:
                raise SearchPersistenceRecordNotFound()
            return self._decode(connection, rows[0])

    def history(
        self, stream_id: str, start_sequence: int = 1, end_sequence: int | None = None
    ) -> tuple[SearchPersistedRecord, ...]:
        if start_sequence < 1 or end_sequence is not None and end_sequence < start_sequence:
            raise SearchPersistenceConflict("Search persistence history range is invalid")
        end = end_sequence if end_sequence is not None else 2**63 - 1
        with self._database.connection() as connection:
            rows = connection.execute(
                " UNION ALL ".join(
                    f"SELECT * FROM {table} WHERE stream_id=? AND sequence BETWEEN ? AND ?"
                    for table in _UNIQUE_TABLES
                )
                + " ORDER BY sequence, record_id",
                tuple(value for _ in _UNIQUE_TABLES for value in (stream_id, start_sequence, end)),
            ).fetchall()
            return tuple(self._decode(connection, row) for row in rows)

    def replay(self, stream_id: str) -> SearchReplay:
        records = self.history(stream_id)
        sequences = {record.sequence for record in records}
        missing_sequences = tuple(
            index for index in range(1, max(sequences, default=0) + 1) if index not in sequences
        )
        missing_lineage = tuple(
            sorted(
                {item for record in records for item in record.missing_lineage_fingerprints},
                key=lambda item: item.value,
            )
        )
        complete = (
            not missing_sequences
            and not missing_lineage
            and all(record.completeness is SearchRecordCompleteness.COMPLETE for record in records)
        )
        return SearchReplay(
            stream_id,
            records,
            missing_sequences,
            missing_lineage,
            complete,
            not complete,
        )

    def restart_state(
        self, stream_id: str, available_references: frozenset[str]
    ) -> SearchRestartState:
        replay = self.replay(stream_id)
        reference_facts = tuple(
            SearchRestartReferenceFact(
                record.record_id,
                reference,
                RestartReferenceAvailability.AVAILABLE
                if reference in available_references
                else RestartReferenceAvailability.UNAVAILABLE,
            )
            for record in replay.records
            if (reference := _content_reference(record.fact)) is not None
        )
        return SearchRestartState(replay, reference_facts)

    def latest_cache_entry(
        self,
        kind: SearchPersistedKind,
        key: CacheSemanticKeyV1,
        *,
        policy_reference: CachePolicyReference | None = None,
        policy_fingerprint: SearchFingerprint | None = None,
        available_references: frozenset[str] | None = None,
    ) -> SearchCacheEntryV1 | RetrievalCacheEntryV1 | ExtractionCacheEntryV1 | None:
        table = _TABLES[kind]
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE kind=? ORDER BY sequence DESC, record_id DESC",
                (kind.value,),
            ).fetchall()
            for row in rows:
                record = self._decode(connection, row)
                fact = record.fact
                if not isinstance(
                    fact,
                    (SearchCacheEntryV1, RetrievalCacheEntryV1, ExtractionCacheEntryV1),
                ) or fact.key != key:
                    continue
                if policy_reference is not None and fact.policy_reference != policy_reference:
                    continue
                if policy_fingerprint is not None and fact.policy_fingerprint != policy_fingerprint:
                    continue
                reference = _content_reference(fact)
                if (
                    available_references is not None
                    and reference is not None
                    and reference not in available_references
                ):
                    continue
                return fact
        return None

    @staticmethod
    def _find_identity(
        connection: sqlite3.Connection, record_id: str, idempotency_key: str
    ) -> list[sqlite3.Row]:
        rows: list[sqlite3.Row] = []
        for table in _UNIQUE_TABLES:
            rows.extend(
                connection.execute(
                    f"SELECT * FROM {table} WHERE record_id=? OR idempotency_key=?",
                    (record_id, idempotency_key),
                ).fetchall()
            )
        return rows

    @staticmethod
    def _stream_version(connection: sqlite3.Connection, stream_id: str) -> int:
        return max(
            int(
                connection.execute(
                    f"SELECT COALESCE(MAX(sequence), 0) FROM {table} WHERE stream_id=?",
                    (stream_id,),
                ).fetchone()[0]
            )
            for table in _UNIQUE_TABLES
        )

    @staticmethod
    def _known_fingerprints(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for table in _UNIQUE_TABLES
            for row in connection.execute(f"SELECT factual_fingerprint FROM {table}")
        }

    def _decode(self, connection: sqlite3.Connection, row: sqlite3.Row) -> SearchPersistedRecord:
        if (
            row["format_version"] != SEARCH_PERSISTENCE_RECORD_FORMAT_V1
            or row["schema_version"] != SEARCH_PERSISTENCE_SCHEMA_VERSION_V1
        ):
            raise SearchPersistenceVersionMismatch("Search record version mismatch")
        if _checksum(row["typed_payload"]).value != row["payload_checksum"]:
            raise SearchPersistenceCorrupt("Search persisted payload checksum mismatch")
        try:
            kind = SearchPersistedKind(row["kind"])
            fact = _decode(json.loads(row["typed_payload"]))
            if not isinstance(fact, _persisted_type(kind)):
                raise SearchPersistenceCorrupt("Search persisted kind mismatch")
            if canonical_json(fact) != row["canonical_payload"]:
                raise SearchPersistenceCorrupt("Search canonical round-trip mismatch")
            lineage = tuple(SearchFingerprint(item) for item in json.loads(row["lineage"]))
            occurred_at = datetime.fromisoformat(row["occurred_at"])
            observed_at = datetime.fromisoformat(row["observed_at"])
            policy_reference = PolicyReference(row["policy_reference"])
            completeness = SearchRecordCompleteness(row["completeness"])
            availability = PersistedPayloadAvailability(row["payload_availability"])
            draft = SearchPersistenceDraft(
                row["record_id"],
                row["stream_id"],
                row["sequence"],
                row["sequence"] - 1,
                row["idempotency_key"],
                kind,
                cast(PersistableSearchFact, fact),
                occurred_at,
                observed_at,
                policy_reference,
                lineage,
                completeness,
                availability,
            )
            if draft.factual_fingerprint.value != row["factual_fingerprint"]:
                raise SearchPersistenceCorrupt("Search factual fingerprint mismatch")
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, SearchPersistenceCorrupt):
                raise
            raise SearchPersistenceCorrupt("malformed Search persisted record") from exc
        known = self._known_fingerprints(connection)
        missing = tuple(item for item in lineage if item.value not in known)
        return SearchPersistedRecord(
            row["record_id"],
            row["stream_id"],
            row["sequence"],
            row["idempotency_key"],
            kind,
            cast(PersistableSearchFact, fact),
            SearchFingerprint(row["factual_fingerprint"]),
            row["canonical_payload"],
            SearchFingerprint(row["payload_checksum"]),
            occurred_at,
            observed_at,
            policy_reference,
            lineage,
            missing,
            completeness,
            availability,
        )


def _persisted_type(kind: SearchPersistedKind) -> type[object]:
    names = {
        SearchPersistedKind.SEARCH_REQUEST: "SearchRequestV1",
        SearchPersistedKind.PROVIDER_INVOCATION: "SearchProviderInvocationV1",
        SearchPersistedKind.PROVIDER_RESULT: "SearchProviderResultV1",
        SearchPersistedKind.NORMALIZED_RESULT: "NormalizedSearchResultV1",
        SearchPersistedKind.RESULT_SET: "SearchResultSetV1",
        SearchPersistedKind.RETRIEVAL_REQUEST: "RetrievalRequestV1",
        SearchPersistedKind.RETRIEVED_ARTIFACT: "RetrievedArtifactV1",
        SearchPersistedKind.EXTRACTION_REQUEST: "ExtractionRequestV1",
        SearchPersistedKind.EXTRACTED_CONTENT: "ExtractedContentV1",
        SearchPersistedKind.SEARCH_CACHE_ENTRY: "SearchCacheEntryV1",
        SearchPersistedKind.RETRIEVAL_CACHE_ENTRY: "RetrievalCacheEntryV1",
        SearchPersistedKind.EXTRACTION_CACHE_ENTRY: "ExtractionCacheEntryV1",
        SearchPersistedKind.CACHE_ASSESSMENT: "CacheReadAssessmentV1",
    }
    return _TYPE_REGISTRY[names[kind]]


def _content_reference(fact: PersistableSearchFact) -> str | None:
    if isinstance(fact, search.RetrievedArtifactV1):
        return fact.content_reference.value if fact.content_reference else None
    if isinstance(fact, search.ExtractedContentV1):
        return fact.content_reference.value if fact.content_reference else None
    if isinstance(fact, RetrievalCacheEntryV1):
        artifact_reference = fact.artifact.content_reference
        return artifact_reference.value if artifact_reference else None
    if isinstance(fact, ExtractionCacheEntryV1):
        extracted_reference = fact.extracted_content.content_reference
        return extracted_reference.value if extracted_reference else None
    return None


class _SQLiteCacheStore:
    kind: SearchPersistedKind
    entry_type: type[object]

    def __init__(
        self,
        store: SQLiteSearchMetadataStore,
        persistence_policy: PolicyReference,
    ) -> None:
        self._store = store
        self._persistence_policy = persistence_policy

    def _append(self, entry: object) -> CacheRecordRepetition:
        if not isinstance(entry, self.entry_type):
            raise SearchPersistenceConflict("cache entry belongs to another namespace")
        typed_entry = cast(SearchCacheEntryV1 | RetrievalCacheEntryV1 | ExtractionCacheEntryV1, entry)
        existing = self._store.latest_cache_entry(self.kind, typed_entry.key)
        if existing is not None:
            if existing == typed_entry:
                return CacheRecordRepetition.IDENTICAL
            if existing.entry_id == typed_entry.entry_id:
                raise SearchPersistenceConflict("contradictory cache entry identity")
        stream_id = f"cache:{typed_entry.key.namespace.value}:{typed_entry.key.fingerprint.value}"
        sequence = self._store.stream_version(stream_id) + 1
        result = self._store.append(
            SearchPersistenceDraft(
                f"cache-record:{typed_entry.entry_id.value}",
                stream_id,
                sequence,
                sequence - 1,
                f"cache-idempotency:{typed_entry.entry_id.value}",
                self.kind,
                typed_entry,
                typed_entry.written_at,
                typed_entry.written_at,
                self._persistence_policy,
                payload_availability=PersistedPayloadAvailability.UNKNOWN,
            )
        )
        return CacheRecordRepetition.FIRST if result.disposition is SearchWriteDisposition.APPENDED else CacheRecordRepetition.IDENTICAL

    def _lookup(self, key: CacheSemanticKeyV1) -> object | None:
        return self._store.latest_cache_entry(self.kind, key)

    def _lookup_compatible(
        self,
        key: CacheSemanticKeyV1,
        policy_reference: CachePolicyReference,
        policy_fingerprint: SearchFingerprint,
        available_references: frozenset[str],
    ) -> object | None:
        return self._store.latest_cache_entry(
            self.kind,
            key,
            policy_reference=policy_reference,
            policy_fingerprint=policy_fingerprint,
            available_references=available_references,
        )

    def record_assessment(self, assessment: CacheReadAssessmentV1) -> None:
        if assessment.entry_id is None:
            raise SearchPersistenceConflict("cache assessment has no entry identity")
        stream_id = f"cache-assessment:{assessment.entry_id.value}"
        sequence = self._store.stream_version(stream_id) + 1
        self._store.append(
            SearchPersistenceDraft(
                f"cache-assessment-record:{assessment.entry_id.value}:{sequence}",
                stream_id,
                sequence,
                sequence - 1,
                f"cache-assessment-idempotency:{assessment.entry_id.value}:{sequence}",
                SearchPersistedKind.CACHE_ASSESSMENT,
                assessment,
                assessment.read_at,
                assessment.read_at,
                self._persistence_policy,
            )
        )


class SQLiteSearchCacheStore(_SQLiteCacheStore, SearchCachePort):
    kind = SearchPersistedKind.SEARCH_CACHE_ENTRY
    entry_type = SearchCacheEntryV1

    def lookup(self, key: CacheSemanticKeyV1) -> SearchCacheEntryV1 | None:
        value = self._lookup(key)
        return cast(SearchCacheEntryV1 | None, value)

    def append(self, entry: SearchCacheEntryV1) -> CacheRecordRepetition:
        return self._append(entry)

    def lookup_compatible(
        self,
        key: CacheSemanticKeyV1,
        policy_reference: CachePolicyReference,
        policy_fingerprint: SearchFingerprint,
    ) -> SearchCacheEntryV1 | None:
        return cast(
            SearchCacheEntryV1 | None,
            self._lookup_compatible(
                key, policy_reference, policy_fingerprint, frozenset()
            ),
        )


class SQLiteRetrievalCacheStore(_SQLiteCacheStore, RetrievalCachePort):
    kind = SearchPersistedKind.RETRIEVAL_CACHE_ENTRY
    entry_type = RetrievalCacheEntryV1

    def lookup(self, key: CacheSemanticKeyV1) -> RetrievalCacheEntryV1 | None:
        value = self._lookup(key)
        return cast(RetrievalCacheEntryV1 | None, value)

    def append(self, entry: RetrievalCacheEntryV1) -> CacheRecordRepetition:
        return self._append(entry)

    def lookup_compatible(
        self,
        key: CacheSemanticKeyV1,
        policy_reference: CachePolicyReference,
        policy_fingerprint: SearchFingerprint,
        available_references: frozenset[str],
    ) -> RetrievalCacheEntryV1 | None:
        return cast(
            RetrievalCacheEntryV1 | None,
            self._lookup_compatible(
                key, policy_reference, policy_fingerprint, available_references
            ),
        )


class SQLiteExtractionCacheStore(_SQLiteCacheStore, ExtractionCachePort):
    kind = SearchPersistedKind.EXTRACTION_CACHE_ENTRY
    entry_type = ExtractionCacheEntryV1

    def lookup(self, key: CacheSemanticKeyV1) -> ExtractionCacheEntryV1 | None:
        value = self._lookup(key)
        return cast(ExtractionCacheEntryV1 | None, value)

    def append(self, entry: ExtractionCacheEntryV1) -> CacheRecordRepetition:
        return self._append(entry)

    def lookup_compatible(
        self,
        key: CacheSemanticKeyV1,
        policy_reference: CachePolicyReference,
        policy_fingerprint: SearchFingerprint,
        available_references: frozenset[str],
    ) -> ExtractionCacheEntryV1 | None:
        return cast(
            ExtractionCacheEntryV1 | None,
            self._lookup_compatible(
                key, policy_reference, policy_fingerprint, available_references
            ),
        )
