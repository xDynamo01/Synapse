from __future__ import annotations

import shlex
from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.permissions import PermissionContext


class WorldStateCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/world-state",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f5167d27444e60b5d504cbd1ca6622090ea7e73fdce5b538a66eca129b8b9ff3",
        ),
        CommandMetadata(
            name="/world-state-entity",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a3863b425467a04bc1871cc21c9de05abe70661063f0b340ef25cc20d816bc74",
        ),
        CommandMetadata(
            name="/world-state-reconcile",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("context",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a91f306e8fa8ad6aac1132d42b9671d2900bbd7c00a181a731dad3c3ba156f87",
        ),
        CommandMetadata(
            name="/attention-list",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="94f948f95ec9e84405474710a45f0a090c37e666cfa923a1b92e3df259d635f1",
        ),
        CommandMetadata(
            name="/attention-show",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="2aa67220fe067713ab0a04cf3e08d9049f4207706ed36f9d434e98054fcdff2d",
        ),
        CommandMetadata(
            name="/attention-acknowledge",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="204991f3aea204947a3de10114d40d47edd50d5e2d53d531469e89b718a34563",
        ),
        CommandMetadata(
            name="/attention-defer",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="10a69c40afbd5373211f87e06a5d887772e9ddb7020f49852983957f1f663fca",
        ),
        CommandMetadata(
            name="/agent-loop-status",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="7997b718bcccb70b0b4b80d2dbb387bd2f45e916024522082c4fe0e5a2848f00",
        ),
        CommandMetadata(
            name="/agent-loop-start",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("command", "method"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a76b41ff415e824185962eb5d26fd13157aa2eb1ea2c45a39e7614dae394e6ff",
        ),
        CommandMetadata(
            name="/agent-loop-pause",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("command", "method"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="98c3056ca84384f267e0fd473aaeef366d1e1759843f11add3ab5b255fdffff1",
        ),
        CommandMetadata(
            name="/agent-loop-resume",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("command", "method"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="798a19aad8465db242108e9dacaa81e3136cdeb24107258fc5e80128a1b91bc9",
        ),
        CommandMetadata(
            name="/agent-loop-stop",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("command", "method"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="824a38bdae4d56f28c59c0190f857ee830820e9d92e8e3e7e8fd8228879e7d9a",
        ),
        CommandMetadata(
            name="/agent-loop-run-once",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("context",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="29f6c0a30271e828981f3dfbdc3f47335b38e09cda9f462dc4c07f2296207666",
        ),
        CommandMetadata(
            name="/agent-loop-cycles",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="b1d5da580e9346900411341c9d49c96fd5af56757bb05b5bf58269511840bb2a",
        ),
        CommandMetadata(
            name="/notification-list",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="8f8cf2fca258da760fbab88e2d222b7b3eb05d123842072cc197af45a1009949",
        ),
        CommandMetadata(
            name="/notification-show",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="4e70d142f5d1abda73593c565763cb9f53b5d06363a94bfe83f094c345e50dc0",
        ),
        CommandMetadata(
            name="/notification-acknowledge",
            aliases=(),
            domain="world_state",
            handler="WorldStateCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="b453c7754b629e598e827decfb012165e5347376f9771fea659d04d5de25a859",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        context = command_context.permission
        if command == "/world-state":
            return self._world_state()
        if command == "/world-state-entity":
            return self._world_state_entity(argument_text)
        if command == "/world-state-reconcile":
            return self._world_state_reconcile(context)
        if command == "/attention-list":
            return self._attention_list(argument_text)
        if command == "/attention-show":
            return self._attention_show(argument_text)
        if command == "/attention-acknowledge":
            return self._attention_acknowledge(argument_text)
        if command == "/attention-defer":
            return self._attention_defer(argument_text)
        if command == "/agent-loop-status":
            return self._agent_loop_status()
        if command == "/agent-loop-start":
            return self._agent_loop_transition(command, "start")
        if command == "/agent-loop-pause":
            return self._agent_loop_transition(command, "pause")
        if command == "/agent-loop-resume":
            return self._agent_loop_transition(command, "resume")
        if command == "/agent-loop-stop":
            return self._agent_loop_transition(command, "stop")
        if command == "/agent-loop-run-once":
            return self._agent_loop_run_once(context)
        if command == "/agent-loop-cycles":
            return self._agent_loop_cycles(argument_text)
        if command == "/notification-list":
            return self._notification_list()
        if command == "/notification-show":
            return self._notification_show(argument_text)
        if command == "/notification-acknowledge":
            return self._notification_acknowledge(context, argument_text)
        raise UnknownCommandError(command)

    def _world_state(self) -> CommandResult:
        if not self.world_state:
            return CommandResult("/world-state", "error", "WorldStateRuntime is unavailable.")
        snapshot = asdict(self.world_state.snapshot())
        return CommandResult(
            "/world-state",
            "ok",
            f"World State revision {snapshot['revision']}.",
            {"snapshot": snapshot},
        )

    def _world_state_entity(self, argument_text: str) -> CommandResult:
        if not self.world_state:
            return CommandResult(
                "/world-state-entity", "error", "WorldStateRuntime is unavailable."
            )
        parts = shlex.split(argument_text)
        if not parts:
            return CommandResult(
                "/world-state-entity", "error", "Usage: /world-state-entity <type> [id]"
            )
        try:
            value = self.world_state.get_entity(parts[0], parts[1] if len(parts) > 1 else None)
            return CommandResult(
                "/world-state-entity", "ok", "World State entity loaded.", {"value": value}
            )
        except Exception as exc:
            return CommandResult("/world-state-entity", "error", str(exc))

    def _world_state_reconcile(self, context: PermissionContext) -> CommandResult:
        if context.actor_type not in {"admin", "system"}:
            return CommandResult(
                "/world-state-reconcile", "error", "Administrative context required."
            )
        result = asdict(self.world_state.reconcile_state())
        return CommandResult("/world-state-reconcile", "ok", "World State reconciled.", result)

    def _attention_list(self, argument_text: str) -> CommandResult:
        status = argument_text or None
        items = (
            [asdict(item) for item in self.attention.list_items(status)] if self.attention else []
        )
        return CommandResult(
            "/attention-list", "ok", f"{len(items)} attention item(s).", {"items": items}
        )

    def _attention_show(self, argument_text: str) -> CommandResult:
        if not argument_text or not self.attention:
            return CommandResult("/attention-show", "error", "Usage: /attention-show <item_id>")
        try:
            item = asdict(self.attention.get_item(argument_text))
            return CommandResult("/attention-show", "ok", "Attention item loaded.", {"item": item})
        except Exception as exc:
            return CommandResult("/attention-show", "error", str(exc))

    def _attention_acknowledge(self, argument_text: str) -> CommandResult:
        if not argument_text or not self.attention:
            return CommandResult(
                "/attention-acknowledge", "error", "Usage: /attention-acknowledge <item_id>"
            )
        item = asdict(self.attention.acknowledge(argument_text))
        return CommandResult(
            "/attention-acknowledge", "ok", "Attention acknowledged.", {"item": item}
        )

    def _attention_defer(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if not parts or not self.attention:
            return CommandResult(
                "/attention-defer", "error", "Usage: /attention-defer <item_id> [until]"
            )
        item = asdict(self.attention.defer(parts[0], parts[1] if len(parts) > 1 else None))
        return CommandResult("/attention-defer", "ok", "Attention deferred.", {"item": item})

    def _agent_loop_status(self) -> CommandResult:
        if not self.agent_loop:
            return CommandResult("/agent-loop-status", "error", "AgentLoopRuntime is unavailable.")
        return CommandResult(
            "/agent-loop-status",
            "ok",
            f"Agent Loop is {self.agent_loop.status().state}.",
            {"state": asdict(self.agent_loop.status()), "health": self.agent_loop.health()},
        )

    def _agent_loop_transition(self, command: str, method: str) -> CommandResult:
        if not self.agent_loop:
            return CommandResult(command, "error", "AgentLoopRuntime is unavailable.")
        state = getattr(self.agent_loop, method)()
        return CommandResult(
            command, "ok", f"Agent Loop is {state.state}.", {"state": asdict(state)}
        )

    def _agent_loop_run_once(self, context: PermissionContext) -> CommandResult:
        if context.actor_type not in {"admin", "system"}:
            return CommandResult(
                "/agent-loop-run-once", "error", "Administrative context required."
            )
        result = asdict(self.agent_loop.run_cycle(trigger="command.run_once"))
        return CommandResult(
            "/agent-loop-run-once", "ok", f"Agent Loop cycle {result['status']}.", {"cycle": result}
        )

    def _agent_loop_cycles(self, argument_text: str) -> CommandResult:
        limit = int(argument_text or 100)
        cycles = (
            [asdict(item) for item in self.agent_loop.list_cycles(limit)] if self.agent_loop else []
        )
        return CommandResult(
            "/agent-loop-cycles", "ok", f"{len(cycles)} cycle(s).", {"cycles": cycles}
        )

    def _notification_list(self) -> CommandResult:
        items = [asdict(item) for item in self.notifications.list_notifications()]
        return CommandResult(
            "/notification-list", "ok", f"{len(items)} notification(s).", {"notifications": items}
        )

    def _notification_show(self, argument_text: str) -> CommandResult:
        if not argument_text:
            return CommandResult("/notification-show", "error", "Usage: /notification-show <id>")
        item = asdict(self.notifications.get(argument_text))
        return CommandResult(
            "/notification-show", "ok", "Notification loaded.", {"notification": item}
        )

    def _notification_acknowledge(
        self, context: PermissionContext, argument_text: str
    ) -> CommandResult:
        if not argument_text:
            return CommandResult(
                "/notification-acknowledge", "error", "Usage: /notification-acknowledge <id>"
            )
        item = asdict(self.notifications.mark_read(argument_text, context))
        return CommandResult(
            "/notification-acknowledge", "ok", "Notification acknowledged.", {"notification": item}
        )
