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
            "name": "Synapse V2 Agent Audit Test",
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
    return directory, settings, create_runtime(settings)


def basic_request(agent_id: str = "managed") -> AgentCreateRequest:
    return AgentCreateRequest(
        agent_id=agent_id,
        display_name="Managed",
        role="assistant",
        capabilities_allow=["filesystem.read"],
        capabilities_deny=["filesystem.write"],
    )


def sensitive_request(agent_id: str = "builder") -> AgentCreateRequest:
    return AgentCreateRequest(
        agent_id=agent_id,
        display_name="Builder",
        role="file_builder",
        capabilities_allow=["filesystem.write"],
        preferred_tools=["write_file"],
    )


class AgentAuditRuntimeTests(unittest.TestCase):
    def test_append_and_list_agent_audit(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        record = runtime.audit.append_record(
            agent_id="managed",
            action="agent.created",
            status="success",
            actor_type="system",
            details={"source": "test"},
        )

        records = runtime.audit.list_agent_audit("managed")
        self.assertEqual(records[0].id, record.id)
        self.assertEqual(records[0].details["source"], "test")

    def test_list_recent_audit(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.audit.append_record("one", "agent.created")
        runtime.audit.append_record("two", "agent.created")

        recent = runtime.audit.list_recent_audit(limit=1)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].agent_id, "two")

    def test_agent_audit_summary(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.audit.append_record("managed", "agent.created", "success")
        runtime.audit.append_record("managed", "agent.provisioning.failed", "blocked")

        summary = runtime.audit.get_agent_audit_summary("managed")
        self.assertEqual(summary.total_records, 2)
        self.assertEqual(summary.successes, 1)
        self.assertEqual(summary.blocked, 1)
        self.assertEqual(summary.last_action, "agent.provisioning.failed")

    def test_create_agent_generates_audit(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.provisioning.create_agent(basic_request())

        actions = [record.action for record in runtime.audit.list_agent_audit("managed")]
        self.assertIn("agent.created", actions)

    def test_archive_and_restore_generate_audit(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(basic_request())

        runtime.admin.archive_agent("managed")
        runtime.admin.restore_agent("managed")

        actions = [record.action for record in runtime.audit.list_agent_audit("managed")]
        self.assertIn("agent.archived", actions)
        self.assertIn("agent.restored", actions)

    def test_provisioning_approval_and_apply_generate_audit(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.provisioning.create_agent(
            sensitive_request(),
            context=runtime.context(actor_id="guest"),
        )
        self.assertEqual(result.status, "awaiting_approval")

        runtime.provisioning.approve_provisioning_request(
            runtime.context(),
            result.provisioning_request_id or "",
        )
        runtime.provisioning.apply_approved_provisioning_request(
            runtime.context(),
            result.provisioning_request_id or "",
        )

        actions = [record.action for record in runtime.audit.list_agent_audit("builder")]
        self.assertIn("agent.provisioning.requested", actions)
        self.assertIn("agent.provisioning.approved", actions)
        self.assertIn("agent.provisioning.applied", actions)

    def test_agent_audit_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(basic_request())

        audit = runtime.commands.execute(runtime.context(), "/agent-audit managed")
        recent = runtime.commands.execute(runtime.context(), "/agent-audit-recent")
        summary = runtime.commands.execute(runtime.context(), "/agent-audit-summary managed")

        self.assertEqual(audit.status, "ok")
        self.assertEqual(recent.status, "ok")
        self.assertEqual(summary.status, "ok")
        self.assertGreaterEqual(summary.data["summary"]["total_records"], 1)

    def test_agent_audit_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(basic_request())
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        audit = client.get("/api/agents/managed/audit")
        recent = client.get("/api/agent-audit/recent")
        summary = client.get("/api/agents/managed/audit/summary")

        self.assertEqual(audit.status_code, 200)
        self.assertEqual(recent.status_code, 200)
        self.assertEqual(summary.status_code, 200)
        self.assertGreaterEqual(summary.json()["total_records"], 1)


if __name__ == "__main__":
    unittest.main()
