from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.core.exceptions import ValidationError
from synapse.migrations.models import MigrationDefinition, MigrationFunction


class MigrationRegistry:
    def __init__(self) -> None:
        self._current_versions: dict[str, int] = {}
        self._migrations: dict[tuple[str, int], MigrationDefinition] = {}

    def register_record_type(self, record_type: str, current_version: int) -> None:
        if current_version < 1:
            raise ValidationError("Schema version must be >= 1")
        existing = self._current_versions.get(record_type)
        if existing is not None and current_version < existing:
            raise ValidationError(
                f"Cannot downgrade registered schema for {record_type}: "
                f"{existing} -> {current_version}"
            )
        self._current_versions[record_type] = current_version

    def register(
        self,
        record_type: str,
        from_version: int,
        to_version: int,
        migrate: MigrationFunction,
    ) -> None:
        if to_version <= from_version:
            raise ValidationError(
                f"Migration must upgrade schema: {record_type} {from_version}->{to_version}"
            )
        key = (record_type, from_version)
        if key in self._migrations:
            raise ValidationError(
                f"Migration already registered: {record_type} from {from_version}"
            )
        self._migrations[key] = MigrationDefinition(
            record_type=record_type,
            from_version=from_version,
            to_version=to_version,
            migrate=migrate,
        )
        if self._current_versions.get(record_type, 0) < to_version:
            self._current_versions[record_type] = to_version

    def current_version(self, record_type: str) -> int:
        version = self._current_versions.get(record_type)
        if version is None:
            raise ValidationError(f"Unknown record type: {record_type}")
        return version

    def migration_for(self, record_type: str, from_version: int) -> MigrationDefinition:
        migration = self._migrations.get((record_type, from_version))
        if not migration:
            raise ValidationError(
                f"No migration path for {record_type} from version {from_version}"
            )
        return migration

    def list_migrations(self) -> list[dict[str, Any]]:
        return [
            asdict(migration) | {"migrate": migration.migrate.__name__}
            for migration in sorted(
                self._migrations.values(),
                key=lambda item: (item.record_type, item.from_version, item.to_version),
            )
        ]

    def current_versions(self) -> dict[str, int]:
        return dict(sorted(self._current_versions.items()))
