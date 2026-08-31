from __future__ import annotations

from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata


class RecoveryDeadLetterCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/dead-letter",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="50785bb1fc1013274a36e629e1a0a8a60971e95b1c525b22e090478e16c0f71c",
        ),
        CommandMetadata(
            name="/move-to-dead-letter",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="b7db26b420ffcb4fbd138f89d3f8d3b87410f2bdbeacac02a4eb243ca79a9499",
        ),
        CommandMetadata(
            name="/restore-dead-letter",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="5649f142e16dd8ff5e4667eb6ad1fbd88865bc4a2e88e12f306650419e94f762",
        ),
        CommandMetadata(
            name="/review-dead-letter",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="5065c15aab8cae7b55ce11b1b0fa89891d9f4738ed696d0e97694c86c4a91ab8",
        ),
        CommandMetadata(
            name="/close-dead-letter",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a38a9cc1ade505059c0213a9fc96bcb2b565ce5633ac7ebd95150ce4f5a3bdb3",
        ),
        CommandMetadata(
            name="/recovery",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="dd4521083aaae9531e028c3074e5916a1e60391fabf7443005c6fb97fd02bda1",
        ),
        CommandMetadata(
            name="/recovery-summary",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="2accc485d6251dfd1cbd1e8bd47b806a5fc477fd7cb24b6386d8e5b8083408ec",
        ),
        CommandMetadata(
            name="/recovery-open",
            aliases=(),
            domain="recovery_dead_letter",
            handler="RecoveryDeadLetterCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="938d8fb5fe7f296e3d3d4313090a7e99b3e12e6734beb80e9a425429a0c7cfe4",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        if command == "/dead-letter":
            return self._dead_letter(argument_text)
        if command == "/move-to-dead-letter":
            return self._move_to_dead_letter(argument_text)
        if command == "/restore-dead-letter":
            return self._restore_dead_letter(argument_text)
        if command == "/review-dead-letter":
            return self._review_dead_letter(argument_text)
        if command == "/close-dead-letter":
            return self._close_dead_letter(argument_text)
        if command == "/recovery":
            return self._recovery(argument_text)
        if command == "/recovery-summary":
            return self._recovery_summary()
        if command == "/recovery-open":
            return self._recovery_open()
        raise UnknownCommandError(command)

    def _dead_letter(self, argument_text: str) -> CommandResult:
        dlq_id = argument_text.strip()
        if dlq_id:
            entry = self.dead_letter.get_entry(dlq_id)
            return CommandResult(
                command="/dead-letter",
                status="ok",
                output=f"Dead letter {entry.dlq_id}: {entry.status}.",
                data={"entry": asdict(entry)},
            )
        entries = [asdict(entry) for entry in self.dead_letter.list_entries()]
        return CommandResult(
            command="/dead-letter",
            status="ok",
            output=f"{len(entries)} dead letter entries.",
            data={"entries": entries},
        )

    def _move_to_dead_letter(self, argument_text: str) -> CommandResult:
        parts = argument_text.split()
        if not parts:
            return CommandResult(
                command="/move-to-dead-letter",
                status="error",
                output="Usage: /move-to-dead-letter <task_id>",
            )
        entry = self.dead_letter.move_to_dead_letter(parts[0])
        return CommandResult(
            command="/move-to-dead-letter",
            status="ok",
            output=f"Moved delegation {entry.task_id} to dead letter {entry.dlq_id}.",
            data={"entry": asdict(entry)},
        )

    def _restore_dead_letter(self, argument_text: str) -> CommandResult:
        dlq_id = argument_text.strip()
        if not dlq_id:
            return CommandResult(
                command="/restore-dead-letter",
                status="error",
                output="Usage: /restore-dead-letter <dlq_id>",
            )
        entry = self.dead_letter.restore_entry(dlq_id)
        return CommandResult(
            command="/restore-dead-letter",
            status="ok",
            output=f"Restored dead letter {entry.dlq_id}.",
            data={"entry": asdict(entry)},
        )

    def _review_dead_letter(self, argument_text: str) -> CommandResult:
        dlq_id = argument_text.strip()
        if not dlq_id:
            return CommandResult(
                command="/review-dead-letter",
                status="error",
                output="Usage: /review-dead-letter <dlq_id>",
            )
        entry = self.dead_letter.review_entry(dlq_id)
        return CommandResult(
            command="/review-dead-letter",
            status="ok",
            output=f"Reviewed dead letter {entry.dlq_id}.",
            data={"entry": asdict(entry)},
        )

    def _close_dead_letter(self, argument_text: str) -> CommandResult:
        dlq_id = argument_text.strip()
        if not dlq_id:
            return CommandResult(
                command="/close-dead-letter",
                status="error",
                output="Usage: /close-dead-letter <dlq_id>",
            )
        entry = self.dead_letter.close_entry(dlq_id)
        return CommandResult(
            command="/close-dead-letter",
            status="ok",
            output=f"Closed dead letter {entry.dlq_id}.",
            data={"entry": asdict(entry)},
        )

    def _recovery(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/recovery",
                status="error",
                output="Usage: /recovery <task_id>",
            )
        decision = self.delegation_recovery.explain_decision(task_id)
        return CommandResult(
            command="/recovery",
            status="ok",
            output=f"Recovery recommendation for {task_id}: {decision.recommendation}.",
            data={"decision": asdict(decision)},
        )

    def _recovery_summary(self) -> CommandResult:
        summary = self.delegation_recovery.summarize_recovery_state()
        return CommandResult(
            command="/recovery-summary",
            status="ok",
            output=f"{summary['recovery_candidates_count']} recovery candidate(s).",
            data={"summary": summary},
        )

    def _recovery_open(self) -> CommandResult:
        decisions = [
            asdict(decision) for decision in self.delegation_recovery.evaluate_all_open_tasks()
        ]
        return CommandResult(
            command="/recovery-open",
            status="ok",
            output=f"{len(decisions)} open delegation recovery decision(s).",
            data={"decisions": decisions},
        )
