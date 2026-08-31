from __future__ import annotations

from typing import Any, Iterable


class CommandServices:
    """Opaque transport for already-built canonical runtimes and facades."""

    def __init__(self, **dependencies: Any) -> None:
        self._dependencies = dict(dependencies)
        self._operations: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        try:
            return self._dependencies[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def replace(self, name: str, value: Any) -> None:
        if name not in self._dependencies:
            raise AttributeError(name)
        self._dependencies[name] = value

    def default_agent_id(self) -> str | None:
        system = self.config.load_system().get("system", {})
        value = system.get("default_agent_id")
        return str(value) if value else None

    def list_memory(self, context: Any):
        return self.memory.list(context)

    def create_memory(self, context: Any, **payload: Any):
        return self.memory.create(context, **payload)

    def bind_handlers(self, handlers: Iterable[Any]) -> None:
        operations: dict[str, Any] = {}
        for handler in handlers:
            for name in handler.operation_names:
                if name in operations:
                    raise ValueError(f"Duplicate command operation: {name}")
                operations[name] = getattr(handler, name)
        self._operations = operations

    def resolve_operation(self, name: str) -> Any:
        try:
            return self._operations[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
