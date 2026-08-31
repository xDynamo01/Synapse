"""Append-only SQLite store for Coding Sessions fencing generations."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .fencing import (
    FencingAuthorityHealth,
    FencingConflictError,
    FencingGenerationFact,
    FencingIntegrityError,
    FencingScope,
    FencingStoreError,
    FencingTransitionRequest,
)
from .identities import (
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionLeaseFactIdentity,
)
from .references import (
    CodingSessionCheckoutReference,
    CodingSessionCorrelationReference,
    CodingSessionRepositoryReference,
    CodingSessionWorktreeReference,
)

FENCING_SQLITE_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE fencing_schema(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL);
CREATE TABLE fencing_history(
 scope_fingerprint TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation >= 1),
 scope_json TEXT NOT NULL, ownership_identity TEXT NOT NULL, authority_identity TEXT NOT NULL,
 authority_version TEXT NOT NULL, occurrence_reference TEXT NOT NULL, correlation TEXT,
 causation_fingerprint TEXT, binding_fingerprint TEXT, transition_fingerprint TEXT NOT NULL,
 idempotency_key TEXT NOT NULL, previous_fact_fingerprint TEXT, fact_fingerprint TEXT NOT NULL UNIQUE,
 PRIMARY KEY(scope_fingerprint, generation), UNIQUE(scope_fingerprint, idempotency_key)
);
CREATE TRIGGER fencing_no_update BEFORE UPDATE ON fencing_history BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER fencing_no_delete BEFORE DELETE ON fencing_history BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""


@dataclass(frozen=True, slots=True)
class FencingSQLiteConfig:
    database_path: str
    timeout_seconds: float = 5.0


class SQLiteFencingGenerationStore:
    def __init__(self, config: FencingSQLiteConfig) -> None:
        self._config = config

    def migrate(self) -> None:
        try:
            with self._connect() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    db.executescript(_SCHEMA)
                    db.execute("INSERT INTO fencing_schema VALUES(1, ?)", (FENCING_SQLITE_SCHEMA_VERSION,))
                    db.execute(f"PRAGMA user_version={FENCING_SQLITE_SCHEMA_VERSION}")
                elif version != FENCING_SQLITE_SCHEMA_VERSION:
                    raise FencingIntegrityError("schema-incompatible")
        except sqlite3.Error as exc:
            raise FencingStoreError("store-unavailable") from exc
        self._verify()

    def transition(self, request: FencingTransitionRequest) -> FencingGenerationFact:
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                scope_key = request.scope.fingerprint.value
                same = db.execute("SELECT * FROM fencing_history WHERE scope_fingerprint=? AND idempotency_key=?", (scope_key, request.idempotency_key)).fetchone()
                if same is not None:
                    fact = self._decode(same)
                    if fact.transition_fingerprint == request.fingerprint:
                        return fact
                    raise FencingConflictError("generation-conflict")
                row = db.execute("SELECT * FROM fencing_history WHERE scope_fingerprint=? ORDER BY generation DESC LIMIT 1", (scope_key,)).fetchone()
                previous = self._decode(row) if row is not None else None
                current_generation = 0 if previous is None else previous.generation.value
                if current_generation != request.expected_generation:
                    raise FencingConflictError("generation-conflict")
                generation = current_generation + 1
                fact = FencingGenerationFact.create(request, generation, None if previous is None else previous.fact_fingerprint)
                db.execute("INSERT INTO fencing_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self._encode(fact))
                return fact
        except FencingConflictError:
            raise
        except (sqlite3.IntegrityError, OverflowError) as exc:
            raise FencingConflictError("generation-conflict") from exc
        except sqlite3.Error as exc:
            raise FencingStoreError("store-unavailable") from exc

    def latest(self, scope: FencingScope) -> FencingGenerationFact | None:
        rows = self.replay(scope)
        return rows[-1] if rows else None

    def replay(self, scope: FencingScope) -> tuple[FencingGenerationFact, ...]:
        try:
            with self._connect() as db:
                rows = db.execute("SELECT * FROM fencing_history WHERE scope_fingerprint=? ORDER BY generation", (scope.fingerprint.value,)).fetchall()
            facts = tuple(self._decode(row) for row in rows)
            self._integrity(facts)
            return facts
        except FencingIntegrityError:
            raise
        except sqlite3.Error as exc:
            raise FencingStoreError("store-unavailable") from exc

    def health(self, scope: FencingScope | None = None) -> FencingAuthorityHealth:
        try:
            self._verify()
            if scope is not None:
                self.replay(scope)
            return FencingAuthorityHealth(True, True, True, True, True)
        except FencingStoreError:
            return FencingAuthorityHealth(False, False, False, False, False)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._config.database_path, timeout=self._config.timeout_seconds)
        db.row_factory = sqlite3.Row
        return db

    def _verify(self) -> None:
        try:
            with self._connect() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                meta = db.execute("SELECT version FROM fencing_schema WHERE singleton=1").fetchone()
            if version != FENCING_SQLITE_SCHEMA_VERSION or meta is None or meta[0] != FENCING_SQLITE_SCHEMA_VERSION:
                raise FencingIntegrityError("schema-incompatible")
        except sqlite3.Error as exc:
            raise FencingStoreError("store-unavailable") from exc

    @staticmethod
    def _integrity(facts: tuple[FencingGenerationFact, ...]) -> None:
        for index, fact in enumerate(facts, 1):
            previous = None if index == 1 else facts[index - 2].fact_fingerprint
            if fact.generation.value != index or fact.previous_fact_fingerprint != previous:
                raise FencingIntegrityError("generation-regression")

    @staticmethod
    def _encode(f: FencingGenerationFact) -> tuple[object, ...]:
        s = f.scope
        def external(
            value: CodingSessionRepositoryReference
            | CodingSessionCheckoutReference
            | CodingSessionWorktreeReference
            | None,
        ) -> list[str] | None:
            if value is None:
                return None
            return [value.producer, value.artifact_type, value.version, value.identity]
        scope_json = json.dumps(
            [s.session.value, external(s.repository), external(s.checkout), external(s.worktree), s.workspace_reference],
            separators=(",", ":"),
        )
        return (s.fingerprint.value, f.generation.value, scope_json, f.ownership_identity.value, f.authority_identity, f.authority_version, f.occurrence_reference, getattr(f.correlation, "value", None), getattr(f.causation_fingerprint, "value", None), getattr(f.binding_fingerprint, "value", None), f.transition_fingerprint.value, f.idempotency_key, getattr(f.previous_fact_fingerprint, "value", None), f.fact_fingerprint.value)

    @staticmethod
    def _decode(row: sqlite3.Row) -> FencingGenerationFact:
        values = json.loads(row["scope_json"])
        scope = FencingScope(
            CodingSessionIdentity(values[0]),
            CodingSessionRepositoryReference(*values[1]) if values[1] else None,
            CodingSessionCheckoutReference(*values[2]) if values[2] else None,
            CodingSessionWorktreeReference(*values[3]) if values[3] else None,
            values[4],
        )
        from .fencing import FencingGeneration
        return FencingGenerationFact(scope, FencingGeneration(row["generation"]), CodingSessionLeaseFactIdentity(row["ownership_identity"]), row["authority_identity"], row["authority_version"], row["occurrence_reference"], CodingSessionCorrelationReference(row["correlation"]) if row["correlation"] else None, CodingSessionFingerprint(row["causation_fingerprint"]) if row["causation_fingerprint"] else None, CodingSessionFingerprint(row["binding_fingerprint"]) if row["binding_fingerprint"] else None, CodingSessionFingerprint(row["transition_fingerprint"]), row["idempotency_key"], CodingSessionFingerprint(row["previous_fact_fingerprint"]) if row["previous_fact_fingerprint"] else None, CodingSessionFingerprint(row["fact_fingerprint"]))
