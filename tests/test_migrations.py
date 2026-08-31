from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.migrations.registry import MigrationRegistry
from synapse.migrations.runtime import MigrationRuntime


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Migration Test",
            "mode": "test",
            "default_agent_id": "orchestrator",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    return directory, settings, create_runtime(settings)


def migration_runtime(root: Path) -> MigrationRuntime:
    from synapse.core.data_dir import DataDir

    data_dir = DataDir(root)
    data_dir.bootstrap()
    registry = MigrationRegistry()
    registry.register_record_type("example", 1)
    return MigrationRuntime(data_dir, registry)


class MigrationRuntimeTests(unittest.TestCase):
    def test_register_migration(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        runtime = migration_runtime(Path(directory.name) / "data")

        runtime.registry.register(
            "example",
            1,
            2,
            lambda record: {**record, "schema_version": 2, "field": "migrated"},
        )

        migrations = runtime.list_migrations()
        self.assertEqual(len(migrations), 1)
        self.assertEqual(migrations[0]["record_type"], "example")

    def test_migrate_record_v1_to_v2(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        runtime = migration_runtime(Path(directory.name) / "data")
        runtime.registry.register(
            "example",
            1,
            2,
            lambda record: {**record, "schema_version": 2, "field": "migrated"},
        )

        migrated = runtime.migrate_record("example", {"schema_version": 1})

        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["field"], "migrated")

    def test_error_when_no_path_exists(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        runtime = migration_runtime(Path(directory.name) / "data")
        runtime.registry.register_record_type("example", 2)

        with self.assertRaisesRegex(ValidationError, "No migration path"):
            runtime.migrate_record("example", {"schema_version": 1})

    def test_prevent_downgrade(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        runtime = migration_runtime(Path(directory.name) / "data")

        with self.assertRaisesRegex(ValidationError, "Cannot downgrade"):
            runtime.migrate_record("example", {"schema_version": 2})

    def test_migrate_file_preserves_file_when_migration_fails(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        runtime = migration_runtime(Path(directory.name) / "data")
        runtime.registry.register(
            "example",
            1,
            2,
            lambda record: (_ for _ in ()).throw(ValidationError("boom")),
        )
        path = Path(directory.name) / "data" / "records" / "item.yaml"
        dump_structured_file(path, {"schema_version": 1, "value": "original"})
        original = path.read_text(encoding="utf-8")

        with self.assertRaisesRegex(ValidationError, "boom"):
            runtime.migrate_file(path, "example")

        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_history_and_status_are_written(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        runtime = migration_runtime(Path(directory.name) / "data")
        runtime.registry.register(
            "example",
            1,
            2,
            lambda record: {**record, "schema_version": 2},
        )
        path = Path(directory.name) / "data" / "records" / "item.yaml"
        dump_structured_file(path, {"schema_version": 1})

        runtime.migrate_file(path, "example")

        history = Path(directory.name) / "data" / "migrations" / "history.jsonl"
        status = Path(directory.name) / "data" / "migrations" / "status.yaml"
        self.assertTrue(history.exists())
        self.assertTrue(status.exists())
        self.assertIn('"status": "completed"', history.read_text(encoding="utf-8"))
        self.assertEqual(load_structured_file(status)["migrations_available"], 1)

    def test_migrations_command(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), "/migrations")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["migrations"]["current_versions"]["job"], 1)
        self.assertEqual(result.data["migrations"]["migrations_available"], 0)

    def test_migrations_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).get("/api/migrations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_versions"]["approval"], 1)


if __name__ == "__main__":
    unittest.main()
