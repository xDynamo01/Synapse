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
from synapse.core.serialization import load_structured_file
from synapse.decisions.models import DecisionRequest, DecisionResult


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def runtime_in_tempdir(admin_policy_updates: dict | None = None):
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
            "agent:worker": [
                "filesystem.read",
                "filesystem.list",
                "filesystem.search",
                "tasks.create",
            ],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Decision Test",
            "mode": "test",
            "default_agent_id": "worker",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    admin_policy = {
        "admin_policy": {
            "allow_user_admin_actions": True,
            "require_approval_for_archive": False,
            "require_approval_for_deactivate": False,
            "require_approval_for_restore": False,
            "protected_agents": [],
            "blocked_admin_actions": [],
            "admin_capabilities_required": {},
        }
    }
    if admin_policy_updates:
        admin_policy["admin_policy"].update(admin_policy_updates)
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    write_json(settings.data_dir / "config" / "admin_policy.yaml", admin_policy)
    write_json(
        settings.data_dir / "agents" / "worker" / "CONFIG.yaml",
        {
            "id": "worker",
            "name": "Worker",
            "role": "decision_test_worker",
            "permissions": ["filesystem.read", "filesystem.list", "filesystem.search", "tasks.create"],
            "capabilities": {"allow": ["filesystem.read", "task.create"], "deny": []},
        },
    )
    return directory, settings, create_runtime(settings)


def deny_capability(settings: Settings, capability_id: str) -> None:
    path = settings.data_dir / "agents" / "worker" / "CONFIG.yaml"
    raw = load_structured_file(path)
    raw["capabilities"] = {"allow": [], "deny": [capability_id]}
    write_json(path, raw)


class DecisionRuntimeTests(unittest.TestCase):
    def test_capability_allowed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="capability",
                actor_type="agent",
                actor_id="worker",
                target_agent_id="worker",
                action="filesystem.read",
                capability_id="filesystem.read",
            )
        )

        self.assertIsInstance(result, DecisionResult)
        self.assertTrue(result.allowed)
        self.assertIn("CapabilityRuntime", result.evaluated_components)

    def test_capability_blocked(self) -> None:
        directory, settings, _ = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        deny_capability(settings, "filesystem.read")
        runtime = create_runtime(settings)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="capability",
                actor_type="agent",
                actor_id="worker",
                target_agent_id="worker",
                action="filesystem.read",
                capability_id="filesystem.read",
            )
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.blocked)
        self.assertIn("agent_deny", result.blocked_reasons)

    def test_tool_execution_allowed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="tool_execution",
                actor_type="agent",
                actor_id="worker",
                target_agent_id="worker",
                action="read_file",
            )
        )

        self.assertTrue(result.allowed)
        self.assertIn("PermissionManager", result.evaluated_components)
        self.assertEqual(result.metadata["permission"], "filesystem.read")

    def test_tool_execution_blocked(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="tool_execution",
                actor_type="agent",
                actor_id="worker",
                target_agent_id="worker",
                action="write_file",
            )
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.blocked)
        self.assertTrue(result.blocked_reasons)

    def test_provisioning_allowed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="agent_provisioning",
                actor_type="user",
                actor_id="local_owner",
                action="create",
                metadata={"capabilities_allow": [], "preferred_tools": [], "forbidden_tools": []},
            )
        )

        self.assertTrue(result.allowed)
        self.assertFalse(result.requires_approval)

    def test_provisioning_requires_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="agent_provisioning",
                actor_type="user",
                actor_id="local_owner",
                action="create",
                metadata={
                    "capabilities_allow": ["filesystem.write"],
                    "preferred_tools": ["write_file"],
                    "forbidden_tools": [],
                },
            )
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.requires_approval)
        self.assertEqual(result.approval_required_by, "AgentProvisioningPolicyRuntime")

    def test_admin_action_allowed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="admin_action",
                actor_type="user",
                actor_id="local_owner",
                action="agent.validate",
                target_agent_id="worker",
            )
        )

        self.assertTrue(result.allowed)

    def test_admin_action_blocked(self) -> None:
        directory, _, runtime = runtime_in_tempdir(
            {"blocked_admin_actions": ["agent.archive"]}
        )
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="admin_action",
                actor_type="user",
                actor_id="local_owner",
                action="agent.archive",
                target_agent_id="worker",
            )
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.blocked)

    def test_explain_decision(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        explanation = runtime.decisions.explain_decision(
            DecisionRequest(
                category="capability",
                actor_type="agent",
                actor_id="worker",
                target_agent_id="worker",
                action="filesystem.read",
            )
        )

        self.assertEqual(explanation["summary"], "allowed")
        self.assertTrue(explanation["result"]["allowed"])

    def test_decision_command(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(
            runtime.context(actor_id="worker", actor_type="agent"),
            "/decision-check capability filesystem.read",
        )

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.data["decision"]["allowed"])

    def test_decision_api(self) -> None:
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

        response = client.post(
            "/api/decision-check",
            json={
                "category": "capability",
                "action": "filesystem.read",
                "capability_id": "filesystem.read",
                "actor_type": "agent",
                "actor_id": "worker",
                "target_agent_id": "worker",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["allowed"])

    def test_decision_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir(
            {"blocked_admin_actions": ["agent.archive"]}
        )
        self.addCleanup(directory.cleanup)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                category="admin_action",
                actor_type="user",
                actor_id="local_owner",
                action="agent.archive",
                target_agent_id="worker",
                correlation_id="decision-test-correlation",
            )
        )

        self.assertTrue(result.blocked)
        events = runtime.events.trace("decision-test-correlation")
        event_types = [event.type for event in events]
        self.assertIn("decision.evaluated", event_types)
        self.assertIn("decision.blocked", event_types)


if __name__ == "__main__":
    unittest.main()
