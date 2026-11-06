import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from storage import RecordPayload, Storage, StorageFormatError


PAYLOAD = RecordPayload("fixture:record", hashlib.sha256(b"fixture").hexdigest())


def test_linked_sqlite_has_wal_reset_fix():
    assert sqlite3.sqlite_version_info >= (3, 51, 3)


def test_append_read_and_reject_duplicate_version(scratch):
    storage = Storage(scratch / "records.sqlite")
    storage.initialize()
    assert storage.read_record("record", 1) is None

    storage.append_record("record", 1, PAYLOAD)
    updated = RecordPayload("fixture:updated", PAYLOAD.sha256)
    with pytest.raises(sqlite3.IntegrityError):
        storage.append_record("record", 1, updated)
    storage.append_record("record", 2, updated)

    reopened = Storage(storage.path)
    reopened.initialize()
    assert reopened.read_record("record", 1) == PAYLOAD
    assert reopened.read_record("record", 2) == updated
    reopened.check_integrity()


def test_rejects_invalid_payload_without_a_partial_record(scratch):
    storage = Storage(scratch / "records.sqlite")
    storage.initialize()

    for invalid in (RecordPayload("", PAYLOAD.sha256), RecordPayload("fixture:x", "z" * 64)):
        with pytest.raises(sqlite3.IntegrityError):
            storage.append_record("record", 1, invalid)
        assert storage.read_record("record", 1) is None

    storage.append_record("record", 1, PAYLOAD)
    assert storage.read_record("record", 1) == PAYLOAD


def test_writer_commits_with_two_reader_snapshots_open(scratch):
    storage = Storage(scratch / "records.sqlite")
    storage.initialize()
    storage.append_record("record", 1, PAYLOAD)
    select_versions = "SELECT version FROM records ORDER BY version"

    with closing(sqlite3.connect(storage.path, autocommit=True)) as first:
        with closing(sqlite3.connect(storage.path, autocommit=True)) as second:
            for reader in (first, second):
                reader.execute("BEGIN")
                assert reader.execute(select_versions).fetchall() == [(1,)]

            with ThreadPoolExecutor(max_workers=1) as executor:
                writer = executor.submit(storage.append_record, "record", 2, PAYLOAD)
                writer.result(timeout=5)
            assert storage.read_record("record", 2) == PAYLOAD

            busy, frames, copied = storage.checkpoint()
            assert busy == 0
            assert 0 <= copied < frames
            for reader in (first, second):
                assert reader.execute(select_versions).fetchall() == [(1,)]
                reader.execute("COMMIT")
                assert reader.execute(select_versions).fetchall() == [(1,), (2,)]

    busy, frames, copied = storage.checkpoint()
    assert busy == 0 and frames == copied >= 0


def test_unrecognized_or_future_schema_fails_closed(scratch):
    path = scratch / "records.sqlite"
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        connection.execute("CREATE TABLE unrelated(id INTEGER)")
    storage = Storage(path)

    with pytest.raises(StorageFormatError):
        storage.initialize()
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)

    current = Storage(scratch / "current.sqlite")
    current.initialize()
    current.append_record("record", 1, PAYLOAD)
    with closing(sqlite3.connect(current.path, autocommit=True)) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(StorageFormatError):
        current.initialize()
    with closing(sqlite3.connect(current.path, autocommit=True)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (999,)
        assert connection.execute("SELECT count(*) FROM records").fetchone() == (1,)


class InterruptedMigration(Storage):
    def _connect(self, mode="rw"):
        connection = super()._connect(mode)

        def deny_version_bump(action, name, value, *_):
            if action == sqlite3.SQLITE_PRAGMA and name == "user_version" and value is not None:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(deny_version_bump)
        return connection


def test_interrupted_migration_rolls_back_schema_and_identity(scratch):
    path = scratch / "records.sqlite"
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        InterruptedMigration(path).initialize()

    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        assert connection.execute("PRAGMA application_id").fetchone() == (0,)
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []

    storage = Storage(path)
    storage.initialize()
    storage.append_record("record", 1, PAYLOAD)
    assert storage.read_record("record", 1) == PAYLOAD
