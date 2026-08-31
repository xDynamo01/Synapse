from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.capabilities.models import Capability
from synapse.capabilities.registry import CapabilityRegistry
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import load_structured_file
from synapse.tools.calls import ToolCallRequest


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
            "agent:worker": [
                "filesystem.read",
                "filesystem.list",
                "filesystem.search",
                "filesystem.write",
                "tasks.create",
                "tasks.update",
                "agents.message",
                "web.search",
            ],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Capability Test",
            "mode": "test",
            "default_agent_id": "worker",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    write_json(
        settings.data_dir / "agents" / "worker" / "CONFIG.yaml",
        {
            "id": "worker",
            "name": "Worker",
            "role": "Generic test worker.",
            "permissions": [
                "filesystem.read",
                "filesystem.list",
                "filesystem.search",
                "filesystem.write",
                "tasks.create",
                "tasks.update",
                "agents.message",
                "web.search",
            ],
        },
    )
    return directory, settings, create_runtime(settings)


def update_agent_capabilities(settings: Settings, allow=None, deny=None) -> None:
    path = settings.data_dir / "agents" / "worker" / "CONFIG.yaml"
    raw = load_structured_file(path)
    raw["capabilities"] = {
        "allow": list(allow or []),
        "deny": list(deny or []),
    }
    write_json(path, raw)


class CapabilityRuntimeTests(unittest.TestCase):
    def test_register_capability(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            Capability(
                capability_id="system.inspect",
                name="Inspect System",
                description="Inspect local system state.",
                category="system",
                risk_level="low",
            )
        )

        self.assertEqual(registry.get("system.inspect").name, "Inspect System")

    def test_list_capabilities(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        capability_ids = {
            capability.capability_id
            for capability in runtime.capabilities.list_capabilities()
        }

        self.assertIn("filesystem.read", capability_ids)
        self.assertIn("notification.read", capability_ids)

    def test_duplicate_capability_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        capability = Capability(
            capability_id="system.inspect",
            name="Inspect System",
            description="Inspect local system state.",
            category="system",
            risk_level="low",
        )
        registry.register(capability)

        with self.assertRaises(ValidationError):
            registry.register(capability)

    def test_agent_with_allowed_capability(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        update_agent_capabilities(settings, allow=["filesystem.read"])
        runtime = create_runtime(settings)

        decision = runtime.capabilities.check_agent_capability(
            "worker",
            "filesystem.read",
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "agent_allow")

    def test_agent_with_denied_capability(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        update_agent_capabilities(settings, deny=["filesystem.read"])
        runtime = create_runtime(settings)

        decision = runtime.capabilities.check_agent_capability(
            "worker",
            "filesystem.read",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "agent_deny")

    def test_fallback_for_agent_without_capability_declarations(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        decision = runtime.capabilities.check_agent_capability(
            "worker",
            "task.create",
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "permission_fallback")

    def test_tool_execution_respects_capability_mapping(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        update_agent_capabilities(settings, deny=["filesystem.read"])
        runtime = create_runtime(settings)
        (settings.data_dir / "notes.txt").write_text("secret", encoding="utf-8")
        context = runtime.context(actor_id="worker", actor_type="agent")

        result = runtime.tool_router.execute_call(
            context,
            ToolCallRequest(name="read_file", arguments={"path": "notes.txt"}),
        )

        self.assertFalse(result.success)
        self.assertIn("filesystem.read", result.error)

    def test_explain_agent_capability(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        explanation = runtime.capabilities.explain_agent_capability(
            "worker",
            "filesystem.read",
        )

        self.assertEqual(explanation["capability"]["capability_id"], "filesystem.read")
        self.assertTrue(explanation["decision"]["allowed"])

    def test_capability_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        capabilities = runtime.commands.execute(runtime.context(), "/capabilities")
        agent_capabilities = runtime.commands.execute(
            runtime.context(),
            "/agent-capabilities worker",
        )

        self.assertEqual(capabilities.status, "ok")
        self.assertGreater(len(capabilities.data["capabilities"]), 0)
        self.assertEqual(agent_capabilities.status, "ok")
        self.assertGreater(len(agent_capabilities.data["capabilities"]), 0)

    def test_capability_api(self) -> None:
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

        capabilities = client.get("/api/capabilities")
        detail = client.get("/api/capabilities/filesystem.read")
        agent_capabilities = client.get("/api/agents/worker/capabilities")

        self.assertEqual(capabilities.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(agent_capabilities.status_code, 200)
        self.assertEqual(detail.json()["capability_id"], "filesystem.read")


if __name__ == "__main__":
    unittest.main()
