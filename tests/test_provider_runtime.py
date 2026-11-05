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
from synapse.providers.models import CapabilityProvider, ProviderManifest
from synapse.providers.registry import ProviderRegistry


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
            "system": {"name": "Synapse V2 Provider Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    return directory, settings, create_runtime(settings)


def custom_manifest(provider_id: str = "local_search") -> ProviderManifest:
    return ProviderManifest(
        provider_id=provider_id,
        name="Local Search Provider",
        description="Local placeholder search provider.",
        provider_type="search",
        capabilities=["search.web"],
        version="0.1.0",
        enabled=True,
        local_only=True,
        requires_network=False,
        requires_gpu=False,
        supported_platforms=["windows"],
        metadata={"mock": True},
    )


class ProviderRuntimeTests(unittest.TestCase):
    def test_mock_is_not_selected_without_explicit_development_mode(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = Settings(
            project_root=PROJECT_ROOT,
            data_dir=Path(directory.name) / "data",
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
        runtime = create_runtime(settings)

        provider = runtime.providers.resolve_provider_for_capability("voice.stt")
        explanation = runtime.providers.explain_provider_resolution("voice.stt")

        self.assertEqual(provider.provider_id, "faster_whisper")
        mock = next(
            item
            for item in explanation["candidates"]
            if item["provider"]["provider_id"] == "mock_stt"
        )
        self.assertIn("mock_requires_explicit_development_mode", mock["reasons"])

    def test_register_provider(self) -> None:
        registry = ProviderRegistry()
        manifest = registry.register_provider(custom_manifest())

        self.assertEqual(manifest.provider_id, "local_search")
        self.assertEqual(registry.get_provider("local_search").provider_type, "search")

    def test_list_providers(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        provider_ids = {provider.provider_id for provider in runtime.providers.list_providers()}

        self.assertIn("mock_stt", provider_ids)
        self.assertIn("mock_tts", provider_ids)
        self.assertIn("piper", provider_ids)
        self.assertNotIn("mock_vision", provider_ids)
        self.assertNotIn("mock_avatar_renderer", provider_ids)

    def test_list_provider_by_type(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        stt = runtime.providers.registry.list_by_type("stt")

        self.assertEqual({provider.provider_id for provider in stt}, {"mock_stt", "faster_whisper"})

    def test_register_capability_provider(self) -> None:
        registry = ProviderRegistry()
        registry.register_provider(custom_manifest())
        registry.register_capability_provider(
            CapabilityProvider(
                capability_id="search.web",
                provider_id="local_search",
                priority=10,
                enabled=True,
            )
        )

        providers = registry.list_capability_providers("search.web")

        self.assertEqual(providers[0].provider_id, "local_search")
        self.assertEqual(providers[0].priority, 10)

    def test_resolve_provider_for_capability(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        provider = runtime.providers.resolve_provider_for_capability("voice.stt")

        self.assertEqual(provider.provider_id, "mock_stt")

    def test_resolve_tts_provider_for_capability(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        provider = runtime.providers.resolve_provider_for_capability("text_to_speech")

        self.assertEqual(provider.provider_id, "kokoro")

    def test_provider_disabled_is_not_chosen(self) -> None:
        directory, settings, _ = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_json(
            settings.data_dir / "config" / "provider_policy.yaml",
            {"providers": {"disabled_providers": ["mock_stt"]}},
        )
        runtime = create_runtime(settings)

        provider = runtime.providers.resolve_provider_for_capability("voice.stt")

        self.assertEqual(provider.provider_id, "faster_whisper")

    def test_provider_health_unconfigured(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.providers.provider_health("mock_stt")

        self.assertEqual(health.status, "unconfigured")
        self.assertIn("no real provider", health.message or "")

    def test_provider_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        providers = runtime.commands.execute(runtime.context(), "/providers")
        provider = runtime.commands.execute(runtime.context(), "/provider mock_stt")
        health = runtime.commands.execute(runtime.context(), "/provider-health")
        resolve = runtime.commands.execute(runtime.context(), "/provider-resolve voice.stt")

        self.assertEqual(providers.status, "ok")
        self.assertEqual(provider.data["provider"]["provider_id"], "mock_stt")
        self.assertEqual(health.status, "ok")
        self.assertEqual(resolve.data["selected"]["provider_id"], "mock_stt")

    def test_provider_api(self) -> None:
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

        providers = client.get("/api/providers")
        provider = client.get("/api/providers/mock_stt")
        health = client.get("/api/providers/health")
        resolve = client.get("/api/providers/resolve/voice.stt")

        self.assertEqual(providers.status_code, 200)
        self.assertEqual(provider.json()["provider_id"], "mock_stt")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(resolve.json()["selected"]["provider_id"], "mock_stt")

    def test_health_and_readiness_include_providers(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.provider_runtime_available)
        self.assertEqual(health.providers_unavailable_count, 0)
        self.assertIn("providers.ready", [check.id for check in readiness.checks])
