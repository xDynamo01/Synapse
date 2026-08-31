from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.agents.models import AgentConfig
from synapse.core.model_router import ModelRouter
from synapse.models.adapters import OllamaModelAdapter, OpenAICompatibleAdapter
from synapse.models.errors import ModelError
from synapse.models.types import ModelRequest


class FakeResponse:
    def __init__(self, payload=None, lines=None, status=200):
        self.payload = payload
        self.lines = lines or []
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

    def __iter__(self):
        return iter([line.encode() for line in self.lines])


def model_request(provider="openai_compatible", model="test", **overrides):
    values = {
        "agent_id": "agent",
        "provider": provider,
        "model": model,
        "base_url": "http://local/v1" if provider == "openai_compatible" else "http://local",
        "user_message": "hello",
        "context": {},
    }
    values.update(overrides)
    return ModelRequest(**values)


class ModelProviderContractTests(unittest.TestCase):
    def test_openai_compatible_generate_usage_and_auth(self):
        response = {"id": "g1", "model": "test", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}
        with patch("synapse.models.adapters.request.urlopen", return_value=FakeResponse(response)) as urlopen:
            result = OpenAICompatibleAdapter().generate(model_request(api_key="secret"))
        self.assertEqual(result.content, "ok")
        self.assertEqual(result.usage.total_tokens, 3)
        self.assertEqual(urlopen.call_args.args[0].headers["Authorization"], "Bearer secret")

    def test_openai_compatible_tool_call_and_structured_payload(self):
        response = {"choices": [{"message": {"content": None, "tool_calls": [{"function": {"name": "lookup", "arguments": "{\"q\": \"x\"}"}}]}, "finish_reason": "tool_calls"}]}
        with patch("synapse.models.adapters.request.urlopen", return_value=FakeResponse(response)):
            result = OpenAICompatibleAdapter().generate(model_request(tools=[{"name": "lookup"}], response_format={"type": "json_object"}))
        self.assertEqual(result.tool_calls[0].name, "lookup")

    def test_openai_compatible_stream_sse(self):
        lines = ['data: {"id":"g1","choices":[{"delta":{"content":"hi"},"finish_reason":null}]}\n', 'data: [DONE]\n']
        with patch("synapse.models.adapters.request.urlopen", return_value=FakeResponse(lines=lines)):
            chunks = OpenAICompatibleAdapter().stream(model_request(stream=True))
        self.assertEqual(chunks[0].content, "hi")

    def test_openai_compatible_invalid_and_empty_response(self):
        with patch("synapse.models.adapters.request.urlopen", return_value=FakeResponse({"choices": []})):
            with self.assertRaisesRegex(ModelError, "malformed"):
                OpenAICompatibleAdapter().generate(model_request())
        with patch("synapse.models.adapters.request.urlopen", return_value=FakeResponse({"choices": [{"message": {"content": ""}}]})):
            with self.assertRaisesRegex(ModelError, "no content"):
                OpenAICompatibleAdapter().generate(model_request())

    def test_ollama_list_generate_usage_and_stream(self):
        adapter = OllamaModelAdapter()
        responses = [FakeResponse({"models": [{"name": "qwen"}]}), FakeResponse({"message": {"content": "ok"}, "prompt_eval_count": 2, "eval_count": 3}), FakeResponse(lines=['{"message":{"content":"a"},"done":false}\n'])]
        with patch("synapse.models.adapters.request.urlopen", side_effect=responses):
            self.assertEqual(adapter.list_models(model_request("ollama", "qwen")), ["qwen"])
            result = adapter.generate(model_request("ollama", "qwen"))
            chunks = adapter.stream(model_request("ollama", "qwen", stream=True))
        self.assertEqual(result.usage.total_tokens, 5)
        self.assertEqual(chunks[0].content, "a")

    def test_router_has_no_silent_mock_fallback(self):
        router = ModelRouter({"system": {"mode": "dev"}, "models": {"default_provider": "missing", "providers": {"missing": {"model": "x"}}}})
        agent = AgentConfig(id="a", name="A", role="worker")
        with self.assertRaisesRegex(ModelError, "No model adapter"):
            router.generate(agent, "hello", {}, [])

    def test_router_explicit_fallback_is_reported(self):
        router = ModelRouter({"models": {"default_provider": "missing", "providers": {"missing": {"model": "x"}}, "fallback": {"enabled": True, "provider": "mock", "model": "test"}}})
        selection = router.resolve_selection(AgentConfig(id="a", name="A", role="worker"))
        self.assertTrue(selection.fallback_applied)
        self.assertEqual(selection.source, "policy_fallback")

    def test_router_preserves_agent_preferred_model_over_resource_recommendation(self):
        class Recommender:
            def recommend_route(self, *_args):
                return type(
                    "Recommendation",
                    (),
                    {
                        "provider_id": "mock",
                        "model_id": "recommended",
                        "reason": "resource recommendation",
                    },
                )()

        router = ModelRouter(
            {"models": {"default_provider": "mock", "providers": {"mock": {"model": "default"}}}}
        )
        router.model_capabilities = Recommender()

        selection = router.resolve_selection(
            AgentConfig(id="a", name="A", role="worker", preferred_model="mock/explicit")
        )

        self.assertEqual(selection.model_id, "explicit")
        self.assertEqual(selection.source, "agent")


if __name__ == "__main__":
    unittest.main()
