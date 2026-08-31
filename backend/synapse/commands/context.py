from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from synapse.core.permissions import PermissionContext


@dataclass(frozen=True)
class CommandResult:
    command: str
    status: str
    output: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandContext:
    permission: PermissionContext
    source_agent_id: str | None = None


@dataclass(frozen=True)
class CommandInvocation:
    raw_input: str
    command_name: str
    canonical_name: str
    alias_used: str | None
    argument_text: str
    args: tuple[str, ...]
    options: dict[str, Any]
    correlation_id: str | None
    requester: str
    metadata: dict[str, Any]


class CommandMetadataLike(Protocol):
    name: str
    aliases: tuple[str, ...]
    domain: str
    handler: str
    argument_names: tuple[str, ...]
    defaults: tuple[str, ...]
    category: str
    status: str
    source_sha256: str


class CommandHandler(Protocol):
    command_names: tuple[str, ...]

    @property
    def metadata(self) -> tuple[CommandMetadataLike, ...]: ...

    def execute(
        self,
        context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult: ...
