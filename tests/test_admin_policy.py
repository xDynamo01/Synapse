from __future__ import annotations

import json
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


def runtime_in_tempdir(policy_updates: dict | None = None):
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
            "name": "Synapse V2 Admin Policy Test",
            "mode": "test",
            "default_agent_id": "managed",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    policy = {
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
    if policy_updates:
        policy["admin_policy"].update(policy_updates)
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    write_json(settings.data_dir / "config" / "admin_policy.yaml", policy)
    runtime = create_runtime(settings)
    runtime.provisioning.create_agent(
        AgentCreateRequest(agent_id="managed", display_name="Managed", role="assistant")
    )
    return directory, runtime


class AdminPolicyRuntimeTests(unittest.TestCase):
    def test_load_default_policy(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        policy = runtime.admin_policy.load_policy()

        self.assertTrue(policy.allow_user_admin_actions)
        self.assertEqual(policy.blocked_admin_actions, [])

    def test_admin_action_allowed(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.admin.deactivate_agent("managed", runtime.context())

        self.assertEqual(result.status, "inactive")

    def test_blocked_admin_action_fails_clearly(self) -> None:
        directory, runtime = runtime_in_tempdir({"blocked_admin_actions": ["agent.archive"]})
        self.addCleanup(directory.cleanup)

        with self.assertRaises(ValidationError) as raised:
            runtime.admin.archive_agent("managed", runtime.context())

        self.assertIn("admin action is blocked by policy", str(raised.exception))

    def test_protected_agent_requires_approval_when_policy_says_so(self) -> None:
        directory, runtime = runtime_in_tempdir(
            {
                "protected_agents": ["managed"],
                "require_approval_for_deactivate": True,
            }
        )
        self.addCleanup(directory.cleanup)

        with self.assertRaises(ValidationError) as raised:
            runtime.admin.deactivate_agent("managed", runtime.context())

        self.assertIn("requires approval", str(raised.exception))

    def test_archive_respects_policy(self) -> None:
        directory, runtime = runtime_in_tempdir({"require_approval_for_archive": True})
        self.addCleanup(directory.cleanup)

        with self.assertRaises(ValidationError) as raised:
            runtime.admin.archive_agent("managed", runtime.context())

        self.assertIn("requires approval", str(raised.exception))

    def test_deactivate_respects_policy(self) -> None:
        directory, runtime = runtime_in_tempdir({"require_approval_for_deactivate": True})
        self.addCleanup(directory.cleanup)

        with self.assertRaises(ValidationError):
            runtime.admin.deactivate_agent("managed", runtime.context())

        status = runtime.admin.get_agent_admin_status("managed")
        self.assertEqual(status.status, "active")

    def test_audit_records_blocked_decision(self) -> None:
        directory, runtime = runtime_in_tempdir({"blocked_admin_actions": ["agent.archive"]})
        self.addCleanup(directory.cleanup)

        with self.assertRaises(ValidationError):
            runtime.admin.archive_agent("managed", runtime.context())

        records = runtime.audit.list_agent_audit("managed")
        self.assertTrue(any(record.status == "blocked" for record in records))

    def test_admin_policy_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        policy = runtime.commands.execute(runtime.context(), "/admin-policy")
        check = runtime.commands.execute(runtime.context(), "/admin-check agent.validate managed")

        self.assertEqual(policy.status, "ok")
        self.assertEqual(check.status, "ok")
        self.assertTrue(check.data["decision"]["allowed"])

    def test_admin_policy_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        policy = client.get("/api/admin-policy")
        check = client.post(
            "/api/admin-check",
            json={"action": "agent.validate", "agent_id": "managed"},
        )

        self.assertEqual(policy.status_code, 200)
        self.assertEqual(check.status_code, 200)
        self.assertTrue(check.json()["allowed"])


if __name__ == "__main__":
    unittest.main()
