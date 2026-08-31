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
from synapse.core.exceptions import NotFound, ValidationError


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
    seed_test_agent(settings.data_dir, "artemis", role="assistant")
    (settings.data_dir / "config" / "system.yaml").write_text(
        json.dumps(
            {
                "system": {"name": "Tool Intent Test", "mode": "test"},
                "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
            }
        ),
        encoding="utf-8",
    )
    (settings.data_dir / "config" / "permissions.yaml").write_text(
        json.dumps(
            {
                "subjects": {
                    "local_owner": ["*"],
                    "user:local_owner": ["*"],
                    "agent:artemis": ["*"],
                }
            }
        ),
        encoding="utf-8",
    )
    return directory, settings, create_runtime(settings)


class ToolIntentRuntimeTests(unittest.TestCase):
    def test_create_and_persist_intent_without_execution(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        intent = runtime.tool_intents.create_intent(
            "health.summary",
            {"detail": "short"},
            source="agent",
            source_agent_id="artemis",
        )

        self.assertEqual(intent.status, "proposed")
        self.assertTrue((settings.data_dir / "tool_intents" / f"{intent.intent_id}.yaml").exists())
        self.assertEqual(runtime.tool_runtime.execution_counts, {})
        self.assertEqual(runtime.approvals.list_pending(), [])
        restarted = create_runtime(settings)
        self.assertEqual(restarted.tool_intents.get_intent(intent.intent_id).tool_id, "health.summary")

    def test_list_and_pending_intents(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        first = runtime.tool_intents.create_intent("health.summary")
        second = runtime.tool_intents.create_intent("tool.summary")
        runtime.tool_intents.approve_intent(first.intent_id, "local_owner")

        self.assertEqual(len(runtime.tool_intents.list_intents()), 2)
        self.assertEqual(
            [intent.intent_id for intent in runtime.tool_intents.list_pending_intents()],
            [second.intent_id],
        )

    def test_missing_tool_fails(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with self.assertRaises(NotFound):
            runtime.tool_intents.create_intent("missing.tool")

    def test_dry_run_decision_is_stored(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        intent = runtime.tool_intents.create_intent("health.summary")

        self.assertTrue(intent.decision_snapshot["allowed"])
        self.assertFalse(intent.decision_snapshot["requires_approval"])
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_approval_required_is_stored_without_approval_request(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        intent = runtime.tool_intents.create_intent("danger.mock")

        self.assertTrue(intent.decision_snapshot["requires_approval"])
        self.assertFalse(intent.decision_snapshot["allowed"])
        self.assertEqual(runtime.approvals.list_pending(), [])
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_approve_does_not_execute(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = runtime.tool_intents.create_intent("danger.mock")

        approved = runtime.tool_intents.approve_intent(intent.intent_id, "local_owner")

        self.assertEqual(approved.status, "approved")
        self.assertEqual(approved.review["reviewed_by"], "local_owner")
        self.assertEqual(runtime.tool_runtime.execution_counts, {})
        self.assertEqual(runtime.approvals.list_pending(), [])

    def test_reject_and_cancel(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        rejected_intent = runtime.tool_intents.create_intent("health.summary")
        cancelled_intent = runtime.tool_intents.create_intent("tool.summary")

        rejected = runtime.tool_intents.reject_intent(rejected_intent.intent_id, "local_owner")
        cancelled = runtime.tool_intents.cancel_intent(cancelled_intent.intent_id, "local_owner")

        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(cancelled.status, "cancelled")
        with self.assertRaises(ValidationError):
            runtime.tool_intents.approve_intent(rejected.intent_id)

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        context = runtime.context()

        proposed = runtime.commands.execute(context, "/propose-tool health.summary detail=short")
        intent_id = proposed.data["intent"]["intent_id"]
        listed = runtime.commands.execute(context, "/tool-intents")
        detail = runtime.commands.execute(context, f"/tool-intent {intent_id}")
        approved = runtime.commands.execute(context, f"/approve-tool-intent {intent_id}")

        self.assertEqual(proposed.status, "ok")
        self.assertEqual(listed.status, "ok")
        self.assertEqual(detail.status, "ok")
        self.assertEqual(approved.data["intent"]["status"], "approved")
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        created = client.post(
            "/api/tool-intents",
            json={"tool_id": "danger.mock", "source": "user"},
        )
        intent_id = created.json()["intent_id"]
        listed = client.get("/api/tool-intents")
        detail = client.get(f"/api/tool-intents/{intent_id}")
        approved = client.post(
            f"/api/tool-intents/{intent_id}/approve",
            json={"reviewed_by": "local_owner"},
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_health_and_readiness(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.tool_intents.create_intent("health.summary")

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.tool_intent_runtime_available)
        self.assertEqual(health.pending_tool_intents_count, 1)
        self.assertIn("tool_intents.ready", {check.id for check in readiness.checks})


if __name__ == "__main__":
    unittest.main()
