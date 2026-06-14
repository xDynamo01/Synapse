from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.core.permissions import PermissionContext


def runtime_in_tempdir(permissions_text: str | None = None):
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    source_data = PROJECT_ROOT / "data"
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=root / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    runtime = create_runtime(settings)
    permissions_source = source_data / "config" / "permissions.yaml"
    permissions_target = settings.data_dir / "config" / "permissions.yaml"
    permissions_target.write_text(
        permissions_text or permissions_source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    system_source = source_data / "config" / "system.yaml"
    system_target = settings.data_dir / "config" / "system.yaml"
    system_target.write_text(system_source.read_text(encoding="utf-8"), encoding="utf-8")
    agent_source = source_data / "agents" / "orchestrator" / "CONFIG.yaml"
    agent_target = settings.data_dir / "agents" / "orchestrator" / "CONFIG.yaml"
    agent_target.write_text(agent_source.read_text(encoding="utf-8"), encoding="utf-8")
    runtime = create_runtime(settings)
    return directory, runtime


class RuntimeFoundationTests(unittest.TestCase):
    def test_data_dir_bootstrap_creates_required_shape(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        for relative_path in [
            "config",
            "memory",
            "agents",
            "tasks/active",
            "tasks/completed",
            "tasks/failed",
            "devices/trusted",
            "devices/untrusted",
            "devices/revoked",
        ]:
            self.assertTrue(runtime.data_dir.resolve(relative_path).exists())

        self.assertTrue(runtime.data_dir.resolve("memory/USER.md").exists())
        self.assertTrue(runtime.data_dir.resolve("agents/orchestrator/INBOX.md").exists())

    def test_permission_manager_blocks_unauthorized_tool(self) -> None:
        directory, runtime = runtime_in_tempdir(
            permissions_text='{"subjects":{"limited_user":["filesystem.write"]}}'
        )
        self.addCleanup(directory.cleanup)

        denied = PermissionContext(actor_id="limited_user", actor_type="user")
        with self.assertRaises(PermissionDenied):
            runtime.tools.execute("read_file", denied, {"path": "memory/USER.md"})

        permission_events = [
            event
            for event in runtime.events.tail(limit=20)
            if event.type == "permission.decision"
            and event.payload["permission"] == "filesystem.read"
        ]
        self.assertEqual(permission_events[-1].payload["allowed"], False)

    def test_filesystem_tools_are_scoped_to_data_dir(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        runtime.tools.execute(
            "write_file",
            context,
            {"path": "projects/demo.md", "content": "hello synapse"},
        )
        read = runtime.tools.execute("read_file", context, {"path": "projects/demo.md"})
        self.assertEqual(read["content"], "hello synapse")

        results = runtime.tools.execute(
            "search_files",
            context,
            {"path": "projects", "pattern": "*.md", "query": "synapse"},
        )
        self.assertEqual(len(results["results"]), 1)

        with self.assertRaises(ValidationError):
            runtime.tools.execute("read_file", context, {"path": "../outside.txt"})

    def test_read_file_blocks_absolute_path_outside_data_dir(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        outside_file = Path(directory.name) / "outside.txt"
        outside_file.write_text("outside", encoding="utf-8")

        with self.assertRaises(ValidationError):
            runtime.tools.execute("read_file", context, {"path": str(outside_file)})

    def test_send_agent_message_persists_message_and_event(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        message = runtime.tools.execute(
            "send_agent_message",
            context,
            {
                "from_agent_id": "orchestrator",
                "to_agent_id": "orchestrator",
                "body": "Record startup state.",
            },
        )
        inbox = runtime.data_dir.resolve("agents/orchestrator/INBOX.md").read_text(encoding="utf-8")
        self.assertIn(message["id"], inbox)
        self.assertIn("Record startup state.", inbox)

        message_events = [
            event
            for event in runtime.events.tail(limit=50)
            if event.type == "agent.message.sent"
            and event.payload["id"] == message["id"]
        ]
        self.assertEqual(len(message_events), 1)

    def test_create_task_persists_task_and_event(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()

        created = runtime.tools.execute(
            "create_task",
            context,
            {"title": "Bootstrap Synapse", "description": "Create runtime foundation."},
        )
        active_path = runtime.data_dir.resolve(f"tasks/active/{created['id']}.json")
        self.assertTrue(active_path.exists())
        self.assertIn('"title": "Bootstrap Synapse"', active_path.read_text(encoding="utf-8"))

        task_events = [
            event
            for event in runtime.events.tail(limit=50)
            if event.type == "task.created" and event.payload["id"] == created["id"]
        ]
        self.assertEqual(len(task_events), 1)

    def test_task_lifecycle_moves_persisted_file_between_status_directories(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        created = runtime.tools.execute(
            "create_task",
            context,
            {"title": "Bootstrap Synapse", "description": "Create runtime foundation."},
        )
        active_path = runtime.data_dir.resolve(f"tasks/active/{created['id']}.json")

        updated = runtime.tools.execute(
            "update_task",
            context,
            {"task_id": created["id"], "status": "completed", "note": "Verified by test."},
        )
        completed_path = runtime.data_dir.resolve(f"tasks/completed/{updated['id']}.json")
        self.assertTrue(completed_path.exists())
        self.assertFalse(active_path.exists())

    def test_memory_store_reads_global_and_agent_memory_from_data_dir(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        runtime.data_dir.resolve("memory/USER.md").write_text(
            "# User Memory\n\nUser-memory-marker\n",
            encoding="utf-8",
        )
        runtime.data_dir.resolve("agents/orchestrator/MEMORY.md").write_text(
            "# Orchestrator Memory\n\nAgent-memory-marker\n",
            encoding="utf-8",
        )

        self.assertIn("User-memory-marker", runtime.memory.read_global(context, "USER.md"))
        self.assertIn(
            "Agent-memory-marker",
            runtime.memory.read_agent_memory(context, "orchestrator"),
        )

    def test_api_task_endpoint_delegates_to_runtime(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover - documents optional API dependency gaps.
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        @dataclass(frozen=True)
        class FakeRuntimeTask:
            id: str
            title: str
            description: str
            status: str
            created_by: str
            metadata: dict[str, str]
            created_at: str
            updated_at: str

        class FakeTasks:
            def __init__(self) -> None:
                self.calls: list[tuple[PermissionContext, str, str, dict[str, str]]] = []

            def create_task(
                self,
                context: PermissionContext,
                title: str,
                description: str,
                metadata: dict[str, str],
            ) -> FakeRuntimeTask:
                self.calls.append((context, title, description, metadata))
                return FakeRuntimeTask(
                    id="runtime-task-id",
                    title=title,
                    description=description,
                    status="active",
                    created_by=context.actor_id,
                    metadata=metadata,
                    created_at="2026-06-14T00:00:00Z",
                    updated_at="2026-06-14T00:00:00Z",
                )

        class FakeRuntime:
            def __init__(self) -> None:
                self.tasks = FakeTasks()

            def context(self, actor_id: str | None = None, actor_type: str = "user"):
                return PermissionContext(actor_id=actor_id or "fallback", actor_type=actor_type)

        fake_runtime = FakeRuntime()
        app = FastAPI()
        app.state.runtime = fake_runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/tasks",
            headers={"x-actor-id": "api-user", "x-actor-type": "user"},
            json={"title": "From API", "description": "delegate", "metadata": {"k": "v"}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "runtime-task-id")
        self.assertEqual(len(fake_runtime.tasks.calls), 1)
        context, title, description, metadata = fake_runtime.tasks.calls[0]
        self.assertEqual(context.actor_id, "api-user")
        self.assertEqual(title, "From API")
        self.assertEqual(description, "delegate")
        self.assertEqual(metadata, {"k": "v"})


if __name__ == "__main__":
    unittest.main()
