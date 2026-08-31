from __future__ import annotations

import json
import socket
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ToolExecutionError
from synapse.core.serialization import load_structured_file
from synapse.model_providers.models import (
    LMStudioChatRequest,
    LMStudioChatResult,
    LMStudioConfig,
    LMStudioHealth,
    LMStudioModel,
)
from synapse.models.adapters import (
    OpenAICompatibleAdapter,
    build_chat_messages,
    estimate_chat_message_characters,
    estimate_chat_tokens,
    reduce_chat_messages,
)
from synapse.models.types import ModelRequest, ModelResponse
from synapse.models.errors import ModelError


class LMStudioProviderRuntime:
    def __init__(self, data_dir: DataDir, event_bus: EventBus):
        self.data_dir = data_dir
        self.event_bus = event_bus

    def load_config(self) -> LMStudioConfig:
        path = self.data_dir.resolve("config/lmstudio_provider.yaml")
        raw = load_structured_file(path) if path.exists() else {}
        payload = raw.get("lmstudio", raw)
        config = LMStudioConfig(
            base_url=payload.get("base_url", "http://127.0.0.1:1234/v1"),
            enabled=bool(payload.get("enabled", False)),
            timeout_seconds=int(payload.get("timeout_seconds", 30)),
            default_model=payload.get("default_model"),
            max_context_chars=int(payload.get("max_context_chars", 18_000)),
            metadata=payload.get("metadata"),
        )
        self.event_bus.emit(
            "lmstudio.provider_config_loaded",
            "lmstudio_local",
            {
                "enabled": config.enabled,
                "base_url": config.base_url,
                "default_model": config.default_model,
                "timeout_seconds": config.timeout_seconds,
                "max_context_chars": config.max_context_chars,
                "config_path": str(path),
            },
        )
        return config

    def health(self) -> LMStudioHealth:
        config = self.load_config()
        if not config.enabled:
            return LMStudioHealth(
                available=False,
                base_url=config.base_url,
                checked_at=_now(),
                model_count=0,
                message="LM Studio provider is disabled in config/lmstudio_provider.yaml (lmstudio.enabled=false).",
                metadata={"enabled": False},
            )
        try:
            raw = self._http_get_json(
                config.base_url.rstrip("/") + "/models", config.timeout_seconds
            )
            models = self._models_from_response(raw)
        except Exception as exc:
            return LMStudioHealth(
                available=False,
                base_url=config.base_url,
                checked_at=_now(),
                model_count=0,
                message=f"LM Studio unavailable: {exc}",
                metadata={"enabled": True},
            )
        return LMStudioHealth(
            available=True,
            base_url=config.base_url,
            checked_at=_now(),
            model_count=len(models),
            message="LM Studio is available.",
            metadata={"enabled": True},
        )

    def list_models(self) -> list[LMStudioModel]:
        config = self.load_config()
        if not config.enabled:
            return []
        try:
            raw = self._http_get_json(
                config.base_url.rstrip("/") + "/models", config.timeout_seconds
            )
        except Exception:
            return []
        return self._models_from_response(raw)

    def _models_from_response(self, raw: dict[str, Any]) -> list[LMStudioModel]:
        models = []
        for item in raw.get("data", []):
            model_id = item.get("id")
            if not isinstance(model_id, str):
                continue
            models.append(
                LMStudioModel(
                    model_id=model_id,
                    owned_by=item.get("owned_by"),
                    metadata={
                        key: value for key, value in item.items() if key not in {"id", "owned_by"}
                    },
                )
            )
        return models

    def chat_completion(self, chat_request: LMStudioChatRequest) -> LMStudioChatResult:
        config = self.load_config()
        if not config.enabled:
            raise ToolExecutionError("LM Studio provider is disabled in config.")
        model = chat_request.model or config.default_model
        if not model:
            raise ToolExecutionError("LM Studio model is not configured.")
        timeout_seconds = chat_request.timeout_seconds or config.timeout_seconds
        payload: dict[str, Any] = {
            "model": model,
            "messages": chat_request.messages,
        }
        if chat_request.temperature is not None:
            payload["temperature"] = chat_request.temperature
        if chat_request.max_tokens is not None:
            payload["max_tokens"] = chat_request.max_tokens
        input_char_limit = _input_context_limit(config.max_context_chars)
        budgeted_messages = reduce_chat_messages(
            chat_request.messages,
            total_char_limit=input_char_limit,
            user_char_limit=max(800, input_char_limit // 2),
        )
        request_profile = _profile_messages(budgeted_messages)
        original_profile = _profile_messages(chat_request.messages)
        if request_profile["character_count"] > input_char_limit:
            raise ToolExecutionError(
                "O contexto está grande demais para este modelo/provider."
            )
        self.event_bus.emit(
            "lmstudio.chat_request_profiled",
            "lmstudio_local",
            {
                "endpoint": config.base_url.rstrip("/") + "/chat/completions",
                "model": model,
                "provider": "lmstudio",
                "payload_fields": sorted(payload.keys()),
                "roles": [str(message.get("role", "")) for message in budgeted_messages],
                "has_tools": False,
                "has_response_format": False,
                "has_stop": False,
                "has_temperature": chat_request.temperature is not None,
                "has_max_tokens": chat_request.max_tokens is not None,
                "timeout_seconds": timeout_seconds,
                "context_capacity_chars": config.max_context_chars,
                "input_char_limit": input_char_limit,
                "original": original_profile,
                **request_profile,
            },
        )

        started = time.perf_counter()
        try:
            raw = self._http_post_json(
                config.base_url.rstrip("/") + "/chat/completions",
                {**payload, "messages": budgeted_messages},
                timeout_seconds,
            )
        except Exception as exc:
            if _is_timeout_error(exc):
                reduced_messages = reduce_chat_messages(
                    budgeted_messages,
                    total_char_limit=max(800, input_char_limit // 2),
                    user_char_limit=max(400, input_char_limit // 4),
                )
                reduced_profile = _profile_messages(reduced_messages)
                self.event_bus.emit(
                    "lmstudio.chat_request_reduced",
                    "lmstudio_local",
                    {
                        "model": model,
                        "provider": "lmstudio",
                        "timeout_seconds": timeout_seconds,
                        "original": request_profile,
                        "reduced": reduced_profile,
                    },
                )
                try:
                    raw = self._http_post_json(
                        config.base_url.rstrip("/") + "/chat/completions",
                        {**payload, "messages": reduced_messages},
                        timeout_seconds,
                    )
                except Exception as retry_exc:
                    if _is_timeout_error(retry_exc):
                        raise ToolExecutionError(
                            "LM Studio generation timed out after governed context reduction."
                        ) from retry_exc
                    raise ToolExecutionError(
                        f"LM Studio chat request failed: {retry_exc}"
                    ) from retry_exc
            else:
                fallback_model = self._fallback_model_for_unloaded_error(model, config, exc)
                if fallback_model:
                    fallback_payload = {**payload, "model": fallback_model}
                    self.event_bus.emit(
                        "lmstudio.model_unloaded_fallback",
                        "lmstudio_local",
                        {
                            "requested_model": model,
                            "fallback_model": fallback_model,
                            "provider": "lmstudio",
                        },
                    )
                    try:
                        raw = self._http_post_json(
                            config.base_url.rstrip("/") + "/chat/completions",
                            {**fallback_payload, "messages": budgeted_messages},
                            timeout_seconds,
                        )
                        model = fallback_model
                    except Exception as fallback_exc:
                        raise ToolExecutionError(
                            f"LM Studio chat request failed: {fallback_exc}"
                        ) from fallback_exc
                else:
                    raise ToolExecutionError(f"LM Studio chat request failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            choice = raw["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ToolExecutionError(
                "LM Studio response did not include choices[0].message.content."
            ) from exc
        if not isinstance(content, str):
            raise ToolExecutionError("LM Studio response content is not text.")
        if not content.strip():
            raise ToolExecutionError("empty_model_response: LM Studio returned empty content.")
        result = LMStudioChatResult(
            model=str(raw.get("model") or model),
            content=content,
            finish_reason=choice.get("finish_reason"),
            latency_ms=latency_ms,
            raw_metadata={"id": raw.get("id"), "usage": raw.get("usage")},
        )
        self.event_bus.emit(
            "lmstudio.chat_completed",
            "lmstudio_local",
            {
                "model": result.model,
                "finish_reason": result.finish_reason,
                "latency_ms": result.latency_ms,
                "request": request_profile,
            },
        )
        return result

    def explain_status(self) -> dict[str, Any]:
        config = self.load_config()
        health = self.health()
        return {"config": asdict(config), "health": asdict(health)}

    def _fallback_model_for_unloaded_error(
        self,
        requested_model: str,
        config: LMStudioConfig,
        exc: Exception,
    ) -> str | None:
        default_model = (config.default_model or "").strip()
        if not default_model or default_model == requested_model:
            return None
        if "Model is unloaded" not in _exception_text(exc):
            return None
        available = {model.model_id for model in self.list_models()}
        if default_model not in available:
            return None
        return default_model

    def _http_get_json(self, url: str, timeout_seconds: int) -> dict[str, Any]:
        http_request = request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _http_post_json(
        self, url: str, payload: dict[str, Any], timeout_seconds: int
    ) -> dict[str, Any]:
        http_request = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = _safe_http_error_body(exc)
            self.event_bus.emit(
                "lmstudio.http_request_failed",
                "lmstudio_local",
                {
                    "endpoint": url,
                    "provider_id": "lmstudio",
                    "model": payload.get("model"),
                    "payload_fields": sorted(str(key) for key in payload.keys()),
                    "message_count": len(payload.get("messages", []))
                    if isinstance(payload.get("messages"), list)
                    else 0,
                    "roles": [
                        str(message.get("role", ""))
                        for message in payload.get("messages", [])
                        if isinstance(message, dict)
                    ],
                    "has_tools": "tools" in payload,
                    "has_response_format": "response_format" in payload,
                    "has_stop": "stop" in payload,
                    "has_temperature": "temperature" in payload,
                    "has_max_tokens": "max_tokens" in payload,
                    "http_status": exc.code,
                    "response_body": body,
                },
            )
            raise ToolExecutionError(
                f"HTTP Error {exc.code}: {exc.reason}"
                + (f": {body}" if body else "")
            ) from exc


def _profile_messages(messages: list[dict[str, Any]]) -> dict[str, int]:
    normalized = [
        {"role": str(message.get("role", "")), "content": str(message.get("content", ""))}
        for message in messages
    ]
    characters = estimate_chat_message_characters(normalized)
    tokens = estimate_chat_tokens(normalized)
    return {
        "character_count": characters,
        "estimated_tokens": tokens,
        "message_count": len(normalized),
    }


def _input_context_limit(max_context_chars: int) -> int:
    capacity = max(1_200, int(max_context_chars))
    reserved_output = max(512, capacity // 4)
    return max(600, capacity - reserved_output)


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, URLError):
        reason = exc.reason
        return (
            isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower()
        )
    return "timed out" in str(exc).lower()


def _exception_text(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        body = _safe_http_error_body(exc)
        return f"{exc} {body}"
    return str(exc)


def _safe_http_error_body(exc: HTTPError) -> str:
    try:
        raw = exc.read(4096)
    except Exception:
        return ""
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = str(raw)
    return text.replace("\r", " ").replace("\n", " ").strip()[:1000]


class LMStudioModelAdapter:
    provider = "lmstudio"

    def __init__(self, runtime: LMStudioProviderRuntime):
        self.runtime = runtime

    def generate(self, request_payload: ModelRequest) -> ModelResponse:
        result = self.runtime.chat_completion(
            LMStudioChatRequest(
                model=request_payload.model,
                messages=build_chat_messages(request_payload),
            )
        )
        return ModelResponse(
            content=result.content,
            provider=self.provider,
            model=result.model,
            metadata={
                "raw_provider": "lmstudio_local",
                "finish_reason": result.finish_reason,
                "latency_ms": result.latency_ms,
            },
            finish_reason=result.finish_reason,
            latency_ms=result.latency_ms,
        )

    def list_models(self, request_payload: ModelRequest) -> list[str]:
        return [item.model_id for item in self.runtime.list_models()]

    def stream(self, request_payload: ModelRequest):
        config = self.runtime.load_config()
        delegated_request = ModelRequest(
            **{
                **request_payload.__dict__,
                "provider": "openai_compatible",
                "base_url": config.base_url,
                "timeout_seconds": float(config.timeout_seconds),
                "stream": True,
            }
        )
        request_profile = _profile_openai_compatible_request(
            delegated_request,
            config.base_url.rstrip("/") + "/chat/completions",
        )
        self.runtime.event_bus.emit(
            "lmstudio.stream_request_profiled",
            "lmstudio_local",
            request_profile,
        )
        try:
            return OpenAICompatibleAdapter().stream(delegated_request)
        except ModelError as exc:
            self.runtime.event_bus.emit(
                "lmstudio.stream_request_failed",
                "lmstudio_local",
                {
                    **request_profile,
                    "error_code": exc.code,
                    "error_message": str(exc),
                    "http_status": exc.details.get("http_status"),
                    "response_body": exc.details.get("response_body"),
                },
            )
            raise

    def cancel(self, generation_id: str) -> None:
        from synapse.models.errors import ModelError

        raise ModelError(
            "streaming_not_supported",
            "LM Studio exposes no standard cancellation endpoint",
            status_code=422,
        )

    @staticmethod
    def capabilities() -> set[str]:
        return {"text_generation", "streaming", "tool_calling", "structured_output"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _profile_openai_compatible_request(
    request_payload: ModelRequest,
    endpoint: str,
) -> dict[str, Any]:
    messages = build_chat_messages(request_payload)
    payload_fields = ["model", "messages", "stream"]
    if request_payload.temperature is not None:
        payload_fields.append("temperature")
    if request_payload.max_tokens is not None:
        payload_fields.append("max_tokens")
    if request_payload.stop_sequences:
        payload_fields.append("stop")
    if request_payload.tools:
        payload_fields.append("tools")
    if request_payload.response_format:
        payload_fields.append("response_format")
    return {
        "endpoint": endpoint,
        "provider_id": "lmstudio",
        "delegated_provider_id": request_payload.provider,
        "model": request_payload.model,
        "payload_fields": sorted(payload_fields),
        "message_count": len(messages),
        "roles": [str(message.get("role", "")) for message in messages],
        "has_tools": bool(request_payload.tools),
        "tool_count": len(request_payload.tools),
        "has_response_format": bool(request_payload.response_format),
        "has_stop": bool(request_payload.stop_sequences),
        "has_temperature": request_payload.temperature is not None,
        "has_max_tokens": request_payload.max_tokens is not None,
        "stream": True,
        "timeout_seconds": request_payload.timeout_seconds,
        "character_count": estimate_chat_message_characters(messages),
        "estimated_tokens": estimate_chat_tokens(messages),
    }
