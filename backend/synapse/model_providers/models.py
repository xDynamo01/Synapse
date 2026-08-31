from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LMStudioConfig:
    base_url: str = "http://127.0.0.1:1234/v1"
    enabled: bool = False
    timeout_seconds: int = 30
    max_context_chars: int = 18_000
    default_model: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class LMStudioHealth:
    available: bool
    base_url: str
    checked_at: str
    model_count: int
    message: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class LMStudioModel:
    model_id: str
    owned_by: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class LMStudioChatRequest:
    messages: list[dict[str, Any]]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class LMStudioChatResult:
    model: str
    content: str
    finish_reason: str | None = None
    latency_ms: int | None = None
    raw_metadata: dict[str, Any] | None = None
