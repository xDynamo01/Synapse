from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.core.events import EventBus
from synapse.storage.atomic import atomic_write_text
from synapse.storage.collection import FileCollection
from synapse.storage.contracts import CollectionQuery, RetentionPolicy
from synapse.storage.errors import (
    StorageCorrupted,
    StorageCursorInvalid,
    StorageLockTimeout,
    StoragePathInvalid,
    StorageRevisionConflict,
    StorageSchemaUnsupported,
    StorageWriteFailed,
)
from synapse.storage.locking import CollectionLock
from synapse.storage.migrations import MigrationRegistry


def payload(record_id: str, revision: int = 1, *, updated_at: str | None = None) -> dict:
    now = updated_at or datetime.now(UTC).isoformat()
    return {
        "id": record_id,
        "schema_version": 1,
        "revision": revision,
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "kind": "test",
    }


def collection(root: Path, **kwargs) -> FileCollection:
    return FileCollection(
        collection_id=kwargs.pop("collection_id", "test_records"),
        root=root,
        current_schema_version=kwargs.pop("current_schema_version", 1),
        validator=kwargs.pop("validator", lambda value: _require(value, "id")),
        **kwargs,
    )


def test_create_get_update_conflict_delete_and_restart(tmp_path: Path) -> None:
    records = collection(tmp_path / "records")
    created = records.put("alpha", payload("alpha"), create_only=True)
    assert created.created and created.revision == 1 and created.checksum
    assert records.get("alpha").payload["id"] == "alpha"

    updated = records.put("alpha", payload("alpha", 2), expected_revision=1)
    assert updated.previous_revision == 1 and updated.revision == 2
    with pytest.raises(StorageRevisionConflict):
        records.put("alpha", payload("alpha", 3), expected_revision=1)

    restarted = collection(tmp_path / "records")
    assert restarted.get("alpha").revision == 2
    assert restarted.delete("alpha", expected_revision=2).deleted
    assert not restarted.delete("alpha").deleted


def test_deterministic_pagination_filter_and_invalid_cursor(tmp_path: Path) -> None:
    records = collection(tmp_path / "records")
    for record_id in ("delta", "alpha", "charlie", "bravo"):
        value = payload(record_id)
        value["kind"] = "selected" if record_id != "delta" else "other"
        records.put(record_id, value)

    first = records.list(CollectionQuery(limit=2, filters={"kind": "selected"}))
    second = records.list(
        CollectionQuery(cursor=first.next_cursor, limit=2, filters={"kind": "selected"})
    )
    assert [item.record_id for item in first.items] == ["alpha", "bravo"]
    assert [item.record_id for item in second.items] == ["charlie"]
    with pytest.raises(StorageCursorInvalid):
        records.list(CollectionQuery(cursor="not-a-cursor"))
    with pytest.raises(StorageCursorInvalid):
        records.list(CollectionQuery(limit=501))


