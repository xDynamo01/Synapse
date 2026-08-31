from __future__ import annotations

from typing import Any

from synapse.commands.services import CommandServices


class BaseCommandHandler:
    metadata: tuple[Any, ...] = ()

    def __init__(self, services: CommandServices) -> None:
        self.services = services

    def __getattr__(self, name: str) -> Any:
        try:
            return getattr(self.services, name)
        except AttributeError:
            return self.services.resolve_operation(name)

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(name for item in self.metadata for name in (item.name, *item.aliases))

    @property
    def operation_names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, value in vars(type(self)).items()
            if name.startswith("_") and not name.startswith("__") and callable(value)
        )
