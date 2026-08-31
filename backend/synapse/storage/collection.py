from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from synapse.storage.atomic import atomic_write_text
from synapse.storage.contracts import (
    CleanupResult,
    CollectionPage,
    CollectionQuery,
    CollectionRecord,
    DeleteResult,
    RecoveryPolicy,
    RecoveryResult,
    RetentionPolicy,
    WriteResult,
)
from synapse.storage.errors import (
    StorageCorrupted,
    StorageCursorInvalid,
    StoragePathInvalid,
    StorageReadFailed,
    StorageRecordNotFound,
    StorageRetentionFailed,
    StorageRevisionConflict,
    StorageSchemaUnsupported,
    StorageWriteFailed,
)
from synapse.storage.locking import CollectionLock
from synapse.storage.migrations import MigrationRegistry

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class EventSink(Protocol):
    def emit(self, event_type: str, actor_id: str, payload: dict[str, Any]) -> Any: ...


class FileCollection:
    """Small operational record collection; domain DTOs remain outside this package."""

    MAX_LIMIT = 500

    def __init__(
        self,
        *,
        collection_id: str,
        root: Path,
        current_schema_version: int,
        suffix: str = ".yaml",
        validator: Callable[[Mapping[str, Any]], None] | None = None,
        schema_version: Callable[[Mapping[str, Any]], int] | None = None,
        revision: Callable[[Mapping[str, Any]], int] | None = None,
        created_at: Callable[[Mapping[str, Any]], str] | None = None,
        updated_at: Callable[[Mapping[str, Any]], str] | None = None,
        migrations: MigrationRegistry | None = None,
        recovery_policy: RecoveryPolicy = "fail_closed",
        events: EventSink | None = None,
        lock_timeout_seconds: float = 5.0,
        stale_lock_seconds: float = 60.0,
        backup_on_write: bool = True,
        sensitive_record_ids: bool = False,
    ) -> None:
        _validate_identifier(collection_id, kind="collection")
        if not root.is_absolute():
            raise StoragePathInvalid("Storage collection root must be pre-resolved")
        if current_schema_version < 1:
            raise StorageSchemaUnsupported("Storage schema version must be positive")
        if not suffix.startswith(".") or any(char in suffix for char in ("/", "\\")):
            raise StoragePathInvalid("Storage suffix is invalid")
        self.collection_id = collection_id
        self.root = root.resolve(strict=False)
        self.current_schema_version = current_schema_version
        self.suffix = suffix
        self.validator = validator or (lambda _payload: None)
        self.schema_version_of = schema_version or (
            lambda payload: int(payload.get("schema_version", current_schema_version))
        )
        self.revision_of = revision or (lambda payload: int(payload.get("revision", 1)))
        self.created_at_of = created_at or (
            lambda payload: str(payload.get("created_at") or _now())
        )
        self.updated_at_of = updated_at or (
            lambda payload: str(payload.get("updated_at") or self.created_at_of(payload))
        )
        self.migrations = migrations or MigrationRegistry()
        self.recovery_policy = recovery_policy
        self.events = events
        self.backup_on_write = backup_on_write
        self.sensitive_record_ids = sensitive_record_ids
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = CollectionLock(
            self.root / f".{collection_id}.lock",
            timeout_seconds=lock_timeout_seconds,
            stale_after_seconds=stale_lock_seconds,
        )

    def put(
        self,
        record_id: str,
        payload: Mapping[str, Any],
        *,
        expected_revision: int | None = None,
        create_only: bool = False,
    ) -> WriteResult:
        started = perf_counter()
        path = self._path(record_id)
        safe_payload = dict(payload)
        self.validator(safe_payload)
        schema_version = self.schema_version_of(safe_payload)
        if schema_version != self.current_schema_version:
            raise StorageSchemaUnsupported(
                f"Cannot write schema {schema_version} to collection schema {self.current_schema_version}"
            )
        with self.lock.acquire():
            existing = self._read_path(path, migrate=False) if path.exists() else None
            if create_only and existing is not None:
                raise StorageRevisionConflict(
                    "Storage record already exists",
                    details={"record_id": self._safe_id(record_id)},
                )
            if expected_revision is not None and (
                existing is None or existing.revision != expected_revision
            ):
                actual = existing.revision if existing else None
                self._emit(
                    "collection.conflict",
                    record_id,
                    {"expected_revision": expected_revision, "actual_revision": actual},
                )
                raise StorageRevisionConflict(
                    "Storage revision conflict",
                    details={"expected": expected_revision, "actual": actual},
                )
            try:
                text = _dump_structured(safe_payload)
                checksum = _checksum(safe_payload)
                written = atomic_write_text(
                    path, text, backup=self.backup_on_write and existing is not None
                )
            except StorageWriteFailed:
                raise
            except Exception as exc:
                raise StorageWriteFailed(
                    "Storage record serialization failed",
                    details={"record_id": self._safe_id(record_id)},
                ) from exc
        result = WriteResult(
            record_id=record_id,
            previous_revision=existing.revision if existing else None,
            revision=self.revision_of(safe_payload),
            created=existing is None,
            checksum=checksum,
            written_at=_now(),
        )
        self._emit(
            "collection.write",
            record_id,
            {
                "schema_version": schema_version,
                "revision": result.revision,
                "bytes": written,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "status": "created" if result.created else "updated",
            },
        )
        return result

    def get(self, record_id: str) -> CollectionRecord:
        started = perf_counter()
        path = self._path(record_id)
        if not path.exists():
            raise StorageRecordNotFound(
                "Storage record not found", details={"record_id": self._safe_id(record_id)}
            )
        record = self._read_path(path, migrate=True)
        self._emit(
            "collection.read",
            record_id,
            {
                "schema_version": record.schema_version,
                "revision": record.revision,
                "bytes": path.stat().st_size,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "status": "ok",
            },
        )
        return record

    def list(self, query: CollectionQuery | None = None) -> CollectionPage:
        query = query or CollectionQuery()
        if query.limit < 1 or query.limit > self.MAX_LIMIT:
            raise StorageCursorInvalid(
                f"Storage query limit must be between 1 and {self.MAX_LIMIT}"
            )
        if query.expected_schema_version not in (None, self.current_schema_version):
            raise StorageSchemaUnsupported("Storage query schema is unsupported")
        cursor = _decode_cursor(query.cursor) if query.cursor else None
        if cursor and (cursor["sort"] != query.sort or cursor["descending"] != query.descending):
            raise StorageCursorInvalid("Storage cursor does not match query ordering")
        if query.sort == "record_id":
            return self._list_by_record_id(query, cursor)
        records: list[CollectionRecord] = []
        warnings: list[str] = []
        for path in sorted(self.root.glob(f"*{self.suffix}")):
            if path.name.endswith(f"{self.suffix}.bak"):
                continue
            try:
                record = self._read_path(path, migrate=True)
            except StorageCorrupted as exc:
                if self.recovery_policy == "skip_with_warning":
                    warnings.append(f"corrupted:{path.stem}")
                    continue
                raise exc
            if not _matches(record.payload, query.filters):
                continue
            if not query.include_deleted and record.payload.get("status") == "deleted":
                continue
            records.append(record)
        records.sort(
            key=lambda item: (_sort_value(item, query.sort), item.record_id),
            reverse=query.descending,
        )
        if cursor:
            records = [
                item
                for item in records
                if _after_cursor(item, query.sort, query.descending, cursor)
            ]
        total = len(records)
        selected = records[: query.limit]
        next_cursor = None
        if len(records) > query.limit:
            last = selected[-1]
            next_cursor = _encode_cursor(last, query.sort, query.descending)
        return CollectionPage(tuple(selected), next_cursor, total, tuple(warnings))

    def _list_by_record_id(
        self,
        query: CollectionQuery,
        cursor: Mapping[str, Any] | None,
    ) -> CollectionPage:
        """Stream stable filename order so each cursor page does not rescan old records."""

        paths = sorted(
            self.root.glob(f"*{self.suffix}"),
            key=lambda path: path.name,
            reverse=query.descending,
        )
        if cursor:
            boundary = str(cursor["record_id"])
            paths = [
                path
                for path in paths
                if (
                    (path.name[: -len(self.suffix)] < boundary)
                    if query.descending
                    else (path.name[: -len(self.suffix)] > boundary)
                )
            ]
        selected: list[CollectionRecord] = []
        warnings: list[str] = []
        has_more = False
        for path in paths:
            try:
                record = self._read_path(path, migrate=True)
            except StorageCorrupted as exc:
                if self.recovery_policy == "skip_with_warning":
                    warnings.append(f"corrupted:{path.stem}")
                    continue
                raise exc
            if not _matches(record.payload, query.filters):
                continue
            if not query.include_deleted and record.payload.get("status") == "deleted":
                continue
            if len(selected) == query.limit:
                has_more = True
                break
            selected.append(record)
        next_cursor = (
            _encode_cursor(selected[-1], query.sort, query.descending)
            if has_more and selected
            else None
        )
        return CollectionPage(tuple(selected), next_cursor, None, tuple(warnings))

    def list_all(self, *, filters: Mapping[str, Any] | None = None) -> tuple[CollectionRecord, ...]:
        """Explicit bounded-store compatibility path for current domain list contracts."""

        items: list[CollectionRecord] = []
        cursor = None
        while True:
            page = self.list(
                CollectionQuery(cursor=cursor, limit=self.MAX_LIMIT, filters=filters or {})
            )
            items.extend(page.items)
            if page.next_cursor is None:
                return tuple(items)
            cursor = page.next_cursor

    def delete(self, record_id: str, *, expected_revision: int | None = None) -> DeleteResult:
        path = self._path(record_id)
        with self.lock.acquire():
            if not path.exists():
                return DeleteResult(record_id, False, False, None, None)
            current = self._read_path(path, migrate=False)
            if expected_revision is not None and current.revision != expected_revision:
                raise StorageRevisionConflict(
                    "Storage revision conflict",
                    details={"expected": expected_revision, "actual": current.revision},
                )
            size = path.stat().st_size
            path.unlink()
            path.with_suffix(path.suffix + ".bak").unlink(missing_ok=True)
        self._emit(
            "collection.cleanup",
            record_id,
            {"status": "deleted", "bytes": size, "revision": current.revision},
        )
        return DeleteResult(record_id, True, False, current.revision, None)

    def recover(self) -> RecoveryResult:
        scanned = valid = repaired = quarantined = failed = 0
        warnings: list[str] = []
        for path in sorted(self.root.glob(f"*{self.suffix}")):
            scanned += 1
            try:
                self._read_path(path, migrate=True)
                valid += 1
            except StorageCorrupted:
                try:
                    if self.recovery_policy == "recover_from_backup" and self._restore_backup(path):
                        repaired += 1
                    elif self.recovery_policy == "quarantine_record":
                        self._quarantine(path)
                        quarantined += 1
                    elif self.recovery_policy == "skip_with_warning":
                        warnings.append(f"skipped:{path.stem}")
                        failed += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
        result = RecoveryResult(scanned, valid, repaired, quarantined, failed, tuple(warnings))
        self._emit(
            "collection.recovery",
            None,
            {
                "status": "completed" if failed == 0 else "partial",
                "scanned": scanned,
                "repaired": repaired,
                "quarantined": quarantined,
                "failed": failed,
            },
        )
        return result

    def cleanup(
        self,
        policy: RetentionPolicy,
        *,
        is_active: Callable[[CollectionRecord], bool] | None = None,
        is_referenced: Callable[[CollectionRecord], bool] | None = None,
        now: datetime | None = None,
    ) -> CleanupResult:
        try:
            records = list(self.list_all())
            active = is_active or (lambda _record: False)
            referenced = is_referenced or (lambda _record: False)
            current = now or datetime.now(UTC)
            protected = {item.record_id for item in records if active(item) or referenced(item)}
            eligible: set[str] = set()
            if policy.max_age_seconds is not None:
                for item in records:
                    age = (current - datetime.fromisoformat(item.updated_at)).total_seconds()
                    if age > policy.max_age_seconds:
                        eligible.add(item.record_id)
            ordered = sorted(
                records, key=lambda item: (item.updated_at, item.record_id), reverse=True
            )
            if policy.max_records is not None:
                eligible.update(item.record_id for item in ordered[policy.max_records :])
            if policy.max_bytes is not None:
                used = 0
                for item in ordered:
                    size = self._path(item.record_id).stat().st_size
                    used += size
                    if used > policy.max_bytes:
                        eligible.add(item.record_id)
            eligible -= protected
            deleted = failed = reclaimed = 0
            if not policy.dry_run:
                for record_id in sorted(eligible):
                    path = self._path(record_id)
                    size = path.stat().st_size if path.exists() else 0
                    try:
                        if self.delete(record_id).deleted:
                            deleted += 1
                            reclaimed += size
                    except Exception:
                        failed += 1
            result = CleanupResult(
                scanned=len(records),
                eligible=len(eligible),
                deleted=deleted,
                retained=len(records) - deleted,
                failed=failed,
                reclaimed_bytes=reclaimed,
            )
            self._emit(
                "collection.cleanup",
                None,
                {
                    "status": "dry_run" if policy.dry_run else "completed",
                    "scanned": result.scanned,
                    "eligible": result.eligible,
                    "deleted": result.deleted,
                    "bytes": result.reclaimed_bytes,
                },
            )
            return result
        except Exception as exc:
            if isinstance(exc, StorageRetentionFailed):
                raise
            raise StorageRetentionFailed("Storage retention failed") from exc

    def _read_path(self, path: Path, *, migrate: bool) -> CollectionRecord:
        try:
            raw = _load_structured(path)
            schema_version = self.schema_version_of(raw)
            if schema_version > self.current_schema_version:
                raise StorageSchemaUnsupported(
                    f"Storage schema {schema_version} is newer than supported"
                )
            if schema_version < self.current_schema_version:
                if not migrate:
                    raise StorageSchemaUnsupported("Storage record requires migration")
                raw = dict(
                    self.migrations.migrate(raw, schema_version, self.current_schema_version)
                )
                self.validator(raw)
                atomic_write_text(path, _dump_structured(raw), backup=True)
                self._emit(
                    "collection.migration",
                    path.stem,
                    {
                        "status": "completed",
                        "from_schema": schema_version,
                        "schema_version": self.current_schema_version,
                    },
                )
                schema_version = self.current_schema_version
            self.validator(raw)
            record_id = path.name[: -len(self.suffix)]
            return CollectionRecord(
                record_id=record_id,
                schema_version=schema_version,
                revision=self.revision_of(raw),
                created_at=self.created_at_of(raw),
                updated_at=self.updated_at_of(raw),
                checksum=_checksum(raw),
                payload=raw,
            )
        except StorageSchemaUnsupported:
            raise
        except Exception as exc:
            if isinstance(exc, StorageCorrupted):
                raise
            raise StorageCorrupted(
                "Storage record is corrupted",
                details={"record_id": self._safe_id(path.stem)},
            ) from exc

    def _path(self, record_id: str) -> Path:
        _validate_identifier(record_id, kind="record")
        candidate = (self.root / f"{record_id}{self.suffix}").resolve(strict=False)
        if candidate.parent != self.root or _contains_symlink(candidate, self.root):
            raise StoragePathInvalid("Storage record path is outside the collection")
        return candidate

    def _restore_backup(self, path: Path) -> bool:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            return False
        _load_structured(backup)
        shutil.copy2(backup, path)
        self._read_path(path, migrate=True)
        return True

    def _quarantine(self, path: Path) -> None:
        quarantine = (self.root / ".quarantine").resolve(strict=False)
        if quarantine.parent != self.root:
            raise StoragePathInvalid("Storage quarantine path is invalid")
        quarantine.mkdir(parents=True, exist_ok=True)
        destination = (
            quarantine / f"{path.name}.{hashlib.sha256(path.name.encode()).hexdigest()[:12]}"
        )
        os.replace(path, destination)

    def _emit(self, event_type: str, record_id: str | None, metadata: dict[str, Any]) -> None:
        if self.events is None:
            return
        payload = {"collection_id": self.collection_id, **metadata}
        if record_id is not None:
            payload["record_id"] = self._safe_id(record_id)
        self.events.emit(event_type, "storage", payload)

    def _safe_id(self, record_id: str) -> str:
        if not self.sensitive_record_ids:
            return record_id
        return hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:16]


