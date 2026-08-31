from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from .codec import canonical_timestamp
from .connection import SkillSQLiteConnectionFactory
from .errors import (
    SkillPersistenceDatabaseCorrupt,
    SkillPersistenceMigrationChecksumMismatch,
    SkillPersistenceMigrationFailed,
    SkillPersistenceMigrationRequired,
    SkillPersistenceSchemaUnsupported,
)


class SkillPersistenceSchemaVersion(IntEnum):
    V1 = 1


_RECORD_TABLES = (
    "publications",
    "lifecycle_records",
    "installation_records",
    "installation_terminations",
    "assignments",
    "assignment_terminations",
    "leases",
    "lease_terminations",
    "legacy_governance_bindings",
    "legacy_evaluation_bindings",
    "governance_bindings",
    "intelligence_bindings",
    "private_eval_bindings",
)
_EXPECTED_TABLES = frozenset(
    {"skill_schema_metadata", "skill_migration_history", *_RECORD_TABLES}
)
_EXPECTED_INDEXES = frozenset(
    {
        "lifecycle_by_version",
        "installations_by_version",
        "installation_ends_by_version",
        "assignments_by_subject",
        "assignment_ends_by_subject",
        "leases_by_agent",
        "leases_by_task",
        "leases_by_version",
        "governance_by_version",
        "intelligence_by_version",
        "private_eval_by_version",
    }
)
_EXPECTED_TRIGGERS = frozenset(
    f"{table}_no_{operation}"
    for table in _RECORD_TABLES
    for operation in ("update", "delete")
)
_EXPECTED_COLUMNS = {
    "skill_schema_metadata": ("singleton", "schema_version"),
    "skill_migration_history": (
        "migration_id",
        "from_version",
        "to_version",
        "checksum",
        "applied_at",
    ),
    "publications": (
        "exact_identity",
        "skill_id",
        "version",
        "occurred_at",
        "payload",
    ),
    "lifecycle_records": (
        "record_id",
        "exact_identity",
        "record_kind",
        "occurred_at",
        "parent_installation_id",
        "payload",
    ),
    "installation_records": (
        "record_id",
        "exact_identity",
        "occurred_at",
        "payload",
    ),
    "installation_terminations": (
        "record_id",
        "installation_id",
        "exact_identity",
        "occurred_at",
        "payload",
    ),
    "assignments": (
        "record_id",
        "exact_identity",
        "subject_ref",
        "occurred_at",
        "payload",
    ),
    "assignment_terminations": (
        "record_id",
        "assignment_id",
        "exact_identity",
        "subject_ref",
        "occurred_at",
        "payload",
    ),
    "leases": (
        "record_id",
        "assignment_id",
        "exact_identity",
        "agent_ref",
        "task_ref",
        "occurred_at",
        "payload",
    ),
    "lease_terminations": (
        "record_id",
        "lease_id",
        "exact_identity",
        "agent_ref",
        "task_ref",
        "occurred_at",
        "payload",
    ),
    "legacy_governance_bindings": (
        "record_id",
        "exact_identity",
        "occurred_at",
        "payload",
    ),
    "legacy_evaluation_bindings": (
        "record_id",
        "exact_identity",
        "occurred_at",
        "payload",
    ),
    "governance_bindings": (
        "occurrence_ref",
        "binding_ref",
        "exact_identity",
        "occurred_at",
        "payload",
    ),
    "intelligence_bindings": (
        "occurrence_ref",
        "binding_ref",
        "exact_identity",
        "occurred_at",
        "payload",
    ),
    "private_eval_bindings": (
        "occurrence_ref",
        "binding_ref",
        "exact_identity",
        "occurred_at",
        "payload",
    ),
}

