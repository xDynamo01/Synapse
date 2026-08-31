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
    policy = {
        "admin_policy": {
            "allow_user_admin_actions": True,
            "require_approval_for_archive": True,
            "require_approval_for_deactivate": True,
            "require_approval_for_restore": True,
            "protected_agents": [],
            "blocked_admin_actions": [],
            "admin_capabilities_required": {},
        }
    }
    if policy_updates:
        policy["admin_policy"].update(policy_updates)
    system = {
        "system": {
            "name": "Synapse V2 Admin Approval Test",
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
    write_json(settings.data_dir / "config" / "admin_policy.yaml", policy)
    runtime = create_runtime(settings)
    runtime.provisioning.create_agent(
        AgentCreateRequest(agent_id="managed", display_name="Managed", role="assistant")
    )
    return directory, settings, runtime


class AdminApprovalFlowTests(unittest.TestCase):
    def test_request_action_that_requires_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        request = runtime.admin.request_admin_action(
            "agent.archive",
            "managed",
            context=runtime.context(),
        )

        self.assertEqual(request.status, "awaiting_approval")
        self.assertEqual(request.action, "agent.archive")
        self.assertIsNotNone(request.approval_id)

    def test_approval_request_is_created(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        request = runtime.admin.request_admin_action(
            "agent.archive",
            "managed",
            context=runtime.context(),
        )
        approval = runtime.approvals.get_status(request.approval_id or "")

        self.assertEqual(approval.tool_name, "agent_admin_action")
        self.assertEqual(approval.tool_args["target_agent_id"], "managed")

    def test_approval_does_not_apply_automatically(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = runtime.admin.request_admin_action(
            "agent.deactivate",
            "managed",
            context=runtime.context(),
        )

        approved = runtime.admin.approve_admin_action_request(request.id, runtime.context())

        self.assertEqual(approved.status, "approved")
        self.assertEqual(runtime.admin.get_agent_admin_status("managed").status, "active")

    def test_apply_executes_action_after_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = runtime.admin.request_admin_action(
            "agent.deactivate",
            "managed",
            context=runtime.context(),
        )
        runtime.admin.approve_admin_action_request(request.id, runtime.context())

        result = runtime.admin.apply_admin_action_request(request.id, runtime.context())

        self.assertTrue(result.applied)
        self.assertEqual(runtime.admin.get_agent_admin_status("managed").status, "inactive")

    def test_rejection_prevents_application(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = runtime.admin.request_admin_action(
            "agent.archive",
            "managed",
            context=runtime.context(),
        )
        runtime.admin.reject_admin_action_request(request.id, runtime.context())

        with self.assertRaises(ValidationError):
            runtime.admin.apply_admin_action_request(request.id, runtime.context())

    def test_duplicate_application_is_blocked(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = runtime.admin.request_admin_action(
            "agent.deactivate",
            "managed",
            context=runtime.context(),
        )
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        runtime.admin.apply_admin_action_request(request.id, runtime.context())

        with self.assertRaises(ValidationError):
            runtime.admin.apply_admin_action_request(request.id, runtime.context())

    def test_policy_blocked_prevents_request(self) -> None:
        directory, _, runtime = runtime_in_tempdir(
            {"blocked_admin_actions": ["agent.archive"]}
        )
        self.addCleanup(directory.cleanup)

        with self.assertRaises(ValidationError):
            runtime.admin.request_admin_action(
                "agent.archive",
                "managed",
                context=runtime.context(),
            )

    def test_apply_revalidates_blocked_policy(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = runtime.admin.request_admin_action(
            "agent.archive",
            "managed",
            context=runtime.context(),
        )
        runtime.admin.approve_admin_action_request(request.id, runtime.context())
        write_json(
            settings.data_dir / "config" / "admin_policy.yaml",
            {
                "admin_policy": {
                    "allow_user_admin_actions": True,
                    "require_approval_for_archive": True,
                    "require_approval_for_deactivate": True,
                    "require_approval_for_restore": True,
                    "protected_agents": [],
                    "blocked_admin_actions": ["agent.archive"],
                    "admin_capabilities_required": {},
                }
            },
        )

        with self.assertRaises(ValidationError):
            runtime.admin.apply_admin_action_request(request.id, runtime.context())

    def test_audit_and_events_are_recorded(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        request = runtime.admin.request_admin_action(
            "agent.archive",
            "managed",
            context=runtime.context(),
        )

        records = runtime.audit.list_agent_audit("managed")
        event_types = [event.type for event in runtime.events.tail(20)]
        self.assertTrue(any(record.action == "admin.action.requested" for record in records))
        self.assertIn("agent.admin_action.requested", event_types)
        self.assertIn("agent.admin_action.awaiting_approval", event_types)
        self.assertEqual(request.status, "awaiting_approval")

    def test_admin_action_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        requested = runtime.commands.execute(
            runtime.context(),
            "/request-admin-action agent.deactivate managed",
        )
        request_id = requested.data["request"]["id"]
        listed = runtime.commands.execute(runtime.context(), "/admin-action-requests")
        detail = runtime.commands.execute(runtime.context(), f"/admin-action-request {request_id}")
        approved = runtime.commands.execute(runtime.context(), f"/approve-admin-action {request_id}")
        applied = runtime.commands.execute(runtime.context(), f"/apply-admin-action {request_id}")

        self.assertEqual(requested.status, "ok")
        self.assertEqual(listed.status, "ok")
        self.assertEqual(detail.status, "ok")
        self.assertEqual(approved.status, "ok")
        self.assertEqual(applied.status, "ok")

    def test_admin_action_api(self) -> None:
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

        requested = client.post(
            "/api/agent-admin/requests",
            json={"action": "agent.deactivate", "agent_id": "managed"},
        )
        request_id = requested.json()["id"]
        listed = client.get("/api/agent-admin/requests")
        detail = client.get(f"/api/agent-admin/requests/{request_id}")
        approved = client.post(f"/api/agent-admin/requests/{request_id}/approve")
        applied = client.post(f"/api/agent-admin/requests/{request_id}/apply")

        self.assertEqual(requested.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(applied.status_code, 200)


if __name__ == "__main__":
    unittest.main()
