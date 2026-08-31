from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from synapse.storage.errors import StorageMigrationFailed, StorageSchemaUnsupported

Migration = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class MigrationRegistry:
    def __init__(self) -> None:
        self._migrations: dict[int, tuple[int, Migration]] = {}

    def register(self, from_version: int, to_version: int, migration: Migration) -> None:
        if from_version < 0 or to_version != from_version + 1:
            raise ValueError("Storage migrations must be positive sequential steps")
        if from_version in self._migrations:
            raise ValueError(f"Migration already registered from schema {from_version}")
        self._migrations[from_version] = (to_version, migration)

    def migrate(
        self,
        payload: Mapping[str, Any],
        from_version: int,
        to_version: int,
    ) -> Mapping[str, Any]:
        if from_version > to_version:
            raise StorageSchemaUnsupported("Storage schema downgrade is not supported")
        current = dict(payload)
        version = from_version
        while version < to_version:
            step = self._migrations.get(version)
            if step is None:
                raise StorageSchemaUnsupported(
                    f"No storage migration registered from schema {version}"
                )
            next_version, migration = step
            try:
                current = dict(migration(current))
            except Exception as exc:
                raise StorageMigrationFailed(
                    f"Storage migration failed at schema {version}"
                ) from exc
            version = next_version
        return current
