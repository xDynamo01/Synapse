from __future__ import annotations

from time import perf_counter
from typing import Any, Callable, TypeVar

from synapse.core.events import EventBus

T = TypeVar("T")


class CollectionRuntime:
    def __init__(self, provider: Any, events: EventBus):
        self.provider = provider
        self.events = events

    def _collect(self, component: str, operation: Callable[[], T]) -> T:
        started = perf_counter()
        try:
            result = operation()
        except Exception as exc:
            self.events.emit(
                "insight.collection_failed",
                "system_insight",
                {
                    "component": component,
                    "provider": self.provider.name,
                    "latency_ms": round((perf_counter() - started) * 1000, 3),
                    "error_type": type(exc).__name__,
                },
            )
            raise
        self.events.emit(
            "insight.collection_completed",
            "system_insight",
            {
                "component": component,
                "provider": self.provider.name,
                "latency_ms": round((perf_counter() - started) * 1000, 3),
            },
        )
        return result
