from __future__ import annotations

from typing import Any


class StorageError(Exception):
    code = "storage_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class StorageRecordNotFound(StorageError):
    code = "storage_record_not_found"


class StorageRevisionConflict(StorageError):
    code = "storage_revision_conflict"


class StorageSchemaUnsupported(StorageError):
    code = "storage_schema_unsupported"


class StorageMigrationFailed(StorageError):
    code = "storage_migration_failed"


class StorageCorrupted(StorageError):
    code = "storage_corrupted"


class StorageLockTimeout(StorageError):
    code = "storage_lock_timeout"


class StorageWriteFailed(StorageError):
    code = "storage_write_failed"


class StorageReadFailed(StorageError):
    code = "storage_read_failed"


class StorageRecoveryFailed(StorageError):
    code = "storage_recovery_failed"


class StorageCursorInvalid(StorageError):
    code = "storage_cursor_invalid"


class StorageRetentionFailed(StorageError):
    code = "storage_retention_failed"


class StoragePathInvalid(StorageError):
    code = "storage_path_invalid"
