from __future__ import annotations

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.parsing import parse_command_line
from synapse.commands.registry import CommandRegistry
from synapse.commands.services import CommandServices
from synapse.core.permissions import PermissionContext


class CommandRuntime:
    """Compatibility facade over the canonical command registry."""

    def __init__(self, registry: CommandRegistry, services: CommandServices) -> None:
        self.registry = registry
        self._services = services

    def execute(
        self,
        context: PermissionContext,
        text: str,
        source_agent_id: str | None = None,
    ) -> CommandResult:
        command_line, command, argument_text = parse_command_line(text)
        if not command_line.startswith("/"):
            return CommandResult(
                command="message",
                status="error",
                output="Command Runtime only handles slash commands.",
            )

        registration = self.registry.resolve(command)
        if registration is None:
            return CommandResult(
                command=command,
                status="error",
                output=f"Unknown command: {command}",
            )

        metadata = registration.metadata
        invocation = CommandInvocation(
            raw_input=text,
            command_name=command,
            canonical_name=metadata.name,
            alias_used=command if command != metadata.name else None,
            argument_text=argument_text,
            args=(argument_text,) if argument_text else (),
            options={},
            correlation_id=None,
            requester=context.actor_id,
            metadata={"domain": metadata.domain, "handler": metadata.handler},
        )
        return registration.handler.execute(
            CommandContext(permission=context, source_agent_id=source_agent_id),
            invocation,
        )

    @property
    def chat(self):
        return self._services.chat

    @chat.setter
    def chat(self, value) -> None:
        self._services.replace("chat", value)

    @property
    def world_state(self):
        return self._services.world_state

    @world_state.setter
    def world_state(self, value) -> None:
        self._services.replace("world_state", value)

    @property
    def attention(self):
        return self._services.attention

    @attention.setter
    def attention(self, value) -> None:
        self._services.replace("attention", value)

    @property
    def agent_loop(self):
        return self._services.agent_loop

    @agent_loop.setter
    def agent_loop(self, value) -> None:
        self._services.replace("agent_loop", value)

    @property
    def desktop(self):
        return self._services.desktop

    @desktop.setter
    def desktop(self, value) -> None:
        self._services.replace("desktop", value)


__all__ = ["CommandResult", "CommandRuntime"]
