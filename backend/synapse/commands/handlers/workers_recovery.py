from __future__ import annotations

import shlex
from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata


class WorkersRecoveryCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/worker-list",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="da81815a83199ba09f0310603ade63a12fa24955dcdd23d6c819fe906f656481",
        ),
        CommandMetadata(
            name="/worker-show",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="5a41c017fd2231bb7f2471f1da0bacefd17bd178f5425ab345c64375fa37930f",
        ),
        CommandMetadata(
            name="/worker-disable",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="dcf3f8ce99de9a93a06b7177d77c7432dfc0535847dd82270ec32f17e258704e",
        ),
        CommandMetadata(
            name="/worker-register",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="56a15b142f68f3b9bd26df6f23d16987ee0faca9bcf1e320ffc1b1e28a3edb2a",
        ),
        CommandMetadata(
            name="/worker-workload",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="aa5fe5e61bc129c5ee424009b4d82987049eb04278941516b183ab4ac9962d03",
        ),
        CommandMetadata(
            name="/worker-attempts",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="fd852934ab73733afee6d70ad9be670626196a0c51a722a9a809639fff71cdbb",
        ),
        CommandMetadata(
            name="/worker-stale-scan",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="18360e1ba69b564c75e554c266e9b7c35a7bc582930a1a28aa061944207a2b67",
        ),
        CommandMetadata(
            name="/worker-heartbeat",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="01e72e5ba9e11b33cf6e8c95ca98660356e615c4edf5a56174369f6a7de98753",
        ),
        CommandMetadata(
            name="/task-history",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9e608431dc816c7f262ccb46e97d1d307aab773abb46e5bf9babe3b331db8fa6",
        ),
        CommandMetadata(
            name="/task-retry",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="55c8c7659efd4ab978600ca1e6ba88849edb024dd21a3985feb37e00297ca7cd",
        ),
        CommandMetadata(
            name="/task-attempts",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6f09681a678a4fee59449da9f982db341703f545ff6fec1b61aa22536c749cf4",
        ),
        CommandMetadata(
            name="/task-assign",
            aliases=("/task-reassign",),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("command", "argument_text", "reassign"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="d4197900c37d0a25db46f63a2d84cb8bc1d4ec5949d27fe0e0d87c2999dd3b0f",
        ),
        CommandMetadata(
            name="/task-cancel",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2a4049f0a9309d1607fccfba077cbbd80a2617ca9b31cf1e165ef81169d41e0b",
        ),
        CommandMetadata(
            name="/task-verify",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2d8b5a4cf8d1abeba0c2162471bef35a10f721b71e8c5dd6e5abaeb09a7424a3",
        ),
        CommandMetadata(
            name="/recovery-show",
            aliases=("/recovery-evaluate",),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("command", "argument_text"),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="8ecca691f854f0179833e751fd385fd432d05b7c5cf79b1056d09bb32d2256ff",
        ),
        CommandMetadata(
            name="/recovery-list",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="798054e7c481b5b68454b526fa9a848441c03eb402d9970075ae335dca920aa9",
        ),
        CommandMetadata(
            name="/recovery-history",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e505a21647ed2fb49cf67fd95b8249a59b6b0a85d0f162f8baba49baa4c00d58",
        ),
        CommandMetadata(
            name="/recovery-options",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2ddfa6790a63284842345411659acb054d1562ceec623d2bd426165379055577",
        ),
        CommandMetadata(
            name="/recovery-apply",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="5105d2af62b1110f089ce90ed83a1a10cce01e48c1103ba93bf7980f0de5c2e6",
        ),
        CommandMetadata(
            name="/dead-letter-retry",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text", "command"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="26560613fdcf590c2a59653017ca2ef2d5d3da34309a59777699a9c47feb7822",
        ),
        CommandMetadata(
            name="/dead-letter-archive",
            aliases=(),
            domain="workers_recovery",
            handler="WorkersRecoveryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9eab0c0b56b618d61b810a8a4fc91b7c6e4a0c9fbe0d484422471338f60f4e86",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        if command == "/worker-list":
            return self._worker_list()
        if command == "/worker-show":
            return self._worker_show(argument_text)
        if command == "/worker-disable":
            return self._worker_disable(argument_text)
        if command == "/worker-register":
            return self._worker_register(argument_text)
        if command == "/worker-workload":
            return self._worker_workload(argument_text)
        if command == "/worker-attempts":
            return self._worker_attempts(argument_text)
        if command == "/worker-stale-scan":
            return self._worker_stale_scan(argument_text)
        if command == "/worker-heartbeat":
            return self._worker_heartbeat(argument_text)
        if command == "/task-history":
            return self._task_history(argument_text)
        if command == "/task-retry":
            return self._task_retry(argument_text)
        if command == "/task-attempts":
            return self._task_history(argument_text)
        if command in {"/task-assign", "/task-reassign"}:
            return self._task_assign_command(command, argument_text, command == "/task-reassign")
        if command == "/task-cancel":
            return self._task_cancel_command(argument_text)
        if command == "/task-verify":
            return self._task_verify_command(argument_text)
        if command in {"/recovery-show", "/recovery-evaluate"}:
            return self._recovery_evaluate_command(command, argument_text)
        if command == "/recovery-list":
            return self._recovery_list_command(argument_text)
        if command == "/recovery-history":
            return self._recovery_history_command(argument_text)
        if command == "/recovery-options":
            return self._recovery_options_command(argument_text)
        if command == "/recovery-apply":
            return self._recovery_apply_command(argument_text)
        if command == "/dead-letter-retry":
            return self._dead_letter_attempt_restore(argument_text, "/dead-letter-retry")
        if command == "/dead-letter-archive":
            return self._dead_letter_archive(argument_text)
        raise UnknownCommandError(command)

    def _worker_list(self) -> CommandResult:
        workers = (
            [asdict(item) for item in self.worker_registry.list()] if self.worker_registry else []
        )
        return CommandResult(
            command="/worker-list",
            status="ok",
            output=f"{len(workers)} worker(s).",
            data={"workers": workers},
        )

    def _worker_show(self, argument_text: str) -> CommandResult:
        worker_id = argument_text.strip()
        if not worker_id or not self.worker_registry:
            return CommandResult(
                command="/worker-show", status="error", output="Usage: /worker-show <worker_id>"
            )
        worker = self.worker_registry.get(worker_id)
        return CommandResult(
            command="/worker-show",
            status="ok",
            output=f"Worker {worker_id}: {worker.status}.",
            data=asdict(worker),
        )

    def _worker_disable(self, argument_text: str) -> CommandResult:
        worker_id = argument_text.strip()
        if not worker_id or not self.worker_registry:
            return CommandResult(
                command="/worker-disable",
                status="error",
                output="Usage: /worker-disable <worker_id>",
            )
        worker = self.worker_registry.disable(worker_id)
        return CommandResult(
            command="/worker-disable",
            status="ok",
            output=f"Worker {worker_id} disabled.",
            data=asdict(worker),
        )

    def _worker_register(self, argument_text: str) -> CommandResult:
        from synapse.missions.models import WorkerDescriptor

        parts = shlex.split(argument_text)
        if len(parts) < 2 or not self.worker_registry:
            return CommandResult(
                command="/worker-register",
                status="error",
                output="Usage: /worker-register <worker_id> <agent_id> [capability,...]",
            )
        capabilities = parts[2].split(",") if len(parts) > 2 and parts[2] else []
        worker = self.worker_registry.register(
            WorkerDescriptor(parts[0], parts[1], "idle", capabilities)
        )
        return CommandResult(
            command="/worker-register",
            status="ok",
            output=f"Worker {worker.worker_id} registered.",
            data=asdict(worker),
        )

    def _worker_workload(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) < 2 or not self.worker_registry:
            return CommandResult(
                command="/worker-workload",
                status="error",
                output="Usage: /worker-workload <worker_id> <0..1> [task_id] [attempt_id]",
            )
        worker = self.worker_registry.set_workload(
            parts[0],
            float(parts[1]),
            parts[2] if len(parts) > 2 else None,
            parts[3] if len(parts) > 3 else None,
        )
        return CommandResult(
            command="/worker-workload",
            status="ok",
            output=f"Worker {worker.worker_id} workload: {worker.workload}.",
            data=asdict(worker),
        )

    def _worker_attempts(self, argument_text: str) -> CommandResult:
        worker_id = argument_text.strip()
        if not worker_id or not self.attempts:
            return CommandResult(
                command="/worker-attempts",
                status="error",
                output="Usage: /worker-attempts <worker_id>",
            )
        attempts = [asdict(item) for item in self.attempts.list() if item.worker_id == worker_id]
        return CommandResult(
            command="/worker-attempts",
            status="ok",
            output=f"{len(attempts)} attempt(s).",
            data={"attempts": attempts},
        )

    def _worker_stale_scan(self, argument_text: str) -> CommandResult:
        seconds = int(argument_text.strip() or "120")
        workers = (
            [asdict(item) for item in self.worker_registry.expire_stale(seconds)]
            if self.worker_registry
            else []
        )
        return CommandResult(
            command="/worker-stale-scan",
            status="ok",
            output=f"{len(workers)} stale worker(s).",
            data={"workers": workers},
        )

    def _worker_heartbeat(self, argument_text: str) -> CommandResult:
        worker_id = argument_text.strip()
        if not worker_id or not self.worker_registry:
            return CommandResult(
                command="/worker-heartbeat",
                status="error",
                output="Usage: /worker-heartbeat <worker_id>",
            )
        worker = self.worker_registry.heartbeat(worker_id)
        return CommandResult(
            command="/worker-heartbeat",
            status="ok",
            output=f"Worker {worker_id} heartbeat updated.",
            data=asdict(worker),
        )

    def _task_history(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id or not self.attempts:
            return CommandResult(
                command="/task-history", status="error", output="Usage: /task-history <task_id>"
            )
        attempts = [asdict(item) for item in self.attempts.list(task_id=task_id)]
        return CommandResult(
            command="/task-history",
            status="ok",
            output=f"{len(attempts)} attempt(s).",
            data={"attempts": attempts},
        )

    def _task_retry(self, argument_text: str) -> CommandResult:
        attempt_id = argument_text.strip()
        if not attempt_id or not self.mission_recovery_runtime:
            return CommandResult(
                command="/task-retry", status="error", output="Usage: /task-retry <attempt_id>"
            )
        attempt = self.mission_recovery_runtime.schedule_retry(attempt_id)
        return CommandResult(
            command="/task-retry",
            status="ok",
            output=f"Retry attempt {attempt.attempt_id} created.",
            data=asdict(attempt),
        )

    def _task_assign_command(
        self, command: str, argument_text: str, reassign: bool
    ) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) != 4:
            return CommandResult(
                command=command,
                status="error",
                output=f"Usage: {command} <mission_id> <task_id> <worker_id> <revision>",
            )
        task = self.missions.assign_task(
            parts[0],
            parts[1],
            parts[2],
            expected_revision=int(parts[3]),
            reassign=reassign,
        )
        return CommandResult(
            command=command,
            status="ok",
            output=f"Task {parts[1]} assigned to {parts[2]}.",
            data=asdict(task),
        )

    def _task_cancel_command(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) != 3:
            return CommandResult(
                command="/task-cancel",
                status="error",
                output="Usage: /task-cancel <mission_id> <task_id> <revision>",
            )
        task = self.missions.cancel_task(parts[0], parts[1], expected_revision=int(parts[2]))
        return CommandResult(
            command="/task-cancel",
            status="ok",
            output=f"Task {parts[1]} cancelled.",
            data=asdict(task),
        )

    def _task_verify_command(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) != 2:
            return CommandResult(
                command="/task-verify",
                status="error",
                output="Usage: /task-verify <mission_id> <task_id>",
            )
        verification = self.missions.verify_task(parts[0], parts[1])
        return CommandResult(
            command="/task-verify",
            status="ok",
            output=f"Task verification: {verification.status}.",
            data=asdict(verification),
        )

    def _recovery_evaluate_command(self, command: str, argument_text: str) -> CommandResult:
        attempt_id = argument_text.strip()
        if not attempt_id or not self.mission_recovery_runtime:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <attempt_id>"
            )
        decision = self.mission_recovery_runtime.evaluate(attempt_id)
        return CommandResult(
            command=command,
            status="ok",
            output=f"Recovery action: {decision.action}.",
            data=asdict(decision),
        )

    def _recovery_list_command(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip() or None
        attempts = self.attempts.list(mission_id=mission_id) if self.attempts else []
        items = [
            asdict(item)
            for item in attempts
            if item.status in {"failed", "timed_out", "recovery_pending", "dead_lettered"}
        ]
        return CommandResult(
            command="/recovery-list",
            status="ok",
            output=f"{len(items)} recovery item(s).",
            data={"items": items},
        )

    def _recovery_history_command(self, argument_text: str) -> CommandResult:
        attempt_id = argument_text.strip()
        if not attempt_id or not self.attempts:
            return CommandResult(
                command="/recovery-history",
                status="error",
                output="Usage: /recovery-history <attempt_id>",
            )
        attempt = self.attempts.get(attempt_id)
        history = [
            asdict(item)
            for item in self.attempts.list(task_id=attempt.task_id)
            if item.recovery_action or item.attempt_number >= attempt.attempt_number
        ]
        return CommandResult(
            command="/recovery-history",
            status="ok",
            output=f"{len(history)} recovery attempt(s).",
            data={"history": history},
        )

    def _recovery_options_command(self, argument_text: str) -> CommandResult:
        attempt_id = argument_text.strip()
        if not attempt_id or not self.mission_recovery_runtime:
            return CommandResult(
                command="/recovery-options",
                status="error",
                output="Usage: /recovery-options <attempt_id>",
            )
        decision = self.mission_recovery_runtime.evaluate(attempt_id)
        return CommandResult(
            command="/recovery-options",
            status="ok",
            output=f"Recommended recovery: {decision.action}.",
            data={
                "recommended": asdict(decision),
                "supported_actions": [
                    "retry_same_worker",
                    "retry_other_worker",
                    "retry_other_agent",
                    "change_model",
                    "change_provider",
                    "replan",
                    "reduce_scope",
                    "pause_mission",
                    "require_intervention",
                    "dead_letter",
                ],
            },
        )

    def _recovery_apply_command(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) < 2 or not self.mission_recovery_runtime:
            return CommandResult(
                command="/recovery-apply",
                status="error",
                output="Usage: /recovery-apply <attempt_id> <action> [idempotency_key]",
            )
        result = self.mission_recovery_runtime.apply(
            parts[0],
            parts[1],
            idempotency_key=parts[2] if len(parts) > 2 else None,
        )
        data = asdict(result) if hasattr(result, "__dataclass_fields__") else result
        return CommandResult(
            command="/recovery-apply",
            status="ok",
            output=f"Recovery {parts[1]} applied.",
            data=data,
        )

    def _dead_letter_attempt_restore(self, argument_text: str, command: str) -> CommandResult:
        dlq_id = argument_text.strip()
        if not dlq_id or not self.mission_recovery_runtime:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <dlq_id>"
            )
        attempt = self.mission_recovery_runtime.restore_dead_letter(dlq_id)
        return CommandResult(
            command=command,
            status="ok",
            output=f"Attempt {attempt.attempt_id} restored.",
            data=asdict(attempt),
        )

    def _dead_letter_archive(self, argument_text: str) -> CommandResult:
        dlq_id = argument_text.strip()
        if not dlq_id:
            return CommandResult(
                command="/dead-letter-archive",
                status="error",
                output="Usage: /dead-letter-archive <dlq_id>",
            )
        entry = self.dead_letter.archive_entry(dlq_id)
        return CommandResult(
            command="/dead-letter-archive",
            status="ok",
            output=f"Dead letter {dlq_id} archived.",
            data=asdict(entry),
        )
