from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.migrations.models import MigrationHistoryEntry, MigrationStatus
from synapse.migrations.registry import MigrationRegistry


class MigrationRuntime:
    def __init__(self, data_dir: DataDir, registry: MigrationRegistry):
        self.data_dir = data_dir
        self.registry = registry
        self._root().mkdir(parents=True, exist_ok=True)

    def get_record_version(self, record: dict[str, Any]) -> int:
        value = record.get("schema_version", 1)
        try:
            version = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Invalid schema_version: {value}") from exc
        if version < 1:
            raise ValidationError(f"Invalid schema_version: {version}")
        return version

    def migrate_record(
        self,
        record_type: str,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        current = self.get_record_version(record)
        target = self.registry.current_version(record_type)
        if current > target:
            raise ValidationError(
                f"Cannot downgrade {record_type}: record version {current} "
                f"is newer than runtime version {target}"
            )
        migrated = dict(record)
        while current < target:
            migration = self.registry.migration_for(record_type, current)
            migrated = migration.migrate(dict(migrated))
            next_version = self.get_record_version(migrated)
            if next_version != migration.to_version:
                raise ValidationError(
                    f"Migration {record_type} {migration.from_version}->{migration.to_version} "
                    f"returned version {next_version}"
                )
            current = next_version
        migrated.setdefault("record_type", record_type)
        migrated["schema_version"] = target
        return migrated

    def migrate_file(self, path: Path, record_type: str) -> dict[str, Any]:
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        record = load_structured_file(path)
        from_version = self.get_record_version(record)
        target = self.registry.current_version(record_type)
        try:
            migrated = self.migrate_record(record_type, record)
            if migrated != record:
                dump_structured_file(path, migrated)
            self._record_history(
                MigrationHistoryEntry(
                    record_type=record_type,
                    path=str(path),
                    from_version=from_version,
                    to_version=target,
                    status="completed",
                )
            )
            return migrated
        except Exception as exc:
            if original:
                path.write_text(original, encoding="utf-8")
            self._record_history(
                MigrationHistoryEntry(
                    record_type=record_type,
                    path=str(path),
                    from_version=from_version,
                    to_version=target,
                    status="failed",
                    error=str(exc) or type(exc).__name__,
                )
            )
            raise

    def check_file(self, path: Path, record_type: str) -> dict[str, Any]:
        record = load_structured_file(path)
        version = self.get_record_version(record)
        target = self.registry.current_version(record_type)
        return {
            "path": str(path),
            "record_type": record_type,
            "schema_version": version,
            "target_version": target,
            "needs_migration": version < target,
            "is_newer_than_runtime": version > target,
        }

    def list_migrations(self) -> list[dict[str, Any]]:
        return self.registry.list_migrations()

    def migration_status(self) -> MigrationStatus:
        last = self._last_history()
        status = MigrationStatus(
            current_versions=self.registry.current_versions(),
            migrations_available=len(self.list_migrations()),
            last_history=last,
        )
        dump_structured_file(self._status_path(), asdict(status))
        return status

    def _record_history(self, entry: MigrationHistoryEntry) -> None:
        payload = asdict(entry)
        self._history_path().parent.mkdir(parents=True, exist_ok=True)
        with self._history_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self.migration_status()

    def _last_history(self) -> dict[str, Any] | None:
        path = self._history_path()
        if not path.exists():
            return None
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])

    def _root(self) -> Path:
        return self.data_dir.resolve("migrations")

    def _history_path(self) -> Path:
        return self.data_dir.resolve("migrations/history.jsonl")

    def _status_path(self) -> Path:
        return self.data_dir.resolve("migrations/status.yaml")
