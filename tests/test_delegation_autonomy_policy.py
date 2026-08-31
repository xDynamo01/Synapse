from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_delegation_pair
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.decisions.models import DecisionRequest

DEFAULT_PERMISSIONS = [
    "filesystem.read",
    "filesystem.write",
    "filesystem.list",
    "filesystem.search",
    "agents.message",
    "delegation.create",
    "tasks.create",
    "tasks.update",
    "web.search",
]


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
            "agent:artemis": DEFAULT_PERMISSIONS,
            "agent:researcher": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Delegation Autonomy Test",
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
    seed_delegation_pair(
        settings.data_dir,
        delegator_extra={"permissions": DEFAULT_PERMISSIONS},
        delegate_extra={"permissions": DEFAULT_PERMISSIONS},
    )
    return directory, create_runtime(settings)


def write_autonomy_policy(runtime, **updates) -> None:
    policy = {
        "enabled": True,
        "allow_auto_accept": False,
        "allow_auto_start": True,
        "allow_auto_reject": False,
        "max_auto_priority": "high",
        "require_approval_for_critical": True,
        "allowed_requester_agents": [],
        "blocked_requester_agents": [],
        "require_capability_match": False,
        "require_due_at_for_auto_accept": False,
        "manual_autonomy_blocks_auto_accept": True,
        "conservative_default": True,
    }
    policy.update(updates)
    write_json(
        runtime.data_dir.resolve("config/delegation_autonomy_policy.yaml"),
        {"delegation_autonomy": policy},
    )


def create_task(runtime, priority: str = "normal", requester: str = "artemis"):
    return runtime.delegation.create_task(
        context=runtime.context(actor_id=requester, actor_type="agent"),
        title=f"{priority} delegated work",
        description="Work item",
        requester_agent_id=requester,
        assignee_agent_id="researcher",
        priority=priority,
    )


def autonomy_decision(runtime, task, action: str):
    return runtime.delegation_autonomy.explain_decision(
        task.task_id,
        action,
        task,
        runtime.identities.load_identity(task.assignee_agent_id),
        runtime.policies.resolve(runtime.context(), task.assignee_agent_id),
    )


class DelegationAutonomyPolicyTests(unittest.TestCase):
    def test_agent_registry_infers_required_identity_fields_from_fixture(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        identity = runtime.identities.load_identity("artemis")

        self.assertEqual(identity.id, "artemis")
        self.assertEqual(identity.role, "orchestrator")
        self.assertTrue(identity.can_delegate)

    def test_default_policy_blocks_auto_accept_manual(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        decision = autonomy_decision(runtime, task, "accept")

        self.assertTrue(decision.blocked)
        self.assertIn("auto accept is disabled", decision.blocked_reasons)
        self.assertIn("manual autonomy blocks auto accept", decision.blocked_reasons)

    def test_auto_accept_allowed_when_policy_permits(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_autonomy_policy(
            runtime,
            allow_auto_accept=True,
            manual_autonomy_blocks_auto_accept=False,
        )
        task = create_task(runtime)

        result = runtime.worker.process_next_delegation(runtime.context(), "researcher")

        self.assertEqual(result.task_id, task.task_id)
        self.assertEqual(result.action, "accepted")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "accepted")

    def test_critical_requires_approval(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_autonomy_policy(
            runtime,
            allow_auto_accept=True,
            manual_autonomy_blocks_auto_accept=False,
        )
        task = create_task(runtime, priority="critical")

        result = runtime.worker.process_next_delegation(runtime.context(), "researcher")

        self.assertEqual(result.action, "autonomy_requires_approval")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "pending")

    def test_blocked_requester_blocks(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_autonomy_policy(
            runtime,
            allow_auto_accept=True,
            manual_autonomy_blocks_auto_accept=False,
            blocked_requester_agents=["artemis"],
        )
        task = create_task(runtime)

        decision = autonomy_decision(runtime, task, "accept")

        self.assertTrue(decision.blocked)
        self.assertIn("blocked requester agent: artemis", decision.blocked_reasons)

    def test_allowed_requester_allows(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_autonomy_policy(
            runtime,
            allow_auto_accept=True,
            manual_autonomy_blocks_auto_accept=False,
            allowed_requester_agents=["artemis"],
        )
        task = create_task(runtime)

        decision = autonomy_decision(runtime, task, "accept")

        self.assertTrue(decision.allowed)

    def test_accepted_starts_only_if_policy_allows(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.delegation.accept_task(runtime.context(), task.task_id)

        result = runtime.worker.process_next_delegation(runtime.context(), "researcher")

        self.assertEqual(result.action, "started")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")

    def test_accepted_start_blocked_when_policy_disallows(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_autonomy_policy(runtime, allow_auto_start=False)
        task = create_task(runtime)
        runtime.delegation.accept_task(runtime.context(), task.task_id)

        result = runtime.worker.process_next_delegation(runtime.context(), "researcher")

        self.assertEqual(result.action, "autonomy_blocked")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "accepted")

    def test_decision_runtime_integrates_delegation_autonomy(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        result = runtime.decisions.evaluate(
            DecisionRequest(
                actor_type="user",
                action="accept",
                category="delegation_autonomy",
                target_agent_id=task.task_id,
                metadata={"task_id": task.task_id},
            )
        )

        self.assertTrue(result.blocked)
        self.assertEqual(result.metadata["category"], "delegation_autonomy")

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        policy = runtime.commands.execute(runtime.context(), "/delegation-autonomy-policy")
        check = runtime.commands.execute(
            runtime.context(),
            f"/delegation-autonomy-check {task.task_id} accept",
        )

        self.assertEqual(policy.status, "ok")
        self.assertEqual(check.status, "ok")
        self.assertTrue(check.data["decision"]["blocked"])

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        policy = client.get("/api/delegation-autonomy-policy")
        check = client.post(
            f"/api/delegations/{task.task_id}/autonomy-check",
            json={"action": "accept"},
        )

        self.assertEqual(policy.status_code, 200)
        self.assertEqual(check.status_code, 200)
        self.assertTrue(check.json()["blocked"])


if __name__ == "__main__":
    unittest.main()