def test_atomic_replace_failure_preserves_original_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "record.json"
    path.write_text("original", encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(StorageWriteFailed):
        atomic_write_text(path, "replacement")
    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_serialization_failure_leaves_no_record(tmp_path: Path) -> None:
    records = collection(tmp_path / "records")
    invalid = payload("alpha")
    invalid["unsupported"] = object()
    with pytest.raises(StorageWriteFailed):
        records.put("alpha", invalid)
    assert not (tmp_path / "records" / "alpha.yaml").exists()


def test_lock_timeout_release_on_exception_and_explicit_reentrancy(tmp_path: Path) -> None:
    path = tmp_path / "records" / ".lock"
    first = CollectionLock(path, timeout_seconds=0.1)
    second = CollectionLock(path, timeout_seconds=0.05)
    errors: list[Exception] = []
    with first.acquire():
        with first.acquire():
            thread = threading.Thread(target=lambda: _capture_lock(second, errors))
            thread.start()
            thread.join()
    assert isinstance(errors[0], StorageLockTimeout)
    with pytest.raises(RuntimeError):
        with first.acquire():
            raise RuntimeError("release")
    with first.acquire():
        assert path.exists()
    assert not path.exists()


def test_concurrent_optimistic_update_has_one_winner(tmp_path: Path) -> None:
    records = collection(tmp_path / "records")
    records.put("alpha", payload("alpha"))
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def update() -> None:
        barrier.wait()
        try:
            records.put("alpha", payload("alpha", 2), expected_revision=1)
            outcomes.append("written")
        except StorageRevisionConflict:
            outcomes.append("conflict")

    threads = [threading.Thread(target=update) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["conflict", "written"]
    assert records.get("alpha").revision == 2


def test_explicit_migration_and_failure(tmp_path: Path) -> None:
    root = tmp_path / "records"
    root.mkdir()
    (root / "alpha.yaml").write_text(
        "id: alpha\nschema_version: 1\nrevision: 1\ncreated_at: '2026-01-01T00:00:00+00:00'\nupdated_at: '2026-01-01T00:00:00+00:00'\n",
        encoding="utf-8",
    )
    migrations = MigrationRegistry()
    migrations.register(1, 2, lambda value: {**value, "schema_version": 2, "migrated": True})
    records = collection(root, current_schema_version=2, migrations=migrations)
    migrated = records.get("alpha")
    assert migrated.schema_version == 2 and migrated.payload["migrated"] is True
    assert (root / "alpha.yaml.bak").exists()

    (root / "beta.yaml").write_text("id: beta\nschema_version: 1\n", encoding="utf-8")
    missing = collection(root, collection_id="missing_migration", current_schema_version=3)
    with pytest.raises(StorageSchemaUnsupported):
        missing.get("beta")


def test_corruption_quarantine_and_backup_recovery(tmp_path: Path) -> None:
    quarantine = collection(tmp_path / "quarantine", recovery_policy="quarantine_record")
    quarantine.put("broken", payload("broken"))
    (tmp_path / "quarantine" / "broken.yaml").write_text("not: [yaml", encoding="utf-8")
    with pytest.raises(StorageCorrupted):
        quarantine.get("broken")
    result = quarantine.recover()
    assert result.quarantined == 1 and result.failed == 0
    assert any((tmp_path / "quarantine" / ".quarantine").iterdir())

    recover = collection(tmp_path / "recover", recovery_policy="recover_from_backup")
    recover.put("alpha", payload("alpha", 1))
    recover.put("alpha", payload("alpha", 2), expected_revision=1)
    (tmp_path / "recover" / "alpha.yaml").write_text("broken: [", encoding="utf-8")
    result = recover.recover()
    assert result.repaired == 1 and recover.get("alpha").revision == 1


def test_retention_dry_run_real_active_and_referenced(tmp_path: Path) -> None:
    old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    records = collection(tmp_path / "records")
    for record_id in ("delete", "active", "referenced", "recent"):
        records.put(
            record_id,
            payload(record_id, updated_at=None if record_id == "recent" else old),
        )
    policy = RetentionPolicy(max_age_seconds=3600, dry_run=True)
    preview = records.cleanup(
        policy,
        is_active=lambda item: item.record_id == "active",
        is_referenced=lambda item: item.record_id == "referenced",
    )
    assert preview.eligible == 1 and preview.deleted == 0
    applied = records.cleanup(
        RetentionPolicy(max_age_seconds=3600, dry_run=False),
        is_active=lambda item: item.record_id == "active",
        is_referenced=lambda item: item.record_id == "referenced",
    )
    assert applied.deleted == 1
    assert {item.record_id for item in records.list_all()} == {"active", "referenced", "recent"}


def test_path_validation_and_symlink_escape(tmp_path: Path) -> None:
    with pytest.raises(StoragePathInvalid):
        collection(Path("relative"))
    records = collection(tmp_path / "records")
    with pytest.raises(StoragePathInvalid):
        records.put("../escape", payload("escape"))
    outside = tmp_path / "outside.yaml"
    outside.write_text("id: outside", encoding="utf-8")
    link = tmp_path / "records" / "linked.yaml"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    with pytest.raises(StoragePathInvalid):
        records.get("linked")


def test_observability_contains_metadata_not_payload_or_sensitive_id(tmp_path: Path) -> None:
    events = EventBus(tmp_path)
    records = collection(
        tmp_path / "records", events=events, sensitive_record_ids=True
    )
    value = payload("secret-record")
    value["secret"] = "do-not-log"
    records.put("secret-record", value)
    event = events.tail(1)[0]
    assert event.type == "collection.write"
    assert event.payload["collection_id"] == "test_records"
    assert event.payload["record_id"] != "secret-record"
    assert "do-not-log" not in str(event.payload)


def _capture_lock(lock: CollectionLock, errors: list[Exception]) -> None:
    try:
        with lock.acquire():
            pass
    except Exception as exc:
        errors.append(exc)


def _require(payload: dict, field: str) -> None:
    if field not in payload:
        raise ValueError(f"missing {field}")
