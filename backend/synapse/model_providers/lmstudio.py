from __future__ import annotations

import json
import socket
import time
from collections import deque
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
    build_chat_messages,
    estimate_chat_message_characters,
    estimate_chat_tokens,
    reduce_chat_messages,
)
from synapse.models.errors import ModelError
from synapse.models.types import ModelRequest, ModelResponse, ModelUsage


class LMStudioProviderRuntime:
    def __init__(self, data_dir: DataDir, event_bus: EventBus):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self._telemetry: deque[dict[str, Any]] = deque(maxlen=80)

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
        return self._native_chat_completion(config, chat_request, model, timeout_seconds)

    def _native_chat_completion(
        self,
        config: LMStudioConfig,
        chat_request: LMStudioChatRequest,
        model: str,
        timeout_seconds: int,
    ) -> LMStudioChatResult:
        endpoint = _native_chat_endpoint(config.base_url)
        budgeted_messages = chat_request.messages if (chat_request.metadata or {}).get("context_budget") else reduce_chat_messages(
            chat_request.messages,
            total_char_limit=_input_context_limit(config.max_context_chars),
            user_char_limit=max(800, _input_context_limit(config.max_context_chars) // 2),
        )
        payload: dict[str, Any] = {
            "model": model,
            "input": _native_input_text(budgeted_messages),
            "stream": True,
        }
        if chat_request.temperature is not None:
            payload["temperature"] = chat_request.temperature
        if chat_request.max_tokens is not None:
            payload["max_output_tokens"] = chat_request.max_tokens
        metadata = chat_request.metadata or {}
        activity_payload = _activity_payload(metadata, model)
        self._emit_native_activity(activity_payload, "prompt_processing", "Prompt processing", "Preparing model context")
        http_request = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        content_parts: list[str] = []
        raw_events: list[dict[str, Any]] = []
        stats: dict[str, Any] = {}
        response_id: str | None = None
        started = time.perf_counter()
        try:
            with request.urlopen(http_request, timeout=timeout_seconds) as response:
                for event_name, data in _iter_sse_events(response):
                    if not isinstance(data, dict):
                        continue
                    raw_events.append({"event": event_name, "type": data.get("type")})
                    event_type = str(data.get("type") or event_name)
                    if event_type in {"prompt_processing.start", "prompt_processing.progress", "prompt_processing.end"}:
                        self._emit_native_activity(activity_payload, "prompt_processing", "Prompt processing", _progress_task(data, "Preparing model context"))
                    elif event_type in {"reasoning.start", "reasoning.delta", "reasoning.end"}:
                        self._emit_native_activity(activity_payload, "reasoning", "Reasoning", "Model reasoning in progress")
                    elif event_type in {"message.start", "message.delta", "message.end"}:
                        self._emit_native_activity(activity_payload, "generating", "Generating response", "Model is producing output")
                        if event_type == "message.delta":
                            delta = data.get("content")
                            if isinstance(delta, str):
                                content_parts.append(delta)
                    elif event_type == "chat.end":
                        result = data.get("result")
                        if isinstance(result, dict):
                            response_id = _optional_str(result.get("response_id"))
                            stats_value = result.get("stats")
                            if isinstance(stats_value, dict):
                                stats = stats_value
                            if not content_parts:
                                content_parts.extend(_message_outputs(result.get("output")))
        except Exception as exc:
            raise ToolExecutionError(f"LM Studio native chat request failed: {_exception_text(exc)}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        content = "".join(content_parts)
        if not content.strip():
            raise ToolExecutionError("empty_model_response: LM Studio native API returned empty content.")
        usage = _usage_from_native_stats(stats)
        self._emit_native_activity(
            {
                **activity_payload,
                **_activity_metrics_from_usage(usage, latency_ms),
            },
            "completed",
            "Response generated",
            "Assistant response complete",
            status="completed",
        )
        return LMStudioChatResult(
            model=model,
            content=content,
            finish_reason="stop",
            latency_ms=latency_ms,
            raw_metadata={"id": response_id, "stats": stats, "usage": _openai_usage_from_usage(usage)},
        )

    def _emit_native_activity(
        self,
        payload: dict[str, Any],
        phase: str,
        current_operation: str,
        current_task: str,
        *,
        status: str = "processing",
    ) -> None:
        if not payload.get("conversation_id"):
            return
        activity = {
            **payload,
            "provider_id": "lmstudio",
            "phase": phase,
            "status": status,
            "current_operation": current_operation,
            "current_task": current_task,
        }
        self._append_telemetry(activity)
        self.event_bus.emit(f"lmstudio.native.{phase}", "lmstudio_local", activity)

    def _append_telemetry(self, payload: dict[str, Any]) -> None:
        self._telemetry.append(
            {
                "occurred_at": _now(),
                **{
                    key: value
                    for key, value in payload.items()
                    if key
                    in {
                        "provider_id",
                        "model_name",
                        "conversation_id",
                        "phase",
                        "status",
                        "current_operation",
                        "current_task",
                        "input_count",
                        "output_count",
                        "total_count",
                        "latency_ms",
                        "first_output_ms",
                        "output_rate",
                    }
                    and isinstance(value, (str, int, float, bool))
                },
            }
        )

    def recent_telemetry(self, limit: int = 24) -> list[dict[str, Any]]:
        count = max(1, min(limit, 80))
        return list(self._telemetry)[-count:]

    def explain_status(self) -> dict[str, Any]:
        config = self.load_config()
        health = self.health()
        return {"config": asdict(config), "health": asdict(health), "telemetry": {"recent": self.recent_telemetry()}}

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


def _native_chat_endpoint(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root.rstrip("/") + "/api/v1/chat"


def _native_input_text(messages: list[dict[str, Any]]) -> str:
    lines = []
    for message in messages:
        role = str(message.get("role") or "user").strip() or "user"
        content = str(message.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _iter_sse_events(response: Any):
    event_name = "message"
    data_lines: list[str] = []
    for encoded in response:
        line = encoded.decode("utf-8", errors="replace").strip()
        if not line:
            if data_lines:
                raw_data = "\n".join(data_lines)
                try:
                    parsed = json.loads(raw_data)
                except json.JSONDecodeError:
                    parsed = raw_data
                yield event_name, parsed
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())


def _activity_payload(metadata: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "model_name": model,
        "agent_id": _optional_str(metadata.get("agent_id")) or "artemis",
        "conversation_id": _optional_str(metadata.get("conversation_id")),
        "session_id": _optional_str(metadata.get("session_id")),
        "project_id": _optional_str(metadata.get("project_id")),
    }


def _progress_task(data: dict[str, Any], fallback: str) -> str:
    progress = data.get("progress")
    if isinstance(progress, (int, float)) and not isinstance(progress, bool):
        return f"Preparing model context ({round(float(progress) * 100)}%)"
    return fallback


def _message_outputs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    outputs = []
    for item in value:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if isinstance(content, str):
            outputs.append(content)
    return outputs


def _usage_from_native_stats(stats: dict[str, Any]) -> ModelUsage:
    input_count = _optional_int(stats.get("input_tokens"))
    output_count = _optional_int(stats.get("total_output_tokens"))
    return ModelUsage(
        input_tokens=input_count,
        output_tokens=output_count,
        total_tokens=(input_count + output_count) if input_count is not None and output_count is not None else None,
        time_to_first_token_ms=_seconds_to_ms(stats.get("time_to_first_token_seconds")),
        tokens_per_second=_optional_float(stats.get("tokens_per_second")),
    )


def _activity_metrics_from_usage(usage: ModelUsage, latency_ms: int) -> dict[str, Any]:
    return {
        "latency_ms": latency_ms,
        "input_count": usage.input_tokens,
        "output_count": usage.output_tokens,
        "total_count": usage.total_tokens,
        "first_output_ms": usage.time_to_first_token_ms,
        "output_rate": usage.tokens_per_second,
    }


def _openai_usage_from_usage(usage: ModelUsage) -> dict[str, int | None]:
    return {
        "prompt_tokens": usage.input_tokens,
        "completion_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


def _seconds_to_ms(value: object) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(float(value) * 1000)
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class LMStudioModelAdapter:
    provider = "lmstudio"

    def __init__(self, runtime: LMStudioProviderRuntime):
        self.runtime = runtime

    def generate(self, request_payload: ModelRequest) -> ModelResponse:
        result = self.runtime.chat_completion(
            LMStudioChatRequest(
                model=request_payload.model,
                messages=build_chat_messages(request_payload),
                temperature=request_payload.temperature,
                max_tokens=request_payload.max_tokens,
                timeout_seconds=int(request_payload.timeout_seconds),
                metadata=request_payload.metadata,
            )
        )
        usage = _usage_from_lmstudio_metadata(result.raw_metadata)
        return ModelResponse(
            content=result.content,
            provider=self.provider,
            model=result.model,
            metadata={
                "raw_provider": "lmstudio_local",
                "finish_reason": result.finish_reason,
                "latency_ms": result.latency_ms,
                "first_output_ms": usage.time_to_first_token_ms,
                "output_rate": usage.tokens_per_second,
            },
            finish_reason=result.finish_reason,
            usage=usage,
            latency_ms=result.latency_ms,
        )

    def list_models(self, request_payload: ModelRequest) -> list[str]:
        return [item.model_id for item in self.runtime.list_models()]

    def stream(self, request_payload: ModelRequest):
        del request_payload
        raise ModelError(
            "lmstudio_native_stream_not_implemented",
            "LM Studio provider is configured for native API only; streaming needs a native adapter.",
            status_code=501,
        )

    def cancel(self, generation_id: str) -> None:
        from synapse.models.errors import ModelError

        raise ModelError(
            "streaming_not_supported",
            "LM Studio exposes no standard cancellation endpoint",
            status_code=422,
        )

    @staticmethod
    def capabilities() -> set[str]:
        return {"text_generation", "tool_calling", "structured_output"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _usage_from_lmstudio_metadata(raw_metadata: dict[str, Any] | None) -> ModelUsage:
    usage = raw_metadata.get("usage") if raw_metadata else None
    stats = raw_metadata.get("stats") if raw_metadata else None
    if isinstance(stats, dict):
        return _usage_from_native_stats(stats)
    if not isinstance(usage, dict):
        return ModelUsage()
    return ModelUsage(
        input_tokens=_optional_int(usage.get("prompt_tokens")),
        output_tokens=_optional_int(usage.get("completion_tokens")),
        total_tokens=_optional_int(usage.get("total_tokens")),
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
