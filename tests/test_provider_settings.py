from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.api.routes import router
from synapse.core.app import create_runtime
from synapse.core.config import Settings


class MemoryCredentials:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, provider_id: str) -> str | None:
        return self.values.get(provider_id)

    def set(self, provider_id: str, value: str) -> None:
        self.values[provider_id] = value

    def clear(self, provider_id: str) -> None:
        self.values.pop(provider_id, None)


class ProviderSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        settings = Settings(
            project_root=PROJECT_ROOT,
            data_dir=Path(self.directory.name) / "data",
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
        self.runtime = create_runtime(settings)
        self.runtime.provider_settings.credentials = MemoryCredentials()
        self.runtime.provider_settings.http_get = lambda _url, _headers, _timeout: None

    def test_lists_seed_configs_and_persists_endpoint_and_model(self) -> None:
        self.assertEqual(len(self.runtime.provider_settings.list_settings()), 8)

        updated = self.runtime.provider_settings.update_setting(
            "openai_compatible",
            enabled=True,
            endpoint="http://127.0.0.1:9000/v1",
            default_model="local-model",
        )

        self.assertTrue(updated.enabled)
        self.assertEqual(updated.default_model, "local-model")
        self.assertIn("127.0.0.1:9000", self.runtime.provider_settings.path.read_text())
        model_provider = next(
            item
            for item in self.runtime.model_hub.list_providers()
            if item.provider_id == "openai_compatible"
        )
        self.assertEqual(model_provider.endpoint, "http://127.0.0.1:9000/v1")

    def test_lmstudio_uses_single_frontend_facing_provider_identity(self) -> None:
        provider_ids = {item.provider_id for item in self.runtime.provider_settings.list_settings()}
        self.assertIn("lmstudio", provider_ids)
        self.assertNotIn("lmstudio_local", provider_ids)

        updated = self.runtime.provider_settings.update_setting(
            "lmstudio",
            enabled=True,
            endpoint="http://127.0.0.1:1234/v1",
            default_model="local-model",
        )
        alias = self.runtime.provider_settings.get_setting("lmstudio_local")

        self.assertEqual(updated.provider_id, "lmstudio")
        self.assertEqual(alias.provider_id, "lmstudio")
        self.assertEqual(alias.default_model, "local-model")
        self.assertIn("lmstudio_local", self.runtime.provider_settings.path.read_text())

        model_provider_ids = {item.provider_id for item in self.runtime.model_hub.list_providers()}
        self.assertIn("lmstudio", model_provider_ids)

    def test_key_is_masked_and_never_written_to_config(self) -> None:
        secret = "sk-super-secret-value"
        updated = self.runtime.provider_settings.update_setting(
            "openai", enabled=True, api_key=secret
        )

        self.assertTrue(updated.has_api_key)
        self.assertEqual(updated.masked_key, "********alue")
        serialized = json.dumps(updated.__dict__)
        self.assertNotIn(secret, serialized)
        self.assertNotIn(secret, self.runtime.provider_settings.path.read_text())

    def test_clear_key_and_controlled_connection_test(self) -> None:
        self.runtime.provider_settings.update_setting(
            "groq", enabled=True, api_key="gsk-test-key"
        )
        result = self.runtime.provider_settings.test_connection("groq")
        self.assertTrue(result.success)
        self.assertEqual(result.status, "available")

        cleared = self.runtime.provider_settings.clear_key("groq")
        self.assertFalse(cleared.has_api_key)
        self.assertEqual(cleared.status, "unconfigured")

    def test_disabled_provider_test_does_not_make_network_call(self) -> None:
        calls: list[str] = []
        self.runtime.provider_settings.http_get = lambda url, _headers, _timeout: calls.append(url)
        result = self.runtime.provider_settings.test_connection("anthropic")
        self.assertFalse(result.success)
        self.assertEqual(result.status, "disabled")
        self.assertEqual(calls, [])

    def test_api_never_returns_raw_key(self) -> None:
        app = FastAPI()
        app.state.runtime = self.runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        response = client.patch(
            "/api/provider-settings/openrouter",
            json={"enabled": True, "api_key": "openrouter-secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("openrouter-secret", response.text)
        self.assertTrue(response.json()["has_api_key"])
        self.assertEqual(client.get("/api/provider-settings").status_code, 200)
        self.assertEqual(client.get("/api/provider-settings/lmstudio").status_code, 200)
        self.assertEqual(
            client.patch(
                "/api/provider-settings/lmstudio",
                json={
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:1234/v1",
                    "default_model": "local-model",
                },
            ).json()["provider_id"],
            "lmstudio",
        )
        self.assertEqual(client.post("/api/provider-settings/openrouter/test").status_code, 200)
        self.assertEqual(
            client.post("/api/provider-settings/openrouter/clear-key").status_code,
            200,
        )

    def test_health_and_readiness_expose_provider_settings(self) -> None:
        health = self.runtime.health.summary()
        readiness = self.runtime.readiness.evaluate()
        self.assertTrue(health.provider_settings_available)
        self.assertTrue(any(item.id == "provider_settings.ready" for item in readiness.checks))


if __name__ == "__main__":
    unittest.main()
