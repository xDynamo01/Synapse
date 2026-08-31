from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from synapse.tools.calls import ToolCallRequest


@dataclass(frozen=True)
class ModelRequest:
    agent_id: str
    provider: str
    model: str | None
    user_message: str
    context: dict[str, Any]
    tools: list[dict[str, Any]] = field(default_factory=list)
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] = field(default_factory=list)
    response_format: dict[str, Any] | None = None
    stream: bool = False
    correlation_id: str | None = None
    timeout_seconds: float = 60.0
    api_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    content: str
    provider: str
    model: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str | None = None
    usage: "ModelUsage" = field(default_factory=lambda: ModelUsage())
    latency_ms: int | None = None
    warnings: list[str] = field(default_factory=list)


MODEL_CAPABILITIES = {
    "text_generation",
    "streaming",
    "tool_calling",
    "structured_output",
    "embeddings",
    "vision",
    "audio_input",
    "long_context",
}


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    time_to_first_token_ms: int | None = None
    tokens_per_second: float | None = None
    context_window_used: int | None = None
    estimated: bool = False


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    provider_id: str
    display_name: str
    family: str = "unknown"
    architecture: str | None = None
    capabilities: list[str] = field(default_factory=lambda: ["text_generation"])
    context_window: int | None = None
    max_output_tokens: int | None = None
    quantization: str | None = None
    parameter_count: int | None = None
    size_bytes: int | None = None
    local_path: str | None = None
    status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.provider_id}:{self.id}"


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    name: str
    type: str
    endpoint: str | None
    enabled: bool
    available: bool
    capabilities: list[str] = field(default_factory=list)
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_embeddings: bool = False
    supports_multimodal: bool = False
    health: str = "unconfigured"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelSelection:
    provider_id: str
    model_id: str
    source: str
    agent_id: str | None = None
    conversation_id: str | None = None
    override: bool = False
    reason: str = "configured"
    fallback_applied: bool = False
    warnings: list[str] = field(default_factory=list)
    resolved_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class GenerationChunk:
    generation_id: str
    event: str
    content: str = ""
    tool_call_delta: dict[str, Any] | None = None
    usage: ModelUsage | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
