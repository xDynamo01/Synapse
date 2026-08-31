from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_test_agent
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.data_dir import DataDir
from synapse.core.serialization import load_structured_file
from synapse.model_providers.models import LMStudioConfig, LMStudioHealth, LMStudioModel


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
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Model Hub Test", "mode": "test"},
            "models": {
                "default_provider": "ollama",
                "providers": {
                    "ollama": {
                        "base_url": "http://127.0.0.1:11434",
                        "model": "test-model",
                    },
                    "openai_compatible": {"base_url": None, "model": None},
                },
            },
        },
    )
    return directory, settings, create_runtime(settings)


class ModelHubTests(unittest.TestCase):
    def test_clean_data_dir_seeds_v001_lmstudio_defaults(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        data_dir = Path(directory.name) / "data"

        DataDir(data_dir).bootstrap()

        system = load_structured_file(data_dir / "config" / "system.yaml")
        provider_settings = load_structured_file(data_dir / "config" / "provider_settings.yaml")
        lmstudio_provider = load_structured_file(data_dir / "config" / "lmstudio_provider.yaml")
        local_chat_policy = load_structured_file(data_dir / "config" / "local_chat_policy.yaml")
        model_defaults = load_structured_file(data_dir / "model_hub" / "defaults.yaml")
        orchestrator = load_structured_file(data_dir / "agents" / "orchestrator" / "CONFIG.yaml")

        self.assertEqual(system["models"]["default_provider"], "lmstudio")
        self.assertEqual(system["models"]["providers"]["lmstudio"]["model"], "gemma-4-e2b-it-qat")
        self.assertEqual(
            provider_settings["providers"]["lmstudio_local"]["default_model"],
            "gemma-4-e2b-it-qat",
        )
        self.assertTrue(provider_settings["providers"]["lmstudio_local"]["enabled"])
        self.assertFalse(provider_settings["providers"]["ollama_local"]["enabled"])
        self.assertEqual(lmstudio_provider["lmstudio"]["default_model"], "gemma-4-e2b-it-qat")
        self.assertTrue(lmstudio_provider["lmstudio"]["enabled"])
        self.assertTrue(local_chat_policy["local_chat"]["enabled"])
        self.assertEqual(model_defaults["default_provider"], "lmstudio")
        self.assertEqual(model_defaults["default_chat_model"], "gemma-4-e2b-it-qat")
        self.assertEqual(orchestrator["preferred_model"], "lmstudio/gemma-4-e2b-it-qat")

    def test_routing_api_and_commands_use_canonical_services(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")
        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_test_agent(
            settings.data_dir,
            "router_agent",
            role="worker",
            extra={"preferred_model": "ollama/test-model"},
        )
        runtime = create_runtime(settings)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        resolved = client.post("/api/models/resolve", json={"agent_id": "router_agent"})
        capabilities = client.get("/api/models/providers/ollama/capabilities")
        command = runtime.commands.execute(runtime.context(), "/model-resolve router_agent")

        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.json()["provider_id"], "ollama")
        self.assertIn("streaming", capabilities.json()["capabilities"])
        self.assertEqual(command.status, "ok")

    def test_detects_default_lmstudio_library_and_supported_files(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        user_profile = Path(directory.name) / "user"
        library = user_profile / ".lmstudio" / "models" / "publisher" / "model"
        library.mkdir(parents=True)
        gguf = library / "example-Q5_K_M.gguf"
        gguf.write_bytes(b"gguf-model")
        (library / "weights.safetensors").write_bytes(b"weights")

        with patch.dict("os.environ", {"USERPROFILE": str(user_profile)}):
            runtime.model_hub.refresh()

        detected = [
            model
            for model in runtime.model_hub.list_catalog()
            if model.origin == "LM Studio Library"
        ]
        self.assertEqual({model.type for model in detected}, {"gguf", "safetensors"})
        gguf_model = next(model for model in detected if model.type == "gguf")
        self.assertEqual(gguf_model.quantization, "Q5_K_M")
        self.assertEqual(gguf_model.size_bytes, gguf.stat().st_size)
        self.assertEqual(gguf_model.metadata["extension"], ".gguf")

    def test_ollama_and_lmstudio_server_offline_do_not_break_refresh(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.lmstudio.load_config = lambda: LMStudioConfig(  # type: ignore[method-assign]
            base_url="http://127.0.0.1:1234/v1",
            enabled=True,
            timeout_seconds=30,
            default_model=None,
            metadata={},
        )
        with patch(
            "synapse.model_hub.runtime._get_json",
            return_value=({}, "offline"),
        ):
            result = runtime.model_hub.refresh()

        providers = {item.provider_id: item for item in runtime.model_hub.list_providers()}
        self.assertGreaterEqual(result.catalog_size, 1)
        self.assertEqual(providers["ollama"].status, "unavailable")
        self.assertEqual(providers["lmstudio"].metadata["server_message"], "offline")

    def test_remote_model_servers_are_added_to_catalog(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.lmstudio.load_config = lambda: LMStudioConfig(  # type: ignore[method-assign]
            base_url="http://127.0.0.1:1234/v1",
            enabled=True,
            timeout_seconds=30,
            default_model=None,
            metadata={},
        )

        def fake_get_json(url: str, timeout: float = 1.0):
            del timeout
            if url.endswith("/api/tags"):
                return {
                    "models": [
                        {
                            "name": "qwen:latest",
                            "size": 123,
                            "details": {"quantization_level": "Q4_K_M"},
                        }
                    ]
                }, None
            return {"data": [{"id": "studio-loaded"}]}, None

        with patch("synapse.model_hub.runtime._get_json", side_effect=fake_get_json):
            result = runtime.model_hub.refresh()

        catalog = {model.id: model for model in runtime.model_hub.list_catalog()}
        self.assertIn("ollama:qwen:latest", catalog)
        self.assertIn("lmstudio:studio-loaded", catalog)
        self.assertEqual(catalog["ollama:qwen:latest"].quantization, "Q4_K_M")
        self.assertGreaterEqual(result.catalog_size, 3)

    def test_catalog_aggregates_configured_and_lmstudio_models(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.lmstudio.health = lambda: LMStudioHealth(  # type: ignore[method-assign]
            True, "http://127.0.0.1:1234/v1", "now", 1
        )
        runtime.lmstudio.list_models = lambda: [LMStudioModel("studio-model")]  # type: ignore[method-assign]

        with (
            patch.dict("os.environ", {"USERPROFILE": directory.name}),
            patch("synapse.model_hub.runtime._get_json", return_value=(None, "offline")),
        ):
            result = runtime.model_hub.refresh()
        catalog = runtime.model_hub.list_catalog()

        self.assertEqual(result.catalog_size, 2)
        self.assertEqual({model.name for model in catalog}, {"test-model", "studio-model"})

    def test_providers_are_centralized_without_secrets(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        providers = runtime.model_hub.list_providers()
        serialized = json.dumps([provider.metadata for provider in providers]).lower()

        self.assertEqual(
            {provider.provider_id for provider in providers},
            {
                "lmstudio",
                "ollama",
                "openai",
                "anthropic",
                "gemini",
                "groq",
                "openrouter",
                "openai_compatible",
            },
        )
        self.assertNotIn("api_key", serialized)

    def test_defaults_are_persisted_across_restart(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        saved = runtime.model_hub.update_defaults(
            default_chat_model="test-model",
            default_provider="ollama",
            preferred_runtime="llama.cpp",
        )
        restarted = create_runtime(settings)

        self.assertEqual(saved.preferred_runtime, "llama.cpp")
        self.assertEqual(restarted.model_hub.get_defaults(), saved)

    def test_local_model_defaults_enable_local_chat_and_lmstudio_provider(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.model_hub.update_defaults(
            default_chat_model="local-model",
            default_provider="lmstudio",
            preferred_runtime="lmstudio",
        )

        local_chat_policy = load_structured_file(settings.data_dir / "config" / "local_chat_policy.yaml")
        lmstudio_provider = load_structured_file(settings.data_dir / "config" / "lmstudio_provider.yaml")

        self.assertTrue(local_chat_policy["local_chat"]["enabled"])
        self.assertEqual(local_chat_policy["local_chat"]["provider_id"], "lmstudio_local")
        self.assertTrue(lmstudio_provider["lmstudio"]["enabled"])
        self.assertEqual(lmstudio_provider["lmstudio"]["default_model"], "local-model")

    def test_gguf_folders_are_managed_without_moving_files(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        model_dir = Path(directory.name) / "models"
        model_dir.mkdir()
        model_path = model_dir / "sample-Q4_K_M.gguf"
        model_path.write_bytes(b"model")

        folder = runtime.model_hub.add_folder(str(model_dir))
        runtime.model_hub.refresh()
        model = next(item for item in runtime.model_hub.list_catalog() if item.type == "gguf")

        self.assertTrue(model_path.exists())
        self.assertEqual(model.quantization, "Q4_K_M")
        self.assertEqual(runtime.model_hub.list_folders()[0].model_count, 1)
        runtime.model_hub.remove_folder(folder.folder_id)
        self.assertEqual(runtime.model_hub.list_folders(), [])
        self.assertTrue(model_path.exists())

    def test_provider_unavailable_does_not_break_refresh(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.lmstudio.health = lambda: LMStudioHealth(  # type: ignore[method-assign]
            False, "http://127.0.0.1:1234/v1", "now", 0, "offline"
        )

        with (
            patch.dict("os.environ", {"USERPROFILE": directory.name}),
            patch("synapse.model_hub.runtime._get_json", return_value=(None, "offline")),
        ):
            result = runtime.model_hub.refresh()
        lmstudio = next(
            provider
            for provider in runtime.model_hub.list_providers()
            if provider.provider_id == "lmstudio"
        )

        self.assertEqual(lmstudio.status, "unavailable")
        self.assertGreaterEqual(result.catalog_size, 1)

    def test_health_and_readiness_include_model_hub(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.model_hub_available)
        self.assertGreaterEqual(health.model_catalog_size, 1)
        self.assertEqual(health.model_provider_count, 8)
        self.assertIn("model_hub.ready", [check.id for check in readiness.checks])

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

        self.assertEqual(client.get("/api/models/catalog").status_code, 200)
        self.assertEqual(len(client.get("/api/models/providers").json()), 8)
        response = client.post(
            "/api/models/default",
            json={
                "default_chat_model": "test-model",
                "default_provider": "ollama",
                "preferred_runtime": "ollama",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["default_chat_model"], "test-model")
        self.assertEqual(client.post("/api/models/refresh").status_code, 200)


if __name__ == "__main__":
    unittest.main()
