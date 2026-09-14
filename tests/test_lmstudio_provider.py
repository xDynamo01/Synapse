from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from io import BytesIO
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ToolExecutionError
from synapse.model_providers.models import LMStudioChatRequest, LMStudioChatResult


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
            "system": {"name": "Synapse V2 LM Studio Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    return directory, settings, create_runtime(settings)


def enable_lmstudio(settings: Settings, default_model: str | None = "local-model") -> None:
    write_json(
        settings.data_dir / "config" / "lmstudio_provider.yaml",
        {
            "lmstudio": {
                "enabled": True,
                "base_url": "http://127.0.0.1:1234/v1",
                "timeout_seconds": 1,
                "default_model": default_model,
                "metadata": {},
            }
        },
    )


def disable_lmstudio(settings: Settings) -> None:
    write_json(
        settings.data_dir / "config" / "lmstudio_provider.yaml",
        {
            "lmstudio": {
                "enabled": False,
                "base_url": "http://127.0.0.1:1234/v1",
                "timeout_seconds": 1,
                "default_model": None,
                "metadata": {},
            }
        },
    )


def mock_native_chat(runtime, content: str = "ok", model: str = "local-model") -> None:
    runtime.lmstudio._native_chat_completion = lambda config, chat_request, selected_model, timeout: LMStudioChatResult(  # type: ignore[method-assign]
        model=model or selected_model,
        content=content,
        finish_reason="stop",
        latency_ms=42,
        raw_metadata={
            "stats": {
                "input_tokens": 3,
                "total_output_tokens": 5,
                "time_to_first_token_seconds": 0.12,
                "tokens_per_second": 40.0,
            }
        },
    )


class LMStudioProviderTests(unittest.TestCase):
    def test_default_config_uses_v001_lmstudio_model(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        config = runtime.lmstudio.load_config()

        self.assertTrue(config.enabled)
        self.assertEqual(config.base_url, "http://127.0.0.1:1234/v1")
        self.assertEqual(config.default_model, "gemma-4-e2b-it-qat")

    def test_health_disabled(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        disable_lmstudio(settings)

        health = runtime.lmstudio.health()

        self.assertFalse(health.available)
        self.assertEqual(health.model_count, 0)
        self.assertIn("disabled", health.message or "")

    def test_health_endpoint_unavailable(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        def fail_get(url: str, timeout_seconds: int) -> dict:
            raise OSError("connection refused")

        runtime.lmstudio._http_get_json = fail_get  # type: ignore[method-assign]

        health = runtime.lmstudio.health()

        self.assertFalse(health.available)
        self.assertEqual(health.model_count, 0)

    def test_list_models_handles_connection_error(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        def fail_get(url: str, timeout_seconds: int) -> dict:
            raise OSError("connection refused")

        runtime.lmstudio._http_get_json = fail_get  # type: ignore[method-assign]

        self.assertEqual(runtime.lmstudio.list_models(), [])

    def test_chat_completion_disabled_fails_controlled(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        disable_lmstudio(settings)

        with self.assertRaises(ToolExecutionError):
            runtime.lmstudio.chat_completion(
                LMStudioChatRequest(messages=[{"role": "user", "content": "hello"}])
            )

    def test_parse_models_response(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        runtime.lmstudio._http_get_json = lambda url, timeout: {  # type: ignore[method-assign]
            "data": [{"id": "local-model", "owned_by": "lmstudio"}]
        }

        models = runtime.lmstudio.list_models()

        self.assertEqual(models[0].model_id, "local-model")
        self.assertEqual(models[0].owned_by, "lmstudio")

    def test_parse_chat_completion_response(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        mock_native_chat(runtime, content="hello from lm studio")

        result = runtime.lmstudio.chat_completion(
            LMStudioChatRequest(messages=[{"role": "user", "content": "hello"}])
        )

        self.assertEqual(result.model, "local-model")
        self.assertEqual(result.content, "hello from lm studio")
        self.assertEqual(result.finish_reason, "stop")

    def test_chat_completion_does_not_fallback_to_openai_compatible_on_native_timeout(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        def fail_native(config, chat_request, model: str, timeout: int):
            del config, chat_request, model, timeout
            raise ToolExecutionError("LM Studio native chat request failed: timed out")

        def forbidden_post(url: str, payload: dict, timeout: int) -> dict:
            del url, payload, timeout
            raise AssertionError("OpenAI-compatible fallback must not be used")

        runtime.lmstudio._native_chat_completion = fail_native  # type: ignore[method-assign]
        runtime.lmstudio._http_post_json = forbidden_post  # type: ignore[method-assign]

        with self.assertRaisesRegex(ToolExecutionError, "native chat request failed"):
            runtime.lmstudio.chat_completion(
                LMStudioChatRequest(messages=[{"role": "user", "content": "oi"}])
            )

    def test_chat_completion_native_timeout_is_reported_explicitly(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        def fail_native(config, chat_request, model: str, timeout: int):
            del config, chat_request, model, timeout
            raise ToolExecutionError("LM Studio native chat request failed: timed out")

        runtime.lmstudio._native_chat_completion = fail_native  # type: ignore[method-assign]

        with self.assertRaisesRegex(ToolExecutionError, "native chat request failed"):
            runtime.lmstudio.chat_completion(
                LMStudioChatRequest(messages=[{"role": "user", "content": "oi"}])
            )

    def test_chat_completion_http_400_preserves_sanitized_response_body(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        def fail_urlopen(request, timeout: int):
            del request, timeout
            raise HTTPError(
                "http://127.0.0.1:1234/api/v1/chat",
                400,
                "Bad Request",
                {},
                BytesIO(b'{"error":"unsupported field: context_length"}'),
            )

        with patch("synapse.model_providers.lmstudio.request.urlopen", fail_urlopen):
            with self.assertRaisesRegex(
                ToolExecutionError,
                "unsupported field: context_length",
            ):
                runtime.lmstudio.chat_completion(
                    LMStudioChatRequest(messages=[{"role": "user", "content": "oi"}])
                )

    def test_chat_completion_does_not_fallback_to_configured_default_when_requested_model_is_unloaded(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings, default_model="loaded-default")

        runtime.lmstudio._http_get_json = lambda url, timeout: {  # type: ignore[method-assign]
            "data": [{"id": "unloaded-agent-model"}, {"id": "loaded-default"}]
        }

        def fail_native(config, chat_request, model: str, timeout: int):
            del config, chat_request, timeout
            raise ToolExecutionError(f"LM Studio native chat request failed: Model is unloaded: {model}")

        runtime.lmstudio._native_chat_completion = fail_native  # type: ignore[method-assign]

        with self.assertRaisesRegex(ToolExecutionError, "unloaded-agent-model"):
            runtime.lmstudio.chat_completion(
                LMStudioChatRequest(
                    model="unloaded-agent-model",
                    messages=[{"role": "user", "content": "oi"}],
                )
            )

    def test_chat_completion_applies_configured_input_budget_before_first_request(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        write_json(
            settings.data_dir / "config" / "lmstudio_provider.yaml",
            {
                "lmstudio": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:1234/v1",
                    "timeout_seconds": 1,
                    "default_model": "local-model",
                    "max_context_chars": 1200,
                    "metadata": {},
                }
            },
        )

        observed_input: list[str] = []

        def observe_native(config, chat_request, model: str, timeout: int) -> LMStudioChatResult:
            del config, model, timeout
            observed_input.append(str(chat_request.messages))
            return LMStudioChatResult(
                model="local-model",
                content="ok",
                finish_reason="stop",
                latency_ms=1,
                raw_metadata={},
            )

        runtime.lmstudio._native_chat_completion = observe_native  # type: ignore[method-assign]

        result = runtime.lmstudio.chat_completion(
            LMStudioChatRequest(
                messages=[
                    {"role": "system", "content": "s" * 4000},
                    {"role": "user", "content": "oi"},
                ]
            )
        )

        self.assertEqual(result.content, "ok")
        self.assertTrue(observed_input)

    def test_provider_and_plugin_manifests_registered(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        provider = runtime.providers.get_provider("lmstudio_local")
        plugin = runtime.provider_plugins.get_plugin("lmstudio_plugin")

        self.assertEqual(provider.provider_type, "model")
        self.assertIn("chat_completion", provider.capabilities)
        self.assertEqual(plugin.plugin_type, "model")
        self.assertIn("lmstudio_local", plugin.providers)

    def test_commands(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)

        runtime.lmstudio._http_get_json = lambda url, timeout: {  # type: ignore[method-assign]
            "data": [{"id": "local-model"}]
        }
        mock_native_chat(runtime, content="ok")

        status = runtime.commands.execute(runtime.context(), "/lmstudio-status")
        models = runtime.commands.execute(runtime.context(), "/lmstudio-models")
        chat = runtime.commands.execute(runtime.context(), '/lmstudio-chat "hello"')

        self.assertEqual(status.status, "ok")
        self.assertEqual(models.data["models"][0]["model_id"], "local-model")
        self.assertEqual(chat.output, "ok")

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        enable_lmstudio(settings)
        runtime.lmstudio._http_get_json = lambda url, timeout: {  # type: ignore[method-assign]
            "data": [{"id": "local-model"}]
        }
        mock_native_chat(runtime, content="api ok")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        self.assertEqual(client.get("/api/providers/lmstudio/status").status_code, 200)
        self.assertEqual(client.get("/api/providers/lmstudio/models").json()[0]["model_id"], "local-model")
        self.assertEqual(
            client.post(
                "/api/providers/lmstudio/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            ).json()["content"],
            "api ok",
        )

    def test_health_and_readiness_include_lmstudio(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.lmstudio._http_get_json = lambda url, timeout: (_ for _ in ()).throw(  # type: ignore[method-assign]
            OSError("connection refused")
        )

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertFalse(health.lmstudio_available)
        self.assertEqual(health.lmstudio_model_count, 0)
        self.assertIn("lmstudio.ready", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
