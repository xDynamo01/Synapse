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
from synapse.intelligence_boundary.models import (
    ProcessingBoundary,
    ProviderTrustProfile,
    TrustProfileStatus,
)
from synapse.mcp.models import MCPServerManifest, MCPToolReference
from synapse.mcp_bridge.runtime import MCP_EXECUTION_UNAVAILABLE, MCPToolBridgeRuntime
from synapse.tools.models import ToolExecutionRequest


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


def register_reference(runtime) -> None:
    runtime.mcp.register_tool(
        MCPToolReference(
            server_id="github",
            tool_name="create_issue",
            description="Create a GitHub issue in a future MCP stage.",
            input_schema={"type": "object", "required": ["title"]},
            output_schema={"type": "object"},
        )
    )


class MCPToolBridgeTests(unittest.TestCase):
    def test_connected_mcp_tool_executes_through_canonical_runtime(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.mcp.register_server(
            MCPServerManifest(
                server_id="connected",
                display_name="Connected",
                version="1",
                description="Test adapter",
                transport="test",
                enabled=True,
                installed=True,
            )
        )
        runtime.mcp.register_tool(
            MCPToolReference(
                server_id="connected",
                tool_name="echo",
                description="Echo",
                input_schema={"type": "object", "required": ["value"]},
            )
        )
        runtime.mcp.register_executor("connected", "echo", lambda args: {"echo": args["value"]})
        runtime.intelligence_boundary.register_trust_profile(
            ProviderTrustProfile(
                trust_profile_id="trust-connected",
                provider_id="connected",
                processing_boundary=ProcessingBoundary.EXTERNAL_MCP,
                status=TrustProfileStatus.ACTIVE,
                provenance={"source": "test", "claim": "test executor"},
            )
        )
        runtime.mcp_bridge.sync_from_mcp_registry()
        request = ToolExecutionRequest(
            tool_id="mcp:connected:echo",
            arguments={"value": "ok"},
            caller="local_owner",
            caller_type="user",
        )
        pending = runtime.tool_runtime.execute_tool_call(request)
        runtime.approvals.approve(runtime.context(), pending.metadata["approval_id"])
        completed = runtime.tool_runtime.execute_tool_call(
            ToolExecutionRequest(
                **{**request.__dict__, "approval_id": pending.metadata["approval_id"]}
            )
        )

        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.output, {"echo": "ok"})
        self.assertEqual(runtime.approvals.get_status(pending.metadata["approval_id"]).status, "resumed")
    def test_sync_and_deterministic_id(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)

        status = runtime.mcp_bridge.sync_from_mcp_registry()
        bridged = runtime.mcp_bridge.list_bridge_tools()

        self.assertEqual(status.total_mcp_tools, 1)
        self.assertEqual(status.bridged_tools, 1)
        self.assertEqual(bridged[0].bridge_tool_id, "mcp:github:create_issue")
        self.assertEqual(
            MCPToolBridgeRuntime.bridge_tool_id("GitHub", "Create Issue"),
            "mcp:github:create_issue",
        )

    def test_bridge_projects_tool_definition(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)
        runtime.mcp_bridge.sync_from_mcp_registry()

        definition = runtime.tool_runtime.get_tool("mcp:github:create_issue")

        self.assertEqual(definition.category, "mcp")
        self.assertFalse(definition.enabled)
        self.assertTrue(definition.approval_required)
        self.assertEqual(definition.risk_level, "high")
        self.assertFalse(definition.metadata["execution_implemented"])

    def test_execution_fails_controlled_without_mcp_call(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)
        runtime.mcp_bridge.sync_from_mcp_registry()

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id="mcp:github:create_issue",
                caller="local_owner",
                caller_type="user",
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, MCP_EXECUTION_UNAVAILABLE)
        self.assertEqual(runtime.approvals.list_pending(), [])
        self.assertTrue(all(not state.connected for state in runtime.mcp.health()))

    def test_discovery_lists_mcp_tool_as_unavailable(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)
        runtime.mcp_bridge.sync_from_mcp_registry()

        catalog = runtime.tool_discovery.catalog_for_user()
        view = next(tool for tool in catalog.tools if tool.tool_id == "mcp:github:create_issue")

        self.assertFalse(view.available)
        self.assertTrue(view.requires_approval)
        self.assertEqual(view.reason_unavailable, MCP_EXECUTION_UNAVAILABLE)

    def test_status_and_explanation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)
        runtime.mcp_bridge.sync_from_mcp_registry()

        status = runtime.mcp_bridge.bridge_status()
        explanation = runtime.mcp_bridge.explain_bridge_tool("mcp:github:create_issue")

        self.assertEqual(status.unavailable_tools, 1)
        self.assertFalse(explanation["execution_available"])
        self.assertEqual(explanation["reason"], MCP_EXECUTION_UNAVAILABLE)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)
        context = runtime.context()

        synced = runtime.commands.execute(context, "/mcp-bridge-sync")
        status = runtime.commands.execute(context, "/mcp-bridge")
        detail = runtime.commands.execute(
            context,
            "/mcp-bridge-tool mcp:github:create_issue",
        )

        self.assertEqual(synced.status, "ok")
        self.assertEqual(status.data["status"]["bridged_tools"], 1)
        self.assertEqual(detail.data["reason"], MCP_EXECUTION_UNAVAILABLE)

    def test_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        synced = client.post("/api/mcp/bridge/sync")
        status = client.get("/api/mcp/bridge")
        detail = client.get("/api/mcp/bridge/tools/mcp:github:create_issue")

        self.assertEqual(synced.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["reason"], MCP_EXECUTION_UNAVAILABLE)

    def test_health_and_readiness(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        register_reference(runtime)
        runtime.mcp_bridge.sync_from_mcp_registry()

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.mcp_bridge_runtime_available)
        self.assertEqual(health.mcp_bridged_tools_count, 1)
        self.assertIn("mcp_bridge.ready", {check.id for check in readiness.checks})


if __name__ == "__main__":
    unittest.main()
