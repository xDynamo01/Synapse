"""SQLite WAL transaction and snapshot candidate for the foundation spike."""

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


_APPLICATION_ID = 0x53594E50  # SYNP
_SCHEMA_VERSION = 1
_V1_SCHEMA = """CREATE TABLE records (
    record_id TEXT NOT NULL CHECK (length(record_id) > 0),
    version INTEGER NOT NULL CHECK (version > 0),
    reference TEXT NOT NULL CHECK (length(reference) > 0),
    sha256 TEXT NOT NULL CHECK (
        length(sha256) = 64
        AND length(CAST(sha256 AS BLOB)) = 64
        AND sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    PRIMARY KEY (record_id, version)
) STRICT, WITHOUT ROWID"""


class StorageFormatError(ValueError):
    """The database identity, schema or integrity check failed."""


@dataclass(frozen=True)
class RecordPayload:
    reference: str
    sha256: str


def _open(path: Path, mode: str) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode={mode}", uri=True, timeout=2.0, autocommit=True,
    )
    try:
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA synchronous = FULL")
    except BaseException:
        connection.close()
        raise
    return connection


def _needs_migration(connection: sqlite3.Connection) -> bool:
    (application_id,) = connection.execute("PRAGMA application_id").fetchone()
    (version,) = connection.execute("PRAGMA user_version").fetchone()
    objects = connection.execute("SELECT type, name, sql FROM sqlite_schema").fetchall()
    if (application_id, version) == (0, 0) and not objects:
        return True
    if (application_id, version) != (_APPLICATION_ID, _SCHEMA_VERSION):
        raise StorageFormatError("Unrecognized database identity or schema version")
    if objects != [("table", "records", _V1_SCHEMA)]:
        raise StorageFormatError("Schema does not match its declared version")
    return False


def _check_integrity(connection: sqlite3.Connection) -> None:
    if _needs_migration(connection):
        raise StorageFormatError("Database has no initialized schema")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise StorageFormatError("SQLite integrity check failed")


def _sidecars(path: Path) -> tuple[Path, ...]:
    return tuple(path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal"))


def _copy_database(source: sqlite3.Connection, destination: Path, journal_mode: str) -> None:
    if any(os.path.lexists(path) for path in (destination, *_sidecars(destination))):
        raise FileExistsError(destination)
    # Stage on the same volume and publish atomically without replacing an existing file.
    with TemporaryDirectory(prefix=".snapshot-", dir=destination.parent) as scratch:
        staged = Path(scratch) / "staged.sqlite"
        with closing(_open(staged, "rwc")) as target:
            source.backup(target)
            if target.execute(f"PRAGMA journal_mode = {journal_mode}").fetchone() != (journal_mode,):
                raise StorageFormatError("Could not configure snapshot journal mode")
            _check_integrity(target)
        os.link(staged, destination)


class Storage:
    def __init__(self, path: Path):
        self.path = path.absolute()

    def _connect(self, mode: str = "rw") -> sqlite3.Connection:
        return _open(self.path, mode)

    def initialize(self) -> None:
        if not os.path.lexists(self.path) and any(os.path.lexists(path) for path in _sidecars(self.path)):
            raise StorageFormatError("Missing database has leftover journal files")
        with closing(self._connect("rwc")) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if _needs_migration(connection):
                connection.execute(_V1_SCHEMA)
                connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.execute("COMMIT")
            if connection.execute("PRAGMA journal_mode = WAL").fetchone() != ("wal",):
                raise StorageFormatError("Could not enable SQLite WAL")

    def append_record(self, record_id: str, version: int, payload: RecordPayload) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO records (record_id, version, reference, sha256) VALUES (?, ?, ?, ?)",
                (record_id, version, payload.reference, payload.sha256),
            )
            connection.execute("COMMIT")

    def read_record(self, record_id: str, version: int) -> RecordPayload | None:
        with closing(self._connect("ro")) as connection:
            row = connection.execute(
                "SELECT reference, sha256 FROM records WHERE record_id = ? AND version = ?",
                (record_id, version),
            ).fetchone()
        return RecordPayload(*row) if row is not None else None

    def checkpoint(self) -> tuple[int, int, int]:
        """Return SQLite's busy flag, WAL frames and checkpointed frames."""
        with closing(self._connect()) as connection:
            return connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()

    def check_integrity(self) -> None:
        with closing(self._connect("ro")) as connection:
            _check_integrity(connection)

    def backup(self, backup_path: Path) -> None:
        with closing(self._connect("ro")) as source:
            _copy_database(source, backup_path.absolute(), "delete")

    def restore(self, backup_path: Path) -> None:
        backup_path = backup_path.absolute()
        if any(os.path.lexists(path) for path in _sidecars(backup_path)):
            raise StorageFormatError("Snapshot must be a single file without journal sidecars")
        with closing(_open(backup_path, "ro")) as source:
            if source.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                raise StorageFormatError("Snapshot must use DELETE journal mode")
            _check_integrity(source)
            _copy_database(source, self.path, "wal")
