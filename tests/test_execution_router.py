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
from synapse.execution_router.models import ExecutionTarget
from synapse.execution_router.registry import ExecutionTargetRegistry
from synapse.mcp.models import MCPToolReference


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
    return directory, create_runtime(settings)


def add_mcp_tool(runtime) -> str:
    runtime.mcp.register_tool(
        MCPToolReference(
            server_id="github",
            tool_name="create_issue",
            description="Future MCP issue creation.",
        )
    )
    runtime.mcp_bridge.sync_from_mcp_registry()
    return "mcp:github:create_issue"


class ExecutionTargetRegistryTests(unittest.TestCase):
    def test_registry(self) -> None:
        registry = ExecutionTargetRegistry()
        target = ExecutionTarget("tool_runtime", "tool_runtime", True, 100)

        registry.register(target)

        self.assertEqual(registry.get("tool_runtime"), target)
        self.assertEqual(registry.list_targets(available=True), [target])


class ExecutionRouterRuntimeTests(unittest.TestCase):
    def test_route_tool_without_execution(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        plan = runtime.execution_router.route_tool("health.summary")

        self.assertEqual(plan.selected_target.target_id, "tool_runtime")
        self.assertTrue(plan.selected_target.available)
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_route_mcp(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        bridge_tool_id = add_mcp_tool(runtime)

        plan = runtime.execution_router.route_mcp(bridge_tool_id)

        self.assertEqual(plan.selected_target.target_id, "mcp_bridge")
        self.assertFalse(plan.selected_target.available)
        self.assertEqual(plan.fallback_targets[0].target_id, "tool_runtime")
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_route_provider(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        provider = runtime.providers.list_providers()[0]

        plan = runtime.execution_router.route_provider(provider.provider_id)

        self.assertEqual(plan.selected_target.target_id, "provider_runtime")
        self.assertEqual(plan.selected_target.metadata["provider_id"], provider.provider_id)
        self.assertEqual(plan.fallback_targets[0].target_id, "plugin_runtime")

    def test_route_intent(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        intent = runtime.tool_intents.create_intent("health.summary")

        plan = runtime.execution_router.route_intent(intent.intent_id)

        self.assertEqual(plan.request_id, intent.intent_id)
        self.assertEqual(plan.selected_target.target_id, "tool_runtime")
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_fallbacks_and_summary(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        plan = runtime.execution_router.route_tool("health.summary")
        summary = runtime.execution_router.execution_summary()

        self.assertEqual(
            {target.target_id for target in plan.fallback_targets},
            {"provider_runtime", "plugin_runtime"},
        )
        self.assertEqual(summary.registered_targets, 4)
        self.assertEqual(summary.available_targets, 3)
        self.assertIn("mcp_tool", summary.routing_table)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        context = runtime.context()

        targets = runtime.commands.execute(context, "/execution-targets")
        plan = runtime.commands.execute(context, "/execution-plan health.summary")
        summary = runtime.commands.execute(context, "/execution-summary")

        self.assertEqual(targets.status, "ok")
        self.assertEqual(plan.data["plan"]["selected_target"]["target_id"], "tool_runtime")
        self.assertEqual(summary.data["summary"]["registered_targets"], 4)
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        targets = client.get("/api/execution/targets")
        plan = client.post("/api/execution/plan", json={"tool_id": "health.summary"})
        summary = client.get("/api/execution/summary")

        self.assertEqual(targets.status_code, 200)
        self.assertEqual(plan.status_code, 200)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(plan.json()["selected_target"]["target_id"], "tool_runtime")
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_health_and_readiness(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.execution_router_available)
        self.assertEqual(health.execution_targets_registered, 4)
        self.assertIn("execution_router.ready", {check.id for check in readiness.checks})


if __name__ == "__main__":
    unittest.main()
