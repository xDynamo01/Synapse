from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import (
    seed_agent_identity_files,
    seed_delegation_pair,
    seed_invalid_agent,
    seed_test_agent,
)
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file


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
            "agent:artemis": ["*"],
            "agent:researcher": [
                "filesystem.read",
                "filesystem.write",
                "filesystem.list",
                "agents.message",
                "tasks.create",
            ],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Identity Test",
            "mode": "test",
            "default_agent_id": "artemis",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    (settings.data_dir / "config" / "permissions.yaml").write_text(
        json.dumps(permissions, indent=2),
        encoding="utf-8",
    )
    (settings.data_dir / "config" / "system.yaml").write_text(
        json.dumps(system, indent=2),
        encoding="utf-8",
    )
    seed_delegation_pair(
        settings.data_dir,
        delegator_extra={
            "default_model": "mock/synapse-test",
            "permissions": ["*"],
            "preferred_tools": ["create_task", "send_agent_message"],
        },
        delegate_extra={
            "permissions": permissions["subjects"]["agent:researcher"],
            "forbidden_tools": ["write_file"],
        },
    )
    seed_agent_identity_files(
        settings.data_dir,
        "artemis",
        soul="# Artemis\n\nCoordinates planning and delegation.\n",
        skills="# Skills\n\n- planning\n- briefings\n",
        memory="# Artemis Memory\n",
        inbox="# Inbox\n",
    )
    seed_agent_identity_files(
        settings.data_dir,
        "researcher",
        soul="# Researcher\n\nResearch specialist.\n",
        skills="# Skills\n\n- research\n",
        memory="# Researcher Memory\n",
        inbox="# Inbox\n",
    )
    return directory, create_runtime(settings)


class AgentIdentityTests(unittest.TestCase):
    def test_agent_identity_loads_soul_skills_and_config(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        identity = runtime.identities.load_identity("artemis")

        self.assertEqual(identity.id, "artemis")
        self.assertEqual(identity.name, "Artemis")
        self.assertIn("Coordinates planning", identity.soul)
        self.assertIn("briefings", identity.skills)
        self.assertEqual(identity.default_model, "mock/synapse-test")

    def test_artemis_identity_is_orchestrator_and_can_delegate(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        identity = runtime.identities.load_identity("artemis")

        self.assertEqual(identity.role, "orchestrator")
        self.assertTrue(identity.can_delegate)
        self.assertIn("create_task", identity.preferred_tools)
        self.assertIn("send_agent_message", identity.preferred_tools)

    def test_researcher_identity_is_specialist_and_cannot_delegate(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        identity = runtime.identities.load_identity("researcher")

        self.assertEqual(identity.role, "research_specialist")
        self.assertFalse(identity.can_delegate)
        self.assertIn("write_file", identity.forbidden_tools)

    def test_forbidden_tool_is_blocked_before_tool_router(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "researcher",
            "tool:write_file path=projects/forbidden.txt content=no",
        )

        tool_result = result.message.metadata["tool_results"][0]
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertEqual(tool_result["status"], "blocked")
        self.assertFalse(tool_result["success"])
        self.assertIn("Tool is forbidden", tool_result["error"])
        self.assertFalse(runtime.data_dir.resolve("projects/forbidden.txt").exists())
        self.assertNotIn("tool.requested", event_types)
        self.assertNotIn("approval.requested", event_types)

    def test_preferred_tools_appear_in_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(runtime.context(), "artemis", "hello")

        self.assertIn("agent_identity", result.context)
        self.assertEqual(
            result.context["agent_identity"]["preferred_tools"],
            ["create_task", "send_agent_message"],
        )

    def test_context_loader_includes_agent_identity(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        loaded = runtime.context_loader.load(runtime.context(), "researcher")

        self.assertEqual(loaded.agent_identity["id"], "researcher")
        self.assertEqual(loaded.agent_identity["role"], "research_specialist")

    def test_agent_command_returns_structured_identity(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), "/agent Artemis")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["agent"]["id"], "artemis")
        self.assertEqual(result.data["agent"]["role"], "orchestrator")
        self.assertTrue(result.data["agent"]["can_delegate"])

    def test_optional_identity_files_can_be_absent(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = Settings(
            project_root=PROJECT_ROOT,
            data_dir=Path(directory.name) / "data",
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
        create_runtime(settings)
        seed_test_agent(settings.data_dir, "minimal", role="worker")

        identity = create_runtime(settings).identities.load_identity("minimal")

        self.assertEqual(identity.name, "Minimal")
        self.assertFalse(identity.can_delegate)
        self.assertEqual(identity.soul, "")
        self.assertEqual(identity.skills, "")

    def test_folder_and_config_id_mismatch_is_rejected(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        config_path = runtime.data_dir.resolve("agents/artemis/CONFIG.yaml")
        config = load_structured_file(config_path)
        config["id"] = "other"
        dump_structured_file(config_path, config)

        with self.assertRaisesRegex(ValidationError, "id mismatch"):
            runtime.identities.load_identity("artemis")

    def test_missing_required_role_is_rejected(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_invalid_agent(
            runtime.data_dir.root,
            "partial",
            {"id": "partial", "name": "Partial"},
        )

        with self.assertRaisesRegex(ValidationError, "role is required"):
            runtime.identities.load_identity("partial")

    def test_base_agents_exist_in_data_dir(self) -> None:
        for agent_id in ["artemis", "researcher", "atlas", "hermes", "vigil"]:
            base = PROJECT_ROOT / "data" / "agents" / agent_id
            self.assertTrue((base / "CONFIG.yaml").exists())
            self.assertTrue((base / "SOUL.md").exists())
            self.assertTrue((base / "MEMORY.md").exists())
            self.assertTrue((base / "SKILLS.md").exists())
            self.assertTrue((base / "INBOX.md").exists())


if __name__ == "__main__":
    unittest.main()
