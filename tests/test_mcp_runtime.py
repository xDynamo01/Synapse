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
from synapse.mcp.models import MCPServerManifest, MCPToolReference
from synapse.mcp.registry import MCPRegistry


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


def custom_server() -> MCPServerManifest:
    return MCPServerManifest(
        server_id="custom_mock",
        display_name="Custom Mock",
        version="1.0.0",
        description="Test-only MCP manifest.",
        transport="unconfigured",
        enabled=True,
        installed=False,
    )


class MCPRegistryTests(unittest.TestCase):
    def test_server_and_tool_registration(self) -> None:
        registry = MCPRegistry()
        registry.register_server(custom_server())
        registry.register_tool_reference(
            MCPToolReference(
                server_id="custom_mock",
                tool_name="mock.echo",
                description="Mock reference.",
            )
        )

        self.assertEqual(registry.get_server("custom_mock").display_name, "Custom Mock")
        self.assertEqual(registry.list_tools()[0].tool_name, "mock.echo")
        self.assertEqual(registry.summary().total_servers, 1)
        self.assertEqual(registry.summary().total_tools, 1)
        self.assertEqual(registry.summary().connected_servers, 0)


class MCPRuntimeTests(unittest.TestCase):
    def test_seed_servers_are_registered_and_disconnected(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        servers = runtime.mcp.list_servers()
        server_ids = {server.server_id for server in servers}

        self.assertEqual(
            server_ids,
            {"local_fs", "github", "browser", "unreal", "blender", "docker"},
        )
        self.assertTrue(all(not server.installed for server in servers))
        self.assertTrue(all(not state.connected for state in runtime.mcp.health()))

    def test_registration_persists_without_connection(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.mcp.register_server(custom_server())
        runtime.mcp.register_tool(
            MCPToolReference(
                server_id="custom_mock",
                tool_name="mock.echo",
                description="Mock reference.",
                input_schema={"type": "object"},
            )
        )

        restarted = create_runtime(settings)

        self.assertEqual(restarted.mcp.get_server("custom_mock").version, "1.0.0")
        self.assertEqual(restarted.mcp.list_tools("custom_mock")[0].tool_name, "mock.echo")
        self.assertFalse(
            next(
                state.connected
                for state in restarted.mcp.health()
                if state.server_id == "custom_mock"
            )
        )
        self.assertTrue((settings.data_dir / "mcp" / "servers.yaml").exists())
        self.assertTrue((settings.data_dir / "mcp" / "tool_registry.yaml").exists())

    def test_summary(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        summary = runtime.mcp.summary()

        self.assertEqual(summary.total_servers, 6)
        self.assertEqual(summary.enabled_servers, 0)
        self.assertEqual(summary.connected_servers, 0)
        self.assertEqual(summary.total_tools, 0)

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        context = runtime.context()

        servers = runtime.commands.execute(context, "/mcp-servers")
        server = runtime.commands.execute(context, "/mcp-server github")
        tools = runtime.commands.execute(context, "/mcp-tools")
        summary = runtime.commands.execute(context, "/mcp-summary")

        self.assertEqual(servers.status, "ok")
        self.assertEqual(server.data["server"]["server_id"], "github")
        self.assertEqual(tools.data["tools"], [])
        self.assertEqual(summary.data["summary"]["connected_servers"], 0)

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

        servers = client.get("/api/mcp/servers")
        server = client.get("/api/mcp/servers/github")
        tools = client.get("/api/mcp/tools")
        summary = client.get("/api/mcp/summary")

        self.assertEqual(servers.status_code, 200)
        self.assertEqual(server.status_code, 200)
        self.assertEqual(tools.status_code, 200)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["connected_servers"], 0)

    def test_health_and_readiness(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.mcp_runtime_available)
        self.assertEqual(health.mcp_registered_servers, 6)
        self.assertEqual(health.mcp_registered_tools, 0)
        self.assertIn("mcp.ready", {check.id for check in readiness.checks})


if __name__ == "__main__":
    unittest.main()
