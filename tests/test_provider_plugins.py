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
from synapse.provider_plugins.models import ProviderPluginManifest


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
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Provider Plugin Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    return directory, settings, create_runtime(settings)


class ProviderPluginRuntimeTests(unittest.TestCase):
    def test_seed_plugins_are_listed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        plugin_ids = {plugin.plugin_id for plugin in runtime.provider_plugins.list_plugins()}

        self.assertIn("faster_whisper_plugin", plugin_ids)
        self.assertIn("piper_plugin", plugin_ids)
        self.assertNotIn("vrm_renderer_plugin", plugin_ids)
        self.assertIn("lmstudio_plugin", plugin_ids)

    def test_register_plugin(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.provider_plugins.registry.register_plugin(
            ProviderPluginManifest(
                plugin_id="test_search_plugin",
                name="Test Search Plugin",
                description="Test manifest only.",
                version="0.1.0",
                plugin_type="search",
                providers=["test_search"],
                capabilities=["search.query"],
                adapters=["test_search_adapter"],
                supported_platforms=["windows", "linux", "darwin"],
                requirements=[],
            )
        )

        plugin = runtime.provider_plugins.get_plugin("test_search_plugin")
        self.assertEqual(plugin.plugin_type, "search")
        self.assertFalse(plugin.installed)

    def test_list_by_type(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        speech_plugins = runtime.provider_plugins.list_by_type("speech")

        self.assertEqual(
            {plugin.plugin_id for plugin in speech_plugins},
            {"faster_whisper_plugin", "piper_plugin", "kokoro_plugin"},
        )

    def test_default_state_is_not_installed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        state = runtime.provider_plugins.registry.get_install_state("piper_plugin")
        health = runtime.provider_plugins.plugin_health("piper_plugin")

        self.assertFalse(state.installed)
        self.assertFalse(state.enabled)
        self.assertEqual(health.status, "not_installed")

    def test_enable_and_disable_plugin(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        enabled = runtime.provider_plugins.enable_plugin("piper_plugin", runtime.context())
        disabled = runtime.provider_plugins.disable_plugin("piper_plugin", runtime.context())

        self.assertTrue(enabled.installed)
        self.assertTrue(enabled.enabled)
        self.assertTrue(disabled.installed)
        self.assertFalse(disabled.enabled)

    def test_summary(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        summary = runtime.provider_plugins.summarize_plugins()

        self.assertEqual(summary.total_plugins, 6)
        self.assertEqual(summary.installed_plugins, 0)
        self.assertEqual(summary.by_type["speech"], 3)
        self.assertEqual(summary.by_type["vision"], 2)
        self.assertNotIn("avatar", summary.by_type)
        self.assertEqual(summary.by_type["model"], 1)

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        listed = runtime.commands.execute(runtime.context(), "/provider-plugins")
        detail = runtime.commands.execute(runtime.context(), "/provider-plugin piper_plugin")
        health = runtime.commands.execute(runtime.context(), "/provider-plugin-health")
        enabled = runtime.commands.execute(runtime.context(), "/enable-provider-plugin piper_plugin")
        disabled = runtime.commands.execute(runtime.context(), "/disable-provider-plugin piper_plugin")

        self.assertEqual(listed.status, "ok")
        self.assertEqual(detail.data["plugin"]["plugin_id"], "piper_plugin")
        self.assertEqual(health.status, "ok")
        self.assertTrue(enabled.data["plugin"]["enabled"])
        self.assertFalse(disabled.data["plugin"]["enabled"])

    def test_api(self) -> None:
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

        self.assertEqual(client.get("/api/provider-plugins").status_code, 200)
        self.assertEqual(
            client.get("/api/provider-plugins/piper_plugin").json()["plugin_id"],
            "piper_plugin",
        )
        self.assertEqual(client.get("/api/provider-plugins/health").status_code, 200)
        self.assertEqual(client.get("/api/provider-plugins/summary").json()["total_plugins"], 6)
        self.assertTrue(client.post("/api/provider-plugins/piper_plugin/enable").json()["enabled"])
        self.assertFalse(client.post("/api/provider-plugins/piper_plugin/disable").json()["enabled"])

    def test_health_and_readiness_include_provider_plugins(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.provider_plugin_runtime_available)
        self.assertEqual(health.provider_plugins_not_installed_count, 6)
        self.assertIn("provider_plugins.ready", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
