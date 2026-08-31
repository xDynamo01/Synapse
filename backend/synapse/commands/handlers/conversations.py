from __future__ import annotations

import shlex
from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.permissions import PermissionContext


class ConversationsCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/conversations",
            aliases=(),
            domain="conversations",
            handler="ConversationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="33c81db3ab6b20b47b1e794ee320b2d4e94c7234220c7567c2a523e820d2a4c7",
        ),
        CommandMetadata(
            name="/conversation",
            aliases=(),
            domain="conversations",
            handler="ConversationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="3a578a30902207b316e2748aa6eed732afd730a8fdd6c2c843cd498a615f6ed4",
        ),
        CommandMetadata(
            name="/conversation-messages",
            aliases=(),
            domain="conversations",
            handler="ConversationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c9238b1f1c61e0ca9998a6353a8adb09467dd31010d85c64000403f5837d243c",
        ),
        CommandMetadata(
            name="/conversation-summary",
            aliases=(),
            domain="conversations",
            handler="ConversationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="c4273d62e0401a26e2e800897782cbd8e646b6fa0a30ae60cc89f4325580a1f0",
        ),
        CommandMetadata(
            name="/update-conversation-summary",
            aliases=(),
            domain="conversations",
            handler="ConversationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="b627b5539320be403867060b898d639224904d55ea3d877ec71d1fdda6bee695",
        ),
        CommandMetadata(
            name="/build-conversation-context",
            aliases=(),
            domain="conversations",
            handler="ConversationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="ec13fe26bc60b1d0ef93f52360f20ce804c029b6972ea045605cb4b17c9af911",
        ),
        CommandMetadata(
            name="/send-agent-message",
            aliases=(),
            domain="conversations",
            handler="ConversationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9cac231411ffb9b085d60ea6add7d99a98328cb10b2af0029f4e96449dcadc9a",
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
        if command == "/conversations":
            return self._conversations()
        if command == "/conversation":
            return self._conversation(argument_text)
        if command == "/conversation-messages":
            return self._conversation_messages(argument_text)
        if command == "/conversation-summary":
            return self._conversation_summary(argument_text)
        if command == "/update-conversation-summary":
            return self._update_conversation_summary(argument_text)
        if command == "/build-conversation-context":
            return self._build_conversation_context(argument_text)
        if command == "/send-agent-message":
            return self._send_agent_message(context, argument_text)
        raise UnknownCommandError(command)

    def _conversations(self) -> CommandResult:
        conversations = [asdict(item) for item in self.conversations.list_conversations()]
        return CommandResult(
            command="/conversations",
            status="ok",
            output=f"{len(conversations)} conversation(s).",
            data={"conversations": conversations},
        )

    def _conversation(self, argument_text: str) -> CommandResult:
        conversation_id = argument_text.strip()
        if not conversation_id:
            return CommandResult(
                command="/conversation",
                status="error",
                output="Usage: /conversation <conversation_id>",
            )
        conversation = self.conversations.get_conversation(conversation_id)
        return CommandResult(
            command="/conversation",
            status="ok",
            output=f"Conversation {conversation_id}: {conversation.status}.",
            data={"conversation": asdict(conversation)},
        )

    def _conversation_messages(self, argument_text: str) -> CommandResult:
        conversation_id = argument_text.strip()
        if not conversation_id:
            return CommandResult(
                command="/conversation-messages",
                status="error",
                output="Usage: /conversation-messages <conversation_id>",
            )
        messages = [
            asdict(message)
            for message in self.conversations.list_conversation_messages(conversation_id)
        ]
        return CommandResult(
            command="/conversation-messages",
            status="ok",
            output=f"{len(messages)} message(s).",
            data={"messages": messages},
        )

    def _conversation_summary(self, argument_text: str) -> CommandResult:
        conversation_id = argument_text.strip()
        if not conversation_id:
            return CommandResult(
                command="/conversation-summary",
                status="error",
                output="Usage: /conversation-summary <conversation_id>",
            )
        summary = self.conversations.get_conversation_summary(conversation_id)
        exists = bool(summary.metadata.get("exists", False))
        output = (
            "Conversation summary loaded." if exists else "Conversation summary does not exist."
        )
        return CommandResult(
            command="/conversation-summary",
            status="ok",
            output=output,
            data={"summary": asdict(summary)},
        )

    def _update_conversation_summary(self, argument_text: str) -> CommandResult:
        try:
            tokens = shlex.split(argument_text)
        except ValueError as exc:
            return CommandResult(
                command="/update-conversation-summary",
                status="error",
                output=str(exc),
            )
        if len(tokens) < 2:
            return CommandResult(
                command="/update-conversation-summary",
                status="error",
                output='Usage: /update-conversation-summary <conversation_id> "<summary>"',
            )
        conversation_id = tokens[0]
        summary_text = " ".join(tokens[1:])
        summary = self.conversations.update_conversation_summary(
            conversation_id,
            summary_text,
        )
        return CommandResult(
            command="/update-conversation-summary",
            status="ok",
            output=f"Updated summary for conversation {conversation_id}.",
            data={"summary": asdict(summary)},
        )

    def _build_conversation_context(self, argument_text: str) -> CommandResult:
        conversation_id = argument_text.strip()
        if not conversation_id:
            return CommandResult(
                command="/build-conversation-context",
                status="error",
                output="Usage: /build-conversation-context <conversation_id>",
            )
        fused = self.context_fusion.build_conversation_context(conversation_id)
        context = {
            "conversation_id": conversation_id,
            "summary": fused.snapshot.latest_conversation_summary,
            "messages": fused.snapshot.latest_messages,
            "message_count": len(fused.snapshot.latest_messages),
            "context_fusion": asdict(fused),
        }
        return CommandResult(
            command="/build-conversation-context",
            status="ok",
            output=f"Built context for conversation {conversation_id}.",
            data={"context": context},
        )

    def _send_agent_message(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        try:
            tokens = shlex.split(argument_text)
        except ValueError as exc:
            return CommandResult(command="/send-agent-message", status="error", output=str(exc))
        if len(tokens) < 3:
            return CommandResult(
                command="/send-agent-message",
                status="error",
                output='Usage: /send-agent-message <sender> <receiver> "<message>"',
            )
        sender, receiver = tokens[0].lower(), tokens[1].lower()
        body = " ".join(tokens[2:])
        message = self.worker.communication.send_agent_message(
            context=context,
            from_agent_id=sender,
            to_agent_id=receiver,
            subject="Agent message",
            body=body,
        )
        conversation_message = self.conversations.message_status(message.id)
        return CommandResult(
            command="/send-agent-message",
            status="ok",
            output=f"Sent message {message.id} to {receiver}.",
            data={
                "message": asdict(message),
                "conversation_message": asdict(conversation_message),
            },
        )
