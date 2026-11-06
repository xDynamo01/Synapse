import hashlib
import sqlite3
from contextlib import closing
from time import perf_counter

import pytest

from storage import RecordPayload, Storage, StorageFormatError


def test_backup_includes_uncheckpointed_data_and_restores_into_new_directory(scratch):
    source_dir = scratch / "source"
    source_dir.mkdir()
    source = Storage(source_dir / "records.sqlite")
    source.initialize()
    records = {
        version: RecordPayload(
            f"fixture:{version}", hashlib.sha256(str(version).encode()).hexdigest(),
        )
        for version in range(1, 257)
    }
    backup = scratch / "snapshot.sqlite"

    with closing(sqlite3.connect(source.path, autocommit=True)) as reader:
        reader.execute("BEGIN")
        assert reader.execute("SELECT count(*) FROM records").fetchone() == (0,)
        for version, payload in records.items():
            source.append_record("record", version, payload)

        assert source.path.with_name("records.sqlite-wal").stat().st_size > 32
        started = perf_counter()
        source.backup(backup)
        backup_ms = 1000 * (perf_counter() - started)
        assert reader.execute("SELECT count(*) FROM records").fetchone() == (0,)

    source.append_record("record", 257, records[1])
    original_snapshot = backup.read_bytes()
    with pytest.raises(FileExistsError):
        source.backup(backup)
    assert backup.read_bytes() == original_snapshot

    restored_dir = scratch / "restored"
    restored_dir.mkdir()
    restored = Storage(restored_dir / "records.sqlite")
    started = perf_counter()
    restored.restore(backup)
    restore_ms = 1000 * (perf_counter() - started)
    restored.check_integrity()
    with closing(sqlite3.connect(restored.path, autocommit=True)) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    for version, payload in records.items():
        assert restored.read_record("record", version) == payload
    assert restored.read_record("record", 257) is None

    restored.append_record("record", 257, records[2])
    assert source.read_record("record", 257) == records[1]
    assert restored.read_record("record", 257) == records[2]
    print(
        f"backup_records={len(records)} backup_bytes={len(original_snapshot)} "
        f"backup_ms={backup_ms:.3f} restore_ms={restore_ms:.3f}"
    )


def test_restore_rejects_corrupt_and_foreign_snapshots_without_publishing(scratch):
    source = Storage(scratch / "records.sqlite")
    source.initialize()
    source.append_record("record", 1, RecordPayload("fixture:blob", "0" * 64))
    snapshot = scratch / "snapshot.sqlite"
    source.backup(snapshot)

    corrupt = scratch / "corrupt.sqlite"
    corrupt.write_bytes(snapshot.read_bytes()[:512])
    unrelated = scratch / "unrelated.sqlite"
    with closing(sqlite3.connect(unrelated, autocommit=True)) as connection:
        connection.execute("CREATE TABLE unrelated(id INTEGER)")

    destination = scratch / "restored"
    destination.mkdir()
    restored = Storage(destination / "records.sqlite")
    for invalid in (corrupt, unrelated):
        with pytest.raises((sqlite3.DatabaseError, StorageFormatError)):
            restored.restore(invalid)
        assert list(destination.iterdir()) == []

    with pytest.raises(sqlite3.OperationalError):
        restored.restore(scratch / "missing.sqlite")
    assert list(destination.iterdir()) == []


def test_restore_preserves_existing_database_and_rejects_sidecars(scratch):
    source = Storage(scratch / "records.sqlite")
    source.initialize()
    payload = RecordPayload("fixture:blob", "0" * 64)
    source.append_record("record", 1, payload)
    snapshot = scratch / "snapshot.sqlite"
    source.backup(snapshot)

    with pytest.raises(FileExistsError):
        source.restore(snapshot)
    assert source.read_record("record", 1) == payload

    destination = scratch / "restored.sqlite"
    stale_wal = destination.with_name("restored.sqlite-wal")
    stale_wal.write_bytes(b"old WAL")
    with pytest.raises(FileExistsError):
        Storage(destination).restore(snapshot)
    assert not destination.exists()
    assert stale_wal.read_bytes() == b"old WAL"

    snapshot.with_name("snapshot.sqlite-wal").write_bytes(b"unexpected WAL")
    with pytest.raises(StorageFormatError):
        Storage(scratch / "other.sqlite").restore(snapshot)
    assert not (scratch / "other.sqlite").exists()
