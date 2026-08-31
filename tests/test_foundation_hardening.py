from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.serialization import dump_structured_file, load_structured_file


def runtime_in_tempdir():
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
    for relative_path in [
        "config/permissions.yaml",
        "config/system.yaml",
        "agents/orchestrator/CONFIG.yaml",
    ]:
        source = source_data / relative_path
        target = settings.data_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    system_path = settings.data_dir / "config" / "system.yaml"
    system = load_structured_file(system_path)
    system.setdefault("system", {})["default_agent_id"] = "orchestrator"
    dump_structured_file(system_path, system)
    runtime = create_runtime(settings)
    return directory, runtime


class FoundationHardeningTests(unittest.TestCase):
    def test_context_loader_loads_files_in_required_order(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        project_dir = runtime.data_dir.resolve("projects/project-a")
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "PROJECT.md").write_text("# Project A\n", encoding="utf-8")
        (project_dir / "MEMORY.md").write_text("# Project A Memory\n", encoding="utf-8")
        task = runtime.tasks.create_task(
            context,
            "Relevant Task",
            metadata={"agent_id": "orchestrator", "project_id": "project-a"},
        )

        loaded = runtime.context_loader.load(
            context,
            agent_id="orchestrator",
            project_id="project-a",
            history=[{"role": "user", "content": "latest session excerpt"}],
        )

        sources = [getattr(section, "source", None) for section in loaded.sections]
        self.assertEqual(
            sources[:9],
            [
                "memory/SYSTEM.md",
                "memory/USER.md",
                "memory/MEMORY.md",
                "agents/orchestrator/SOUL.md",
                "agents/orchestrator/MEMORY.md",
                "agents/orchestrator/SKILLS.md",
                "projects/project-a/PROJECT.md",
                "projects/project-a/MEMORY.md",
                f"tasks/active/{task.id}.json",
            ],
        )
        self.assertEqual(loaded.history[0].content, "latest session excerpt")
        self.assertEqual(loaded.sections[-1].order, 9)

    def test_context_loader_keeps_chat_history_out_of_memory(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        loaded = runtime.context_loader.load(
            context,
            agent_id="orchestrator",
            history=["transient chat snippet"],
        )

        memory_text = "\n".join(section.content for section in loaded.memory)
        self.assertNotIn("transient chat snippet", memory_text)
        self.assertEqual(loaded.history[0].content, "transient chat snippet")

    def test_agent_message_starts_pending_and_is_structured(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        message = runtime.communication.send_agent_message(
            context,
            from_agent_id="orchestrator",
            to_agent_id="orchestrator",
            subject="Structured message",
            body="Check structured state.",
        )

        self.assertEqual(message.status, "pending")
        message_path = runtime.data_dir.resolve(f"agents/orchestrator/messages/{message.id}.yaml")
        self.assertTrue(message_path.exists())

        messages = runtime.communication.list_messages(context, "orchestrator", status="pending")
        self.assertEqual(messages[0].id, message.id)
        self.assertEqual(messages[0].subject, "Structured message")

    def test_agent_message_status_transitions_emit_events(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        message = runtime.communication.send_agent_message(
            context,
            from_agent_id="orchestrator",
            to_agent_id="orchestrator",
            subject="Status message",
            body="Check transitions.",
        )

        read = runtime.communication.mark_read(context, "orchestrator", message.id)
        processed = runtime.communication.mark_processed(context, "orchestrator", message.id)
        failed = runtime.communication.mark_failed(context, "orchestrator", message.id)

        self.assertEqual(read.status, "read")
        self.assertEqual(processed.status, "processed")
        self.assertEqual(failed.status, "failed")
        events = [
            event
            for event in runtime.events.tail(limit=50)
            if event.type == "agent.message.status_changed"
            and event.payload["id"] == message.id
        ]
        self.assertEqual([event.payload["to_status"] for event in events], ["read", "processed", "failed"])

    def test_command_runtime_call_creates_real_agent_message(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        result = runtime.commands.execute(context, "/call orchestrator hello from command")

        self.assertEqual(result.status, "ok")
        message_id = result.data["message"]["id"]
        messages = runtime.communication.list_messages(context, "orchestrator")
        self.assertIn(message_id, {message.id for message in messages})
        inbox = runtime.data_dir.resolve("agents/orchestrator/INBOX.md").read_text(encoding="utf-8")
        self.assertIn("hello from command", inbox)

    def test_command_runtime_task_creates_real_task(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        context = runtime.context()
        result = runtime.commands.execute(context, "/task Harden foundation --agent orchestrator")

        self.assertEqual(result.status, "ok")
        task_id = result.data["task"]["id"]
        task_path = runtime.data_dir.resolve(f"tasks/active/{task_id}.json")
        self.assertTrue(task_path.exists())
        task = runtime.tasks.get_task(task_id)
        self.assertEqual(task.metadata["agent_id"], "orchestrator")

    def test_device_registry_registers_trusted_and_revoked_devices(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        trusted = runtime.devices.register_device(
            "arthur_phone",
            trusted=True,
            permissions=["approve_actions", "view_notifications"],
            actor_id="local_owner",
        )
        self.assertTrue(trusted.trusted)
        self.assertFalse(trusted.revoked)
        trusted_path = runtime.data_dir.resolve("devices/trusted/arthur_phone.yaml")
        self.assertTrue(trusted_path.exists())

        revoked = runtime.devices.revoke_device("arthur_phone", actor_id="local_owner")
        self.assertFalse(revoked.trusted)
        self.assertTrue(revoked.revoked)
        self.assertFalse(trusted_path.exists())
        self.assertTrue(runtime.data_dir.resolve("devices/revoked/arthur_phone.yaml").exists())

    def test_device_permissions_are_persisted(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.devices.register_device(
            "wall_tablet",
            trusted=False,
            permissions=["view_notifications", "view_cameras"],
            actor_id="local_owner",
        )

        loaded = runtime.devices.get_device("wall_tablet")
        self.assertEqual(loaded.permissions, ["view_notifications", "view_cameras"])
        record_text = runtime.data_dir.resolve("devices/untrusted/wall_tablet.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("view_notifications", record_text)
        self.assertIn("view_cameras", record_text)

    def test_structured_write_retries_transient_windows_replace_denial(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "presence" / "synapse.yaml"
        attempts = 0
        original_replace = __import__("os").replace

        def flaky_replace(source: str | Path, target: str | Path) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError("transient access denied")
            original_replace(source, target)

        with patch("synapse.core.serialization.os.replace", flaky_replace):
            dump_structured_file(path, {"agent_id": "synapse", "state": "thinking"})

        self.assertEqual(load_structured_file(path)["state"], "thinking")
        self.assertEqual(attempts, 2)


if __name__ == "__main__":
    unittest.main()
