from __future__ import annotations

import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.intelligence_boundary.errors import BoundaryNotFound
from synapse.tools.models import ToolDefinition, ToolExecutionRequest
from synapse.tools.runtime import ToolRuntime


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
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"], "agent:artemis": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Tool Runtime Test", "mode": "test", "default_agent_id": "artemis"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    write_json(
        settings.data_dir / "agents" / "artemis" / "CONFIG.yaml",
        {
            "id": "artemis",
            "name": "Artemis",
            "role": "Tool runtime test agent",
            "preferred_model": "mock",
            "autonomy": "manual",
            "permissions": ["*"],
        },
    )
    return directory, settings, create_runtime(settings)


class ConcurrentAssetRegistrationGate:
    def __init__(self, delegate):
        self.delegate = delegate
        self.missing = Barrier(2)

    def get_asset(self, asset_id):
        try:
            return self.delegate.get_asset(asset_id)
        except BoundaryNotFound:
            self.missing.wait(timeout=5)
            raise

    def __getattr__(self, name):
        return getattr(self.delegate, name)


class ToolRuntimeV1Tests(unittest.TestCase):
    def test_concurrent_identical_tool_inputs_reuse_one_boundary_asset(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.tool_runtime.egress_gate = ConcurrentAssetRegistrationGate(
            runtime.intelligence_boundary
        )
        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="test.concurrent-echo",
                display_name="Concurrent Echo",
                description="Echo identical concurrent inputs.",
                category="test",
                input_schema={
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": False,
                },
                required_permission="tools.execute",
            ),
            lambda request: {"value": request.arguments["value"]},
        )

        def execute(_index: int):
            return runtime.tool_runtime.execute(
                ToolExecutionRequest(
                    tool_id="test.concurrent-echo",
                    arguments={"value": "same"},
                    caller="local_owner",
                    caller_type="user",
                )
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(execute, range(2)))

        self.assertTrue(all(result.success for result in results), results)
        tool_inputs = [
            item
            for item in runtime.intelligence_boundary.list_assets()
            if item.asset_id.startswith("tool-input-")
        ]
        self.assertEqual(len(tool_inputs), 1)

    def test_schema_preview_and_idempotency(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        calls = []
        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="test.echo",
                display_name="Echo",
                description="Echo a value.",
                category="test",
                input_schema={
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": False,
                },
                required_permission="tools.execute",
            ),
            lambda request: calls.append(request.arguments["value"]) or {"value": request.arguments["value"]},
        )
        request = ToolExecutionRequest(
            tool_id="test.echo",
            arguments={"value": "one"},
            caller="local_owner",
            idempotency_key="same-call",
        )
        preview = runtime.tool_runtime.preview(request)
        first = runtime.tool_runtime.execute_tool_call(request)
        second = runtime.tool_runtime.execute_tool_call(request)

        self.assertEqual(preview.normalized_arguments, {"value": "one"})
        self.assertTrue(preview.config_hash)
        self.assertEqual(calls, ["one"])
        self.assertEqual(first.call_id, second.call_id)
        with self.assertRaisesRegex(Exception, "Unknown arguments"):
            runtime.tool_runtime.preview(
                ToolExecutionRequest(
                    tool_id="test.echo",
                    arguments={"value": "one", "extra": True},
                    caller="local_owner",
                )
            )

    def test_registry_registers_tool(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        tool_ids = {tool.tool_id for tool in runtime.tool_runtime.list_tools()}

        self.assertIn("health.summary", tool_ids)
        self.assertIn("tool.summary", tool_ids)

    def test_register_and_execute_mock_tool(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="mock.echo",
                display_name="Mock Echo",
                description="Echo arguments.",
                category="test",
            ),
            lambda request: {"echo": request.arguments},
        )
        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id="mock.echo",
                arguments={"value": "hello"},
                caller="test",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["echo"]["value"], "hello")

    def test_missing_tool_returns_controlled_error(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(tool_id="missing.tool", caller="test")
        )

        self.assertFalse(result.success)
        self.assertIn("Tool not found", result.error or "")

    def test_critical_mock_requires_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="test.danger",
                display_name="Test Danger",
                description="Test-only critical tool.",
                category="test",
                input_schema={"type": "object", "properties": {}},
                risk_level="critical",
                approval_required=True,
                required_permission="tools.execute",
            ),
            lambda request: {"executed": True},
        )
        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(tool_id="test.danger", caller="local_owner", caller_type="user")
        )

        self.assertFalse(result.success)
        self.assertTrue(result.metadata["approval_required"])
        self.assertIsNotNone(result.metadata["approval_id"])
        self.assertEqual(len(runtime.approvals.list_pending()), 1)

    def test_critical_mock_does_not_execute_before_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(tool_id="danger.mock", caller="local_owner", caller_type="user")
        )

        self.assertEqual(result.output, {})
        self.assertNotIn("executed", result.output)

    def test_dry_run_evaluates_without_execution_or_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id="danger.mock",
                caller="local_owner",
                caller_type="user",
                dry_run=True,
            )
        )

        self.assertFalse(result.success)
        self.assertTrue(result.metadata["dry_run"])
        self.assertTrue(result.metadata["decision"]["requires_approval"])
        self.assertIsNone(result.metadata["approval_id"])
        self.assertEqual(runtime.approvals.list_pending(), [])

    def test_tool_failure_returns_controlled_error(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        def fail(_: ToolExecutionRequest) -> dict:
            raise RuntimeError("expected failure")

        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="mock.fail",
                display_name="Mock Fail",
                description="Fail deterministically.",
                category="test",
            ),
            fail,
        )
        result = runtime.tool_runtime.execute(ToolExecutionRequest(tool_id="mock.fail", caller="test"))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "expected failure")

    def test_execution_log_is_written(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id="tool.summary",
                caller="local_owner",
                caller_type="user",
            )
        )

        log_path = settings.data_dir / "tools" / "execution_log.jsonl"
        records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[-1]["tool"], "tool.summary")
        self.assertTrue(records[-1]["success"])
        self.assertIn("decision", records[-1])
        self.assertTrue(records[-1]["decision"]["allowed"])

    def test_execution_log_includes_agent_and_approval_decision(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id="danger.mock",
                caller="local_owner",
                caller_type="user",
                agent_id="artemis",
            )
        )

        log_path = settings.data_dir / "tools" / "execution_log.jsonl"
        records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[-1]["agent_id"], "artemis")
        self.assertEqual(records[-1]["caller_type"], "user")
        self.assertTrue(records[-1]["decision"]["requires_approval"])
        self.assertIsNotNone(records[-1]["approval_id"])

    def test_health_and_summary(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.tool_runtime.health()
        summary = runtime.tool_runtime.summary()

        self.assertIn("health.summary", health)
        self.assertTrue(health["health.summary"].available)
        self.assertGreaterEqual(summary["tool_count"], 7)

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        tools = runtime.commands.execute(runtime.context(), "/tools")
        detail = runtime.commands.execute(runtime.context(), "/tool tool.summary")
        health = runtime.commands.execute(runtime.context(), "/tool-health")
        run = runtime.commands.execute(runtime.context(), "/run-tool tool.summary")
        decision = runtime.commands.execute(runtime.context(), "/tool-decision danger.mock")

        self.assertEqual(tools.status, "ok")
        self.assertEqual(detail.status, "ok")
        self.assertEqual(health.status, "ok")
        self.assertEqual(run.status, "ok")
        self.assertEqual(decision.status, "ok")
        self.assertTrue(decision.data["decision"]["requires_approval"])
        self.assertTrue(run.data["result"]["success"])

    def test_run_tool_command_accepts_agent_and_dry_run(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(
            runtime.context(),
            "/run-tool danger.mock --agent artemis --dry-run",
        )

        self.assertEqual(result.status, "error")
        self.assertTrue(result.data["result"]["metadata"]["dry_run"])
        self.assertTrue(result.data["result"]["metadata"]["decision"]["requires_approval"])

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

        listed = client.get("/api/tools")
        detail = client.get("/api/tools/tool.summary")
        health = client.get("/api/tools/health")
        executed = client.post(
            "/api/tools/run",
            json={"tool_id": "tool.summary", "caller": "local_owner", "caller_type": "user"},
        )
        decision = client.post(
            "/api/tools/decision",
            json={
                "tool_id": "danger.mock",
                "caller": "local_owner",
                "caller_type": "user",
            },
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(decision.status_code, 200)
        self.assertTrue(executed.json()["success"])
        self.assertTrue(decision.json()["requires_approval"])

    def test_health_and_readiness_include_tool_runtime(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.tool_runtime_available)
        self.assertTrue(health.tool_permission_bridge_available)
        self.assertGreaterEqual(health.tool_count, 7)
        self.assertIn(
            "tool_runtime.ready",
            {check.id for check in readiness.checks},
        )
        self.assertIn(
            "tool_permissions.ready",
            {check.id for check in readiness.checks},
        )

    def test_seed_tool_reuses_existing_runtimes(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id="provider.summary",
                caller="local_owner",
                caller_type="user",
            )
        )

        self.assertTrue(result.success)
        self.assertIn("provider_count", result.output)


class StandaloneToolRuntimeTests(unittest.TestCase):
    def test_runtime_can_be_used_with_mock_tool_only(self) -> None:
        directory, _, container = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime = ToolRuntime(container.data_dir, container.events)
        runtime.register(
            ToolDefinition(
                tool_id="mock.only",
                display_name="Mock Only",
                description="Standalone mock.",
                category="test",
            ),
            lambda request: {"ok": True},
        )

        result = runtime.execute(ToolExecutionRequest(tool_id="mock.only", caller="test"))

        self.assertEqual([tool.tool_id for tool in runtime.list_tools()], ["mock.only"])
        self.assertFalse(result.success)
        self.assertIn("permission bridge unavailable", result.error or "")


if __name__ == "__main__":
    unittest.main()
