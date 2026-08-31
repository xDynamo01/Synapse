from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from synapse.commands.context import CommandHandler, CommandMetadataLike
from synapse.commands.errors import DuplicateCommandError


@dataclass(frozen=True)
class CommandMetadata:
    name: str
    aliases: tuple[str, ...]
    domain: str
    handler: str
    argument_names: tuple[str, ...]
    defaults: tuple[str, ...]
    category: str
    status: str
    source_sha256: str


@dataclass(frozen=True)
class RegisteredCommand:
    metadata: CommandMetadataLike
    handler: CommandHandler


class CommandRegistry:
    """Canonical, side-effect-free registry for names, aliases and metadata."""

    def __init__(self) -> None:
        self._commands: dict[str, RegisteredCommand] = {}
        self._canonical: dict[str, RegisteredCommand] = {}

    def register(self, handler: CommandHandler) -> None:
        metadata_items = tuple(handler.metadata)
        if not metadata_items:
            raise ValueError(f"Handler {type(handler).__name__} has no command metadata")
        for metadata in metadata_items:
            registration = RegisteredCommand(metadata=metadata, handler=handler)
            names = (metadata.name, *metadata.aliases)
            duplicates = [name for name in names if name in self._commands]
            if duplicates:
                raise DuplicateCommandError(
                    f"Command name or alias already registered: {duplicates[0]}"
                )
            if len(set(names)) != len(names):
                raise DuplicateCommandError(
                    f"Command metadata repeats a name or alias: {metadata.name}"
                )
            self._canonical[metadata.name] = registration
            for name in names:
                self._commands[name] = registration

    def register_all(self, handlers: Iterable[CommandHandler]) -> None:
        for handler in handlers:
            self.register(handler)

    def resolve(self, name: str) -> RegisteredCommand | None:
        return self._commands.get(name)

    def list_commands(self) -> tuple[CommandMetadataLike, ...]:
        return tuple(item.metadata for item in self._canonical.values())

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._commands)
