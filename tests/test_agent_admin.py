from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.agents.provisioning import AgentCreateRequest
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError


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
            "agent:managed": ["agents.message"],
            "agent:sender": ["agents.message"],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Agent Admin Test",
            "mode": "test",
            "default_agent_id": "managed",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    runtime = create_runtime(settings)
    runtime.provisioning.create_agent(
        AgentCreateRequest(agent_id="managed", display_name="Managed", role="assistant")
    )
    runtime.provisioning.create_agent(
        AgentCreateRequest(agent_id="sender", display_name="Sender", role="assistant")
    )
    return directory, settings, runtime


class AgentAdminRuntimeTests(unittest.TestCase):
    def test_list_agents(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        entries = runtime.admin.list_agents()

        self.assertTrue(any(entry.agent_id == "managed" for entry in entries))

    def test_admin_status(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        status = runtime.admin.get_agent_admin_status("managed")

        self.assertEqual(status.status, "active")
        self.assertFalse(status.is_archived)

    def test_deactivate_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.admin.deactivate_agent("managed")

        self.assertEqual(result.status, "inactive")
        self.assertEqual(runtime.presence.get("managed").state, "offline")

    def test_activate_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.deactivate_agent("managed")

        result = runtime.admin.activate_agent("managed")

        self.assertEqual(result.status, "active")

    def test_archive_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.admin.archive_agent("managed")

        self.assertTrue(result.is_archived)
        self.assertFalse(any(entry.agent_id == "managed" for entry in runtime.admin.list_agents()))
        self.assertTrue(any(entry.agent_id == "managed" for entry in runtime.admin.list_agents(True)))

    def test_restore_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.archive_agent("managed")

        result = runtime.admin.restore_agent("managed")

        self.assertFalse(result.is_archived)
        self.assertTrue(any(entry.agent_id == "managed" for entry in runtime.admin.list_agents()))

    def test_delete_requires_inactive_agent_and_strong_confirmation(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with self.assertRaisesRegex(ValidationError, "deactivated"):
            runtime.admin.delete_agent("managed", "DELETE managed", runtime.context())
        runtime.admin.deactivate_agent("managed")
        with self.assertRaisesRegex(ValidationError, "confirmation"):
            runtime.admin.delete_agent("managed", "delete managed", runtime.context())

        result = runtime.admin.delete_agent("managed", "DELETE managed", runtime.context())

        self.assertTrue(result.deleted)
        self.assertFalse((settings.data_dir / "agents" / "managed").exists())

    def test_delete_blocks_dependencies_unless_force_is_explicit(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.deactivate_agent("managed")
        write_json(
            settings.data_dir / "tasks" / "active" / "dependent.json",
            {"id": "dependent", "agent_id": "managed"},
        )

        with self.assertRaisesRegex(ValidationError, "dependent records"):
            runtime.admin.delete_agent("managed", "DELETE managed", runtime.context())

        result = runtime.admin.delete_agent(
            "managed", "DELETE managed", runtime.context(), force=True
        )
        self.assertEqual(result.dependencies, ["tasks"])

    def test_delete_rolls_back_when_staged_removal_fails(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.deactivate_agent("managed")
        original = shutil.rmtree

        def fail_removal(*_args, **_kwargs):
            raise OSError("removal failed")

        shutil.rmtree = fail_removal
        self.addCleanup(setattr, shutil, "rmtree", original)

        with self.assertRaisesRegex(ValidationError, "rolled back"):
            runtime.admin.delete_agent("managed", "DELETE managed", runtime.context())

        self.assertTrue((settings.data_dir / "agents" / "managed" / "CONFIG.yaml").exists())

    def test_archive_preserves_agent_files_while_delete_removes_them(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.archive_agent("managed")
        self.assertTrue((settings.data_dir / "agents" / "managed" / "CONFIG.yaml").exists())
        runtime.admin.deactivate_agent("managed")

        runtime.admin.delete_agent("managed", "DELETE managed", runtime.context())

        self.assertFalse((settings.data_dir / "agents" / "managed").exists())

    def test_chat_blocked_for_archived_or_inactive_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.deactivate_agent("managed")

        with self.assertRaises(ValidationError):
            runtime.chat.send_message(runtime.context(), "managed", "hello")

        runtime.admin.activate_agent("managed")
        runtime.admin.archive_agent("managed")
        with self.assertRaises(ValidationError):
            runtime.chat.send_message(runtime.context(), "managed", "hello")

    def test_worker_blocked_for_archived_or_inactive_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="sender",
            to_agent_id="managed",
            body="Process this",
        )
        runtime.admin.deactivate_agent("managed")

        with self.assertRaises(ValidationError):
            runtime.worker.process_inbox(runtime.context(), "managed")

    def test_new_agent_starts_active(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        status = runtime.admin.get_agent_admin_status("managed")

        self.assertEqual(status.status, "active")
        self.assertFalse(status.is_archived)

    def test_admin_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        directory_result = runtime.commands.execute(runtime.context(), "/agent-directory")
        admin_result = runtime.commands.execute(runtime.context(), "/agent-admin managed")
        deactivated = runtime.commands.execute(runtime.context(), "/deactivate-agent managed")
        activated = runtime.commands.execute(runtime.context(), "/activate-agent managed")
        archived = runtime.commands.execute(runtime.context(), "/archive-agent managed")
        restored = runtime.commands.execute(runtime.context(), "/restore-agent managed")
        runtime.commands.execute(runtime.context(), "/deactivate-agent managed")
        deleted = runtime.commands.execute(
            runtime.context(), '/delete-agent managed "DELETE managed"'
        )

        self.assertEqual(directory_result.status, "ok")
        self.assertEqual(admin_result.status, "ok")
        self.assertEqual(deactivated.status, "ok")
        self.assertEqual(activated.status, "ok")
        self.assertEqual(archived.status, "ok")
        self.assertEqual(restored.status, "ok")
        self.assertEqual(deleted.status, "ok")

    def test_admin_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        listed = client.get("/api/agent-directory")
        status = client.get("/api/agents/managed/admin")
        deactivated = client.post("/api/agents/managed/deactivate")
        activated = client.post("/api/agents/managed/activate")
        archived = client.post("/api/agents/managed/archive")
        restored = client.post("/api/agents/managed/restore")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(deactivated.status_code, 200)
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(restored.status_code, 200)

        deactivated_again = client.post("/api/agents/managed/deactivate")
        deleted = client.request(
            "DELETE",
            "/api/agents/managed",
            json={"confirmation": "DELETE managed"},
        )
        self.assertEqual(deactivated_again.status_code, 200)
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])


if __name__ == "__main__":
    unittest.main()