def _validate_identifier(value: str, *, kind: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise StoragePathInvalid(f"Storage {kind} identifier is invalid")


def _contains_symlink(path: Path, root: Path) -> bool:
    current = root
    for part in path.relative_to(root).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return path.exists() and path.is_symlink()


def _load_structured(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        try:
            import yaml

            value = yaml.safe_load(text)
        except ImportError:
            value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Storage record must be an object")
        return value
    except Exception as exc:
        raise StorageReadFailed("Storage record read failed", details={"file": path.name}) from exc


def _dump_structured(payload: Mapping[str, Any]) -> str:
    try:
        import yaml

        return yaml.safe_dump(dict(payload), sort_keys=True, allow_unicode=True)
    except Exception:
        return json.dumps(dict(payload), indent=2, sort_keys=True)


def _checksum(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _matches(payload: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    return all(payload.get(key) == value for key, value in filters.items())


def _sort_value(record: CollectionRecord, sort: str) -> str:
    return record.record_id if sort == "record_id" else getattr(record, sort)


def _encode_cursor(record: CollectionRecord, sort: str, descending: bool) -> str:
    raw = json.dumps(
        {
            "v": 1,
            "sort": sort,
            "descending": descending,
            "value": _sort_value(record, sort),
            "record_id": record.record_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if (
            raw.get("v") != 1
            or raw.get("sort") not in {"record_id", "created_at", "updated_at"}
            or not isinstance(raw.get("descending"), bool)
            or not isinstance(raw.get("value"), str)
            or not isinstance(raw.get("record_id"), str)
        ):
            raise ValueError("invalid cursor")
        return raw
    except Exception as exc:
        raise StorageCursorInvalid("Storage cursor is invalid") from exc


def _after_cursor(
    record: CollectionRecord,
    sort: str,
    descending: bool,
    cursor: Mapping[str, Any],
) -> bool:
    value = (_sort_value(record, sort), record.record_id)
    boundary = (str(cursor["value"]), str(cursor["record_id"]))
    return value < boundary if descending else value > boundary


def _now() -> str:
    return datetime.now(UTC).isoformat()
