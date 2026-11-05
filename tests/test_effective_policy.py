from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_test_agent
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import load_structured_file
from synapse.tools.calls import ToolCallRequest


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def runtime_in_tempdir(
    global_permissions: list[str] | None = None,
    global_denies: list[str] | None = None,
    agent_permissions: list[str] | None = None,
    forbidden_tools: list[str] | None = None,
    preferred_tools: list[str] | None = None,
    role: str = "orchestrator",
):
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    seed_test_agent(
        settings.data_dir,
        "artemis",
        role=role,
        extra={
            "permissions": agent_permissions or [],
            "forbidden_tools": forbidden_tools or [],
            "preferred_tools": preferred_tools or [],
        },
    )

    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:artemis": global_permissions
            or [
                "filesystem.read",
                "filesystem.write",
                "filesystem.list",
                "filesystem.search",
                "agents.message",
                "tasks.create",
                "tasks.update",
                "web.search",
            ],
        },
        "denies": {"agent:artemis": global_denies or []},
    }
    system = {
        "system": {
            "name": "Synapse V2 Effective Policy Test",
            "mode": "test",
            "default_agent_id": "artemis",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)

    config_path = settings.data_dir / "agents" / "artemis" / "CONFIG.yaml"
    config = load_structured_file(config_path)
    if agent_permissions is not None:
        config["permissions"] = agent_permissions
    if forbidden_tools is not None:
        config["forbidden_tools"] = forbidden_tools
    if preferred_tools is not None:
        config["preferred_tools"] = preferred_tools
    write_json(config_path, config)

    return directory, create_runtime(settings)


class EffectiveAgentPolicyTests(unittest.TestCase):
    def test_primary_agent_receives_synapse_permissions(self) -> None:
        directory, runtime = runtime_in_tempdir(role="primary_agent")
        self.addCleanup(directory.cleanup)

        policy = runtime.policies.resolve(runtime.context(), "artemis")

        self.assertIn("filesystem.read", policy.allowed_permissions)
        self.assertIn("filesystem.write", policy.allowed_permissions)
        self.assertIn("read_file", policy.allowed_tools)
        self.assertIn("write_file", policy.allowed_tools)

    def test_policy_combines_global_permissions_and_agent_config(self) -> None:
        directory, runtime = runtime_in_tempdir(
            global_permissions=["filesystem.read", "filesystem.list"],
            agent_permissions=["filesystem.read", "filesystem.write", "filesystem.list"],
        )
        self.addCleanup(directory.cleanup)

        policy = runtime.policies.resolve(runtime.context(), "artemis")

        self.assertIn("read_file", policy.allowed_tools)
        self.assertIn("list_directory", policy.allowed_tools)
        self.assertNotIn("write_file", policy.allowed_tools)
        self.assertEqual(policy.allowed_permissions, ["filesystem.list", "filesystem.read"])

    def test_forbidden_tools_always_block(self) -> None:
        directory, runtime = runtime_in_tempdir(forbidden_tools=["write_file"])
        self.addCleanup(directory.cleanup)

        result = runtime.chat.send_message(
            runtime.context(),
            "artemis",
            "tool:write_file path=projects/forbidden-policy.txt content=no",
        )

        tool_result = result.message.metadata["tool_results"][0]
        self.assertEqual(tool_result["status"], "blocked")
        self.assertIn("Tool is forbidden", tool_result["error"])
        self.assertFalse(runtime.data_dir.resolve("projects/forbidden-policy.txt").exists())

    def test_global_deny_wins_agent_allow(self) -> None:
        directory, runtime = runtime_in_tempdir(
            global_permissions=["filesystem.read", "filesystem.write"],
            global_denies=["filesystem.write"],
            agent_permissions=["filesystem.read", "filesystem.write"],
        )
        self.addCleanup(directory.cleanup)

        policy = runtime.policies.resolve(runtime.context(), "artemis")
        decision = runtime.permissions.is_allowed(
            PermissionContext(actor_id="artemis", actor_type="agent"),
            "filesystem.write",
        )

        self.assertNotIn("write_file", policy.allowed_tools)
        self.assertIn("filesystem.write", policy.denied_permissions)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "explicit_deny")

    def test_agent_forbidden_wins_global_allow(self) -> None:
        directory, runtime = runtime_in_tempdir(
            global_permissions=["filesystem.write"],
            agent_permissions=["filesystem.write"],
            forbidden_tools=["write_file"],
        )
        self.addCleanup(directory.cleanup)

        policy = runtime.policies.resolve(runtime.context(), "artemis")

        self.assertIn("write_file", policy.forbidden_tools)
        self.assertNotIn("write_file", policy.allowed_tools)

    def test_approval_required_for_appears_from_approval_policy(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        policy = runtime.policies.resolve(runtime.context(), "artemis")

        self.assertEqual(policy.approval_required_for, ["high", "critical"])

    def test_preferred_tools_do_not_grant_permission(self) -> None:
        directory, runtime = runtime_in_tempdir(
            global_permissions=["filesystem.read", "tasks.create"],
            agent_permissions=["filesystem.read"],
            preferred_tools=["create_task"],
        )
        self.addCleanup(directory.cleanup)

        policy = runtime.policies.resolve(runtime.context(), "artemis")

        self.assertIn("create_task", policy.preferred_tools)
        self.assertNotIn("create_task", policy.allowed_tools)

    def test_device_constraints_restrict_action(self) -> None:
        directory, runtime = runtime_in_tempdir(
            global_permissions=["filesystem.read", "filesystem.write", "filesystem.list"],
            agent_permissions=["filesystem.read", "filesystem.write", "filesystem.list"],
        )
        self.addCleanup(directory.cleanup)
        runtime.devices.register_device(
            "reader-device",
            trusted=True,
            permissions=["filesystem.read"],
            actor_id="local_owner",
        )

        policy = runtime.policies.resolve(
            runtime.context(device_id="reader-device"),
            "artemis",
        )

        self.assertTrue(policy.device_constraints["applied"])
        self.assertIn("read_file", policy.allowed_tools)
        self.assertNotIn("write_file", policy.allowed_tools)
        self.assertNotIn("list_directory", policy.allowed_tools)

    def test_tool_router_uses_agent_effective_policy(self) -> None:
        directory, runtime = runtime_in_tempdir(
            global_permissions=["filesystem.write"],
            agent_permissions=["filesystem.read"],
        )
        self.addCleanup(directory.cleanup)
        policy = runtime.policies.resolve(runtime.context(), "artemis")
        call = ToolCallRequest(
            name="write_file",
            arguments={"path": "projects/router-policy.txt", "content": "blocked"},
        )

        result = runtime.tool_router.execute_call(
            PermissionContext(actor_id="artemis", actor_type="agent"),
            call,
            policy=policy,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "failed")
        self.assertIn("effective policy blocks", result.error)
        self.assertFalse(runtime.data_dir.resolve("projects/router-policy.txt").exists())

    def test_policy_command_returns_structured_policy(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), "/policy Artemis")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["policy"]["agent_id"], "artemis")
        self.assertIn("allowed_tools", result.data["policy"])
        self.assertIn("approval_required_for", result.data["policy"])


if __name__ == "__main__":
    unittest.main()
