from __future__ import annotations

from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata


def _metadata(name: str, arguments: tuple[str, ...] = ("argument_text",)) -> CommandMetadata:
    return CommandMetadata(
        name=name,
        aliases=(),
        domain="agent_kinds",
        handler="AgentKindsCommandHandler",
        argument_names=arguments,
        defaults=(),
        category="operational",
        status="active",
        source_sha256="agent-kinds-v1",
    )


class AgentKindsCommandHandler(BaseCommandHandler):
    metadata = tuple(
        _metadata(name)
        for name in (
            "/primary-agent-show",
            "/primary-agent-set",
            "/primary-agent-replace",
            "/primary-interaction-status",
            "/primary-interaction-bootstrap",
            "/primary-interaction-pause",
            "/primary-interaction-resume",
            "/ephemeral-agent-list",
            "/ephemeral-agent-show",
            "/ephemeral-agent-result",
            "/ephemeral-agent-reconcile",
            "/ephemeral-agent-cleanup-dry-run",
        )
    )

    def execute(
        self, command_context: CommandContext, invocation: CommandInvocation
    ) -> CommandResult:
        command = invocation.command_name
        argument = invocation.argument_text.strip()
        context = command_context.permission
        if command == "/primary-agent-show":
            data = asdict(self.primary_agent.get_state(argument or "default"))
        elif command in {"/primary-agent-set", "/primary-agent-replace"}:
            parts = argument.split()
            if not parts:
                return self._usage(command, f"{command} <agent_id> [workspace_id]")
            workspace = parts[1] if len(parts) > 1 else "default"
            operation = (
                self.primary_agent.replace_primary
                if command.endswith("replace")
                else self.primary_agent.set_primary
            )
            data = asdict(operation(context, parts[0], workspace))
        elif command == "/primary-interaction-status":
            data = asdict(self.primary_agent.get_state(argument or "default"))
        elif command == "/primary-interaction-bootstrap":
            data = asdict(
                self.primary_agent.get_primary_interaction_bootstrap(argument or "default")
            )
        elif command in {"/primary-interaction-pause", "/primary-interaction-resume"}:
            operation = (
                self.primary_agent.pause_interaction
                if command.endswith("pause")
                else self.primary_agent.resume_interaction
            )
            data = asdict(operation(context, argument or "default"))
        elif command == "/ephemeral-agent-list":
            data = {
                "agents": [asdict(item) for item in self.ephemeral_agents.list(argument or None)]
            }
        elif command == "/ephemeral-agent-show":
            if not argument:
                return self._usage(command, f"{command} <ephemeral_agent_id>")
            data = asdict(self.ephemeral_agents.get(argument))
        elif command == "/ephemeral-agent-result":
            if not argument:
                return self._usage(command, f"{command} <ephemeral_agent_id>")
            data = asdict(self.ephemeral_agents.get_result(argument))
        elif command == "/ephemeral-agent-reconcile":
            data = {"agents": [asdict(item) for item in self.ephemeral_agents.reconcile()]}
        elif command == "/ephemeral-agent-cleanup-dry-run":
            data = asdict(self.ephemeral_agents.cleanup(dry_run=True))
        else:
            raise UnknownCommandError(command)
        return CommandResult(
            command=command, status="ok", output=f"{command} completed.", data=data
        )

    @staticmethod
    def _usage(command: str, usage: str) -> CommandResult:
        return CommandResult(command=command, status="error", output=f"Usage: {usage}")
