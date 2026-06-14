from __future__ import annotations

import json
from typing import Protocol
from urllib import request

from synapse.core.exceptions import ToolExecutionError
from synapse.models.types import ModelRequest, ModelResponse


class BaseModelAdapter(Protocol):
    provider: str

    def generate(self, request_payload: ModelRequest) -> ModelResponse:
        ...


class MockModelAdapter:
    provider = "mock"

    def __init__(self, response_prefix: str = "Mock response"):
        self.response_prefix = response_prefix

    def generate(self, request_payload: ModelRequest) -> ModelResponse:
        memory_count = len(request_payload.context.get("memory", []))
        task_count = len(request_payload.context.get("tasks", []))
        content = (
            f"{self.response_prefix} for {request_payload.agent_id}: "
            f"{request_payload.user_message} "
            f"(memory_sections={memory_count}, tasks={task_count})"
        )
        return ModelResponse(
            content=content,
            provider=self.provider,
            model=request_payload.model,
            metadata={"deterministic": True},
        )


class OllamaModelAdapter:
    provider = "ollama"

    def generate(self, request_payload: ModelRequest) -> ModelResponse:
        if not request_payload.base_url:
            raise ToolExecutionError("Ollama base_url is not configured.")
        if not request_payload.model:
            raise ToolExecutionError("Ollama model is not configured.")

        body = {
            "model": request_payload.model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an agent in Synapse. Use the provided structured context.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": request_payload.user_message,
                            "context": request_payload.context,
                            "tools": request_payload.tools,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        url = request_payload.base_url.rstrip("/") + "/api/chat"
        data = json.dumps(body).encode("utf-8")
        http_request = request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ToolExecutionError(f"Ollama request failed: {exc}") from exc

        message = raw.get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            raise ToolExecutionError("Ollama response did not include message.content.")
        return ModelResponse(
            content=content,
            provider=self.provider,
            model=request_payload.model,
            metadata={"raw_provider": "ollama"},
        )


class OpenAICompatibleAdapter:
    provider = "openai_compatible"

    def generate(self, request_payload: ModelRequest) -> ModelResponse:
        raise NotImplementedError("OpenAI-compatible adapter is prepared but not implemented yet.")

