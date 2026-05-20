from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable


class ProviderError(RuntimeError):
    pass


@dataclass
class ChatRequest:
    messages: list[dict[str, str]]
    model: str
    max_tokens: int
    temperature: float = 0.7
    stream: bool = False


class BaseProvider(ABC):
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def chat(self, request: ChatRequest) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream(self, request: ChatRequest) -> Iterable[str]:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True
