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
from synapse.core.exceptions import ValidationError


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
    (settings.data_dir / "config" / "permissions.yaml").write_text(
        json.dumps({"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}}),
        encoding="utf-8",
    )
    return directory, settings, create_runtime(settings)


def approved_intent(runtime, tool_id: str = "health.summary", arguments=None):
    intent = runtime.tool_intents.create_intent(tool_id, arguments or {})
    return runtime.tool_intents.approve_intent(intent.intent_id, "local_owner")


class ToolIntentExecutionTests(unittest.TestCase):
    def test_proposed_does_not_execute(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = runtime.tool_intents.create_intent("health.summary")

        with self.assertRaises(ValidationError):
            runtime.tool_intents.execute_intent(intent.intent_id)

        self.assertEqual(runtime.tool_runtime.execution_counts, {})
        self.assertEqual(runtime.tool_intents.get_intent(intent.intent_id).status, "proposed")

    def test_rejected_and_cancelled_do_not_execute(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        rejected = runtime.tool_intents.create_intent("health.summary")
        rejected = runtime.tool_intents.reject_intent(rejected.intent_id)
        cancelled = runtime.tool_intents.create_intent("health.summary")
        cancelled = runtime.tool_intents.cancel_intent(cancelled.intent_id)

        for intent in [rejected, cancelled]:
            with self.assertRaises(ValidationError):
                runtime.tool_intents.execute_intent(intent.intent_id)

        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_reviewed_does_not_execute(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = runtime.tool_intents.create_intent("health.summary")
        reviewed = runtime.tool_intents.review_intent(intent.intent_id)

        with self.assertRaises(ValidationError):
            runtime.tool_intents.execute_intent(reviewed.intent_id)

        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_approved_executes_and_persists_result_and_plan(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = approved_intent(runtime)

        executed = runtime.tool_intents.execute_intent(intent.intent_id, "local_owner")

        self.assertEqual(executed.status, "executed")
        self.assertTrue(executed.execution_result["success"])
        self.assertEqual(executed.execution_plan["selected_target"]["target_id"], "tool_runtime")
        self.assertIsNotNone(executed.executed_at)
        self.assertEqual(executed.executor, "local_owner")
        restarted = create_runtime(settings)
        self.assertEqual(restarted.tool_intents.get_intent(intent.intent_id).status, "executed")

    def test_executed_does_not_execute_twice(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = approved_intent(runtime)
        runtime.tool_intents.execute_intent(intent.intent_id)
        count = runtime.tool_runtime.execution_counts["health.summary"]

        with self.assertRaises(ValidationError):
            runtime.tool_intents.execute_intent(intent.intent_id)

        self.assertEqual(runtime.tool_runtime.execution_counts["health.summary"], count)

    def test_handler_error_marks_intent_failed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = approved_intent(runtime, "conversation.summary")

        failed = runtime.tool_intents.execute_intent(intent.intent_id)

        self.assertEqual(failed.status, "failed")
        self.assertFalse(failed.execution_result["success"])
        self.assertIn("conversation_id", failed.execution_result["error"])
        self.assertIsNotNone(failed.execution_plan)
        self.assertFalse(runtime.tool_intents.can_execute_intent(intent.intent_id))

    def test_missing_tool_marks_intent_failed_controlled(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = approved_intent(runtime)
        runtime.tool_runtime.registry._tools.pop("health.summary")

        failed = runtime.tool_intents.execute_intent(intent.intent_id)

        self.assertEqual(failed.status, "failed")
        self.assertIn("not found", failed.execution_result["error"].lower())

    def test_execution_summary(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = approved_intent(runtime)

        before = runtime.tool_intents.execution_summary(intent.intent_id)
        runtime.tool_intents.execute_intent(intent.intent_id)
        after = runtime.tool_intents.execution_summary(intent.intent_id)

        self.assertTrue(before["can_execute"])
        self.assertFalse(after["can_execute"])
        self.assertEqual(after["status"], "executed")

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = approved_intent(runtime)
        context = runtime.context()

        executed = runtime.commands.execute(
            context,
            f"/execute-tool-intent {intent.intent_id}",
        )
        summary = runtime.commands.execute(
            context,
            f"/tool-intent-execution {intent.intent_id}",
        )

        self.assertEqual(executed.status, "ok")
        self.assertEqual(executed.data["intent"]["status"], "executed")
        self.assertEqual(summary.data["execution"]["status"], "executed")

    def test_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = approved_intent(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        executed = client.post(
            f"/api/tool-intents/{intent.intent_id}/execute",
            json={"executor": "local_owner"},
        )
        summary = client.get(f"/api/tool-intents/{intent.intent_id}/execution")

        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["status"], "executed")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["status"], "executed")

    def test_health_and_readiness(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        approved = approved_intent(runtime)
        failed = approved_intent(runtime, "conversation.summary")
        runtime.tool_intents.execute_intent(failed.intent_id)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(runtime.tool_intents.can_execute_intent(approved.intent_id))
        self.assertEqual(health.executable_tool_intents_count, 1)
        self.assertEqual(health.failed_tool_intents_count, 1)
        self.assertIn("tool_intent_execution.ready", {check.id for check in readiness.checks})


if __name__ == "__main__":
    unittest.main()