_V1_SQL = """
CREATE TABLE skill_schema_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1)
);
CREATE TABLE skill_migration_history (
    migration_id TEXT PRIMARY KEY,
    from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE publications (
    exact_identity TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(skill_id, version)
);
CREATE TABLE lifecycle_records (
    record_id TEXT PRIMARY KEY,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    record_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    parent_installation_id TEXT REFERENCES installation_records(record_id),
    payload TEXT NOT NULL
);
CREATE TABLE installation_records (
    record_id TEXT PRIMARY KEY,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE installation_terminations (
    record_id TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL REFERENCES installation_records(record_id),
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE assignments (
    record_id TEXT PRIMARY KEY,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    subject_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE assignment_terminations (
    record_id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL REFERENCES assignments(record_id),
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    subject_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE leases (
    record_id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL REFERENCES assignments(record_id),
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    agent_ref TEXT NOT NULL,
    task_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE lease_terminations (
    record_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL REFERENCES leases(record_id),
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    agent_ref TEXT NOT NULL,
    task_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE legacy_governance_bindings (
    record_id TEXT PRIMARY KEY,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE legacy_evaluation_bindings (
    record_id TEXT PRIMARY KEY,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE governance_bindings (
    occurrence_ref TEXT PRIMARY KEY,
    binding_ref TEXT NOT NULL,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(binding_ref, occurrence_ref)
);
CREATE TABLE intelligence_bindings (
    occurrence_ref TEXT PRIMARY KEY,
    binding_ref TEXT NOT NULL,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(binding_ref, occurrence_ref)
);
CREATE TABLE private_eval_bindings (
    occurrence_ref TEXT PRIMARY KEY,
    binding_ref TEXT NOT NULL,
    exact_identity TEXT NOT NULL REFERENCES publications(exact_identity),
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(binding_ref, occurrence_ref)
);
CREATE INDEX lifecycle_by_version
    ON lifecycle_records(exact_identity, occurred_at, record_id);
CREATE INDEX installations_by_version
    ON installation_records(exact_identity, occurred_at, record_id);
CREATE INDEX installation_ends_by_version
    ON installation_terminations(exact_identity, occurred_at, record_id);
CREATE INDEX assignments_by_subject
    ON assignments(subject_ref, occurred_at, record_id);
CREATE INDEX assignment_ends_by_subject
    ON assignment_terminations(subject_ref, occurred_at, record_id);
CREATE INDEX leases_by_agent ON leases(agent_ref, occurred_at, record_id);
CREATE INDEX leases_by_task ON leases(task_ref, occurred_at, record_id);
CREATE INDEX leases_by_version
    ON leases(exact_identity, occurred_at, record_id);
CREATE INDEX governance_by_version
    ON governance_bindings(exact_identity, occurred_at, occurrence_ref);
CREATE INDEX intelligence_by_version
    ON intelligence_bindings(exact_identity, occurred_at, occurrence_ref);
CREATE INDEX private_eval_by_version
    ON private_eval_bindings(exact_identity, occurred_at, occurrence_ref);
"""


def _append_only_triggers() -> str:
    statements: list[str] = []
    for table in _RECORD_TABLES:
        statements.extend(
            (
                f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'append-only'); END;",
                f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'append-only'); END;",
            )
        )
    return "\n".join(statements)


@dataclass(frozen=True)
class _SkillPersistenceMigration:
    migration_id: str
    from_version: int
    to_version: SkillPersistenceSchemaVersion
    sql: str
    checksum: str
    rollback_supported: bool = False


_V1_BODY = _V1_SQL + _append_only_triggers()
_V1_ID = "skills-schema-v1"
_V1_FROM = 0
_V1_TO = SkillPersistenceSchemaVersion.V1
_V1_CANONICAL_STEPS = " ".join(_V1_BODY.split())
_V1_CHECKSUM_INPUT = (
    f"id={_V1_ID}\nfrom={_V1_FROM}\nto={int(_V1_TO)}\n" + _V1_CANONICAL_STEPS
)
_V1_MIGRATION = _SkillPersistenceMigration(
    _V1_ID,
    _V1_FROM,
    _V1_TO,
    _V1_BODY,
    hashlib.sha256(_V1_CHECKSUM_INPUT.encode("utf-8")).hexdigest(),
)


