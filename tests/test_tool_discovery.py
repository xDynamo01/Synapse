from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.tool_discovery.runtime import ToolDiscoveryRuntime
from synapse.tools.models import ToolDefinition
from synapse.tools.runtime import ToolRuntime


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
    permissions = settings.data_dir / "config" / "permissions.yaml"
    permissions.write_text(
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
    system = settings.data_dir / "config" / "system.yaml"
    system.write_text(
        json.dumps(
            {
                "system": {
                    "name": "Synapse V2 Tool Discovery Test",
                    "mode": "test",
                    "default_agent_id": "artemis",
                },
                "models": {
                    "default_provider": "mock",
                    "providers": {"mock": {"model": "test"}},
                },
            }
        ),
        encoding="utf-8",
    )
    agent = settings.data_dir / "agents" / "artemis" / "CONFIG.yaml"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text(
        json.dumps(
            {
                "id": "artemis",
                "name": "Artemis",
                "role": "Tool discovery test agent",
                "preferred_model": "mock",
                "autonomy": "manual",
                "permissions": ["*"],
            }
        ),
        encoding="utf-8",
    )
    return directory, create_runtime(settings)


class ToolDiscoveryRuntimeTests(unittest.TestCase):
    def test_empty_catalog(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        data_dir = DataDir(Path(directory.name))
        tools = ToolRuntime(data_dir, EventBus(Path(directory.name)))
        discovery = ToolDiscoveryRuntime(tools)

        catalog = discovery.catalog_for_user()

        self.assertEqual(catalog.total_tools, 0)
        self.assertEqual(catalog.tools, [])

    def test_complete_catalog_and_approval_tool(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        catalog = runtime.tool_discovery.catalog_for_agent("artemis")
        views = {tool.tool_id: tool for tool in catalog.tools}

        self.assertEqual(catalog.total_tools, len(runtime.tool_runtime.registry.list_registered_tools()))
        self.assertIn("read_file", views)
        self.assertIn("edit_file", views)
        self.assertIn("delete_file", views)
        self.assertTrue(views["health.summary"].available)
        self.assertFalse(views["danger.mock"].available)
        self.assertTrue(views["danger.mock"].requires_approval)
        self.assertEqual(views["danger.mock"].reason_unavailable, "Approval required")
        self.assertEqual(runtime.approvals.list_pending(), [])

    def test_capability_requirement_marks_tool_unavailable(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        executed = []
        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="capability.mock",
                display_name="Capability Mock",
                description="Requires an unavailable capability.",
                category="test",
                required_capability="capability.missing",
            ),
            lambda request: executed.append(request) or {"executed": True},
        )

        catalog = runtime.tool_discovery.catalog_for_agent("artemis")
        view = next(tool for tool in catalog.tools if tool.tool_id == "capability.mock")

        self.assertFalse(view.available)
        self.assertIn("capability", (view.reason_unavailable or "").lower())
        self.assertEqual(executed, [])

    def test_disabled_tool_is_unavailable(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="disabled.mock",
                display_name="Disabled Mock",
                description="Disabled tool.",
                category="test",
                enabled=False,
            ),
            lambda request: {"executed": True},
        )

        catalog = runtime.tool_discovery.catalog_for_user()
        view = next(tool for tool in catalog.tools if tool.tool_id == "disabled.mock")

        self.assertFalse(view.available)
        self.assertEqual(view.reason_unavailable, "Tool is disabled")

    def test_explain_tool(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        explanation = runtime.tool_discovery.explain_tool("danger.mock")

        self.assertEqual(explanation.tool.tool_id, "danger.mock")
        self.assertEqual(explanation.required_permission, "tools.execute")
        self.assertTrue(explanation.tool.requires_approval)

    def test_agent_runtime_exposes_catalog(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        catalog = runtime.agent_runtime.available_tools("artemis")

        self.assertEqual(catalog.agent_id, "artemis")
        self.assertGreater(catalog.total_tools, 0)
    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        context = runtime.context()

        agent = runtime.commands.execute(context, "/agent-tools artemis")
        user = runtime.commands.execute(context, "/tool-catalog")
        explanation = runtime.commands.execute(context, "/tool-explain danger.mock")

        self.assertEqual(agent.status, "ok")
        self.assertEqual(user.status, "ok")
        self.assertEqual(explanation.status, "ok")
        self.assertEqual(explanation.data["tool"]["tool"]["tool_id"], "danger.mock")

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

        agent = client.get("/api/agents/artemis/tools")
        user = client.get("/api/tools/catalog")
        explanation = client.get("/api/tools/explain/danger.mock")

        self.assertEqual(agent.status_code, 200)
        self.assertEqual(user.status_code, 200)
        self.assertEqual(explanation.status_code, 200)
        self.assertEqual(explanation.json()["tool"]["tool_id"], "danger.mock")

    def test_health_and_readiness(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.tool_discovery_runtime_available)
        self.assertIn("tool_discovery.ready", {check.id for check in readiness.checks})
        self.assertEqual(asdict(health)["tool_discovery_runtime_available"], True)


if __name__ == "__main__":
    unittest.main()