class SkillPersistenceMigrator:
    def __init__(
        self,
        connections: SkillSQLiteConnectionFactory,
        clock: Callable[[], datetime],
    ) -> None:
        self._connections = connections
        self._clock = clock

    def migrate(self) -> SkillPersistenceSchemaVersion:
        try:
            with self._connections.connection() as connection:
                current = self._current_version(connection)
                if current == SkillPersistenceSchemaVersion.V1:
                    connection.execute("BEGIN")
                    self._verify_migration(connection, _V1_MIGRATION)
                    self._verify_schema(connection)
                    self._integrity(connection)
                    connection.commit()
                    return SkillPersistenceSchemaVersion(current)
                if current != 0:
                    raise SkillPersistenceSchemaUnsupported()
                connection.executescript("BEGIN EXCLUSIVE;\n" + _V1_MIGRATION.sql)
                connection.execute(
                    "INSERT INTO skill_schema_metadata(singleton, schema_version) "
                    "VALUES (1, ?)",
                    (int(_V1_MIGRATION.to_version),),
                )
                connection.execute(
                    "INSERT INTO skill_migration_history"
                    "(migration_id, from_version, to_version, checksum, applied_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        _V1_MIGRATION.migration_id,
                        _V1_MIGRATION.from_version,
                        int(_V1_MIGRATION.to_version),
                        _V1_MIGRATION.checksum,
                        canonical_timestamp(self._clock()),
                    ),
                )
                self._integrity(connection)
                self._verify_schema(connection)
                connection.commit()
                return _V1_MIGRATION.to_version
        except (
            SkillPersistenceDatabaseCorrupt,
            SkillPersistenceMigrationChecksumMismatch,
            SkillPersistenceMigrationRequired,
            SkillPersistenceSchemaUnsupported,
        ):
            raise
        except sqlite3.Error as exc:
            raise SkillPersistenceMigrationFailed() from exc

    def verify(self) -> SkillPersistenceSchemaVersion:
        try:
            with self._connections.connection() as connection:
                current = self._current_version(connection)
                if current != SkillPersistenceSchemaVersion.V1:
                    raise SkillPersistenceMigrationRequired()
                self._verify_migration(connection, _V1_MIGRATION)
                self._verify_schema(connection)
                self._integrity(connection)
                return SkillPersistenceSchemaVersion(current)
        except sqlite3.Error as exc:
            raise SkillPersistenceDatabaseCorrupt() from exc

    @staticmethod
    def _current_version(connection: sqlite3.Connection) -> int:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if not str(row[0]).startswith("sqlite_")
        }
        if not tables:
            return 0
        if "skill_schema_metadata" not in tables or "skill_migration_history" not in tables:
            raise SkillPersistenceMigrationRequired()
        rows = connection.execute(
            "SELECT schema_version FROM skill_schema_metadata WHERE singleton = 1"
        ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], int):
            raise SkillPersistenceDatabaseCorrupt()
        version = int(rows[0][0])
        if version > int(SkillPersistenceSchemaVersion.V1):
            raise SkillPersistenceSchemaUnsupported()
        return version

    @staticmethod
    def _verify_migration(
        connection: sqlite3.Connection, migration: _SkillPersistenceMigration
    ) -> None:
        rows = connection.execute(
            "SELECT from_version, to_version, checksum FROM skill_migration_history "
            "WHERE migration_id = ?",
            (migration.migration_id,),
        ).fetchall()
        if len(rows) != 1:
            raise SkillPersistenceMigrationRequired()
        row = rows[0]
        if (
            row[0] != migration.from_version
            or row[1] != int(migration.to_version)
            or row[2] != migration.checksum
        ):
            raise SkillPersistenceMigrationChecksumMismatch()

    @staticmethod
    def _integrity(connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SkillPersistenceDatabaseCorrupt()
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise SkillPersistenceDatabaseCorrupt()

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        objects = connection.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE type IN ('table', 'index', 'trigger')"
        ).fetchall()
        tables = {
            row[1] for row in objects if row[0] == "table" and not row[1].startswith("sqlite_")
        }
        indexes = {
            row[1] for row in objects if row[0] == "index" and not row[1].startswith("sqlite_")
        }
        triggers = {row[1] for row in objects if row[0] == "trigger"}
        if (
            tables != _EXPECTED_TABLES
            or indexes != _EXPECTED_INDEXES
            or triggers != _EXPECTED_TRIGGERS
        ):
            raise SkillPersistenceDatabaseCorrupt()
        for table, expected in _EXPECTED_COLUMNS.items():
            actual = tuple(
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if actual != expected:
                raise SkillPersistenceDatabaseCorrupt()
        expected_foreign_keys = {
            "lifecycle_records": 2,
            "installation_records": 1,
            "installation_terminations": 2,
            "assignments": 1,
            "assignment_terminations": 2,
            "leases": 2,
            "lease_terminations": 2,
            "legacy_governance_bindings": 1,
            "legacy_evaluation_bindings": 1,
            "governance_bindings": 1,
            "intelligence_bindings": 1,
            "private_eval_bindings": 1,
        }
        for table, expected_count in expected_foreign_keys.items():
            if len(connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()) != expected_count:
                raise SkillPersistenceDatabaseCorrupt()
        publication_unique = connection.execute(
            "PRAGMA index_list(publications)"
        ).fetchall()
        if sum(1 for row in publication_unique if row[2] == 1) < 2:
            raise SkillPersistenceDatabaseCorrupt()
