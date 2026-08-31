from __future__ import annotations

import shlex
from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.permissions import PermissionContext


class DelegationCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/delegations",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=("argument_text=''",),
            category="user/admin useful",
            status="active",
            source_sha256="4071ec80e0f818b7788cc1e9bb5a75af35f3ac592d17cf119626f20228a5716e",
        ),
        CommandMetadata(
            name="/delegation",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9dc41359b86ca94d6cb00ca752eda55141e79fc77bd3ec615a1c1aa1932969ae",
        ),
        CommandMetadata(
            name="/delegation-executions",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="5782dd786ae3026d3848d638d5aaabd7c2e6b6dc3565de394beab4d4953657a4",
        ),
        CommandMetadata(
            name="/delegation-execution",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9f5c90e778430a39d247f1950d8b049b498a2621916ce3c0a0ccabea02b4fe94",
        ),
        CommandMetadata(
            name="/delegation-inbox",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="bb3b6a775e1aa5f90a88b10efa832ce79cb2abb90db5e39b7ad8a6a10d4f4193",
        ),
        CommandMetadata(
            name="/delegation-summary",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="117061ce9be42380ee4b3c9cdc57dad34fd6707a0ff71a197dc519a4ab1b49f7",
        ),
        CommandMetadata(
            name="/delegation-scheduling-policy",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="df5c21642a3a49ccece33cb8552c7523be799e4d50c63ec365a33bfe62f33565",
        ),
        CommandMetadata(
            name="/delegation-autonomy-policy",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="98e604122e8819c8888a0f45c827012af849e431f185e2076bb4f5baea360bf5",
        ),
        CommandMetadata(
            name="/delegation-autonomy-check",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="723b17b6ec0087b5f0ac9503cdc874d615de0c9581a04bceb6d8bedca8286f4a",
        ),
        CommandMetadata(
            name="/delegation-retry-policy",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="1e7e670de904e9d76af28f837dd311abce1bd208fa40ce0dcaa70a46b0eb001a",
        ),
        CommandMetadata(
            name="/delegation-retry-check",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="7c3190399e9a275238aa514b0ad1b87a86dcb8ea49af8888afc0451130db9feb",
        ),
        CommandMetadata(
            name="/retry-delegation",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="47cb44b94dfde69538ec4ff837349a093fef74450d30d44c6a20e2b422305a92",
        ),
        CommandMetadata(
            name="/delegation-timeout-policy",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="b72c69749a53b67dbadf69e509a99f8a20986446b4396d799523bbfd93cb7af5",
        ),
        CommandMetadata(
            name="/delegation-timeout-scan",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6098ed378a0ed2c0d2179fb6fc6eafc6ccbf3875c2dcbbdebbdb1c41c829aafe",
        ),
        CommandMetadata(
            name="/delegation-timeout-check",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="52126f1822342423cf319575e2c6b7a9a8ee3204c85069728b99c86dfcea7918",
        ),
        CommandMetadata(
            name="/apply-delegation-timeout",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a60170fa643ed09090c0790a3ae5bbe0130c1a505b12c9e414c19a28ea4f4b06",
        ),
        CommandMetadata(
            name="/delegation-next",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="320ce03036628bd19208d42cc7443b7cf10c40d3818470eb3b772330ed93d0de",
        ),
        CommandMetadata(
            name="/delegation-order",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2af3cc04bbe53eafcb8f919d15a31dc7bfa88b46b0f2b1fb610e9617bf4c613a",
        ),
        CommandMetadata(
            name="/rebuild-delegation-inbox",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="74d5ab75e8e2051fa5298130b2964c3ec93f23717a318f7d52bf46ccd7ec6496",
        ),
        CommandMetadata(
            name="/rebuild-all-delegation-inboxes",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="141481f36c97265ad5d342ba19abcacbc1a46579a4cc99af1af130fb4b2e6407",
        ),
        CommandMetadata(
            name="/create-delegation",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="eb98c28f40687d7c6d154e6c55f5d9250952344ab8bdbcb8f768dfb010c0cc7e",
        ),
        CommandMetadata(
            name="/accept-delegation",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="64c5315b018b8dea4c314d2808fc38af3a05056e106db1ad723d2acc7e229d29",
        ),
        CommandMetadata(
            name="/reject-delegation",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="7c19a9bc48e731926ee2820de15ecc36ac0a0043fb9673f58a0339ebd8de3777",
        ),
        CommandMetadata(
            name="/start-delegation",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="62c92a6ec1285cc91197a3853a44a0710f81b5c620ed3381399457499729e4c2",
        ),
        CommandMetadata(
            name="/complete-delegation",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="db6a8ee63d24a2075130a34e8f5925d0781b5800df91f66e1af0a1396191d62b",
        ),
        CommandMetadata(
            name="/delegation-completion",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="994fda6e7b7ed7b394fe3f17107cf3eb6d0e98137afd6298ac51e78ab0ed907a",
        ),
        CommandMetadata(
            name="/apply-delegation-completion",
            aliases=(),
            domain="delegation",
            handler="DelegationCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="50a6744f0f97e061bcdf5be61523c4b84f221614d5b19ca2cf89f64f1c75b7e0",
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
        if command == "/delegations":
            return self._delegations(argument_text)
        if command == "/delegation":
            return self._delegation(argument_text)
        if command == "/delegation-executions":
            return self._delegation_executions(argument_text)
        if command == "/delegation-execution":
            return self._delegation_execution(argument_text)
        if command == "/delegation-inbox":
            return self._delegation_inbox(argument_text)
        if command == "/delegation-summary":
            return self._delegation_summary(argument_text)
        if command == "/delegation-scheduling-policy":
            return self._delegation_scheduling_policy()
        if command == "/delegation-autonomy-policy":
            return self._delegation_autonomy_policy()
        if command == "/delegation-autonomy-check":
            return self._delegation_autonomy_check(context, argument_text)
        if command == "/delegation-retry-policy":
            return self._delegation_retry_policy()
        if command == "/delegation-retry-check":
            return self._delegation_retry_check(argument_text)
        if command == "/retry-delegation":
            return self._retry_delegation(context, argument_text)
        if command == "/delegation-timeout-policy":
            return self._delegation_timeout_policy()
        if command == "/delegation-timeout-scan":
            return self._delegation_timeout_scan(argument_text)
        if command == "/delegation-timeout-check":
            return self._delegation_timeout_check(argument_text)
        if command == "/apply-delegation-timeout":
            return self._apply_delegation_timeout(argument_text)
        if command == "/delegation-next":
            return self._delegation_next(argument_text)
        if command == "/delegation-order":
            return self._delegation_order(argument_text)
        if command == "/rebuild-delegation-inbox":
            return self._rebuild_delegation_inbox(argument_text)
        if command == "/rebuild-all-delegation-inboxes":
            return self._rebuild_all_delegation_inboxes()
        if command == "/create-delegation":
            return self._create_delegation(context, argument_text)
        if command == "/accept-delegation":
            return self._accept_delegation(context, argument_text)
        if command == "/reject-delegation":
            return self._reject_delegation(context, argument_text)
        if command == "/start-delegation":
            return self._start_delegation(context, argument_text)
        if command == "/complete-delegation":
            return self._complete_delegation(context, argument_text)
        if command == "/delegation-completion":
            return self._delegation_completion(argument_text)
        if command == "/apply-delegation-completion":
            return self._apply_delegation_completion(context, argument_text)
        raise UnknownCommandError(command)

    def _delegations(self, argument_text: str = "") -> CommandResult:
        status = argument_text.strip() or None
        delegations = [asdict(task) for task in self.delegation.list_tasks(status=status)]
        return CommandResult(
            command="/delegations",
            status="ok",
            output=f"{len(delegations)} delegation task(s).",
            data={"delegations": delegations},
        )

    def _delegation(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/delegation",
                status="error",
                output="Usage: /delegation <task_id>",
            )
        task = self.delegation.get_task(task_id)
        return CommandResult(
            command="/delegation",
            status="ok",
            output=f"Delegation {task.task_id}: {task.status}.",
            data={"delegation": asdict(task)},
        )

    def _delegation_executions(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/delegation-executions",
                status="error",
                output="Usage: /delegation-executions <task_id>",
            )
        executions = [
            asdict(execution)
            for execution in self.delegation_execution.list_task_executions(task_id)
        ]
        return CommandResult(
            command="/delegation-executions",
            status="ok",
            output=f"{len(executions)} execution(s) for delegation {task_id}.",
            data={"executions": executions},
        )

    def _delegation_execution(self, argument_text: str) -> CommandResult:
        execution_id = argument_text.strip()
        if not execution_id:
            return CommandResult(
                command="/delegation-execution",
                status="error",
                output="Usage: /delegation-execution <execution_id>",
            )
        execution = self.delegation_execution.get_execution(execution_id)
        return CommandResult(
            command="/delegation-execution",
            status="ok",
            output=f"Delegation execution {execution.execution_id}: {execution.status}.",
            data={"execution": asdict(execution)},
        )

    def _delegation_inbox(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/delegation-inbox",
                status="error",
                output="Usage: /delegation-inbox <agent_id>",
            )
        entries = [asdict(entry) for entry in self.delegation_inbox.get_agent_inbox(agent_id)]
        return CommandResult(
            command="/delegation-inbox",
            status="ok",
            output=f"{len(entries)} delegation inbox entry(s) for {agent_id}.",
            data={"entries": entries},
        )

    def _delegation_summary(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/delegation-summary",
                status="error",
                output="Usage: /delegation-summary <agent_id>",
            )
        summary = self.delegation_inbox.get_inbox_summary(agent_id)
        return CommandResult(
            command="/delegation-summary",
            status="ok",
            output=f"Delegation summary for {summary.agent_id}: {summary.total_count} total.",
            data={"summary": asdict(summary)},
        )

    def _delegation_scheduling_policy(self) -> CommandResult:
        policy = self.delegation_scheduling.load_policy()
        return CommandResult(
            command="/delegation-scheduling-policy",
            status="ok",
            output="Delegation scheduling policy loaded.",
            data={"policy": asdict(policy)},
        )

    def _delegation_autonomy_policy(self) -> CommandResult:
        policy = self.delegation_autonomy.load_policy()
        return CommandResult(
            command="/delegation-autonomy-policy",
            status="ok",
            output="Delegation autonomy policy loaded.",
            data={"policy": asdict(policy)},
        )

    def _delegation_autonomy_check(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        parts = argument_text.split()
        if len(parts) != 2 or parts[1] not in {"accept", "start", "reject"}:
            return CommandResult(
                command="/delegation-autonomy-check",
                status="error",
                output="Usage: /delegation-autonomy-check <task_id> <accept|start|reject>",
            )
        task_id, action = parts
        task = self.delegation.get_task(task_id)
        identity = self.identities.load_identity(task.assignee_agent_id)
        effective_policy = self.policies.resolve(context, task.assignee_agent_id)
        decision = self.delegation_autonomy.explain_decision(
            task_id,
            action,
            task,
            identity,
            effective_policy,
        )
        return CommandResult(
            command="/delegation-autonomy-check",
            status="ok",
            output=f"Delegation autonomy {action}: {self._decision_word(decision)}.",
            data={"decision": decision.to_dict()},
        )

    def _delegation_retry_policy(self) -> CommandResult:
        policy = self.delegation_retry.load_policy()
        return CommandResult(
            command="/delegation-retry-policy",
            status="ok",
            output="Delegation retry policy loaded.",
            data={"policy": asdict(policy)},
        )

    def _delegation_retry_check(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/delegation-retry-check",
                status="error",
                output="Usage: /delegation-retry-check <task_id>",
            )
        task = self.delegation.get_task(task_id)
        executions = self.delegation_execution.list_task_executions(task_id)
        decision = self.delegation_retry.evaluate_retry(task, executions)
        return CommandResult(
            command="/delegation-retry-check",
            status="ok",
            output=f"Delegation retry: {self._retry_word(decision)}.",
            data={"decision": decision.to_dict()},
        )

    def _retry_delegation(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/retry-delegation",
                status="error",
                output="Usage: /retry-delegation <task_id>",
            )
        result = self.delegation.request_retry(task_id, context=context)
        return CommandResult(
            command="/retry-delegation",
            status="ok",
            output=f"Retry request for delegation {task_id}: {result['status']}.",
            data=result,
        )

    def _delegation_timeout_policy(self) -> CommandResult:
        policy = self.delegation_timeout.load_policy()
        return CommandResult(
            command="/delegation-timeout-policy",
            status="ok",
            output="Delegation timeout policy loaded.",
            data={"policy": asdict(policy)},
        )

    def _delegation_timeout_scan(self, argument_text: str) -> CommandResult:
        dry_run = "--apply" not in argument_text.split()
        result = self.delegation_timeout.run_timeout_scan(dry_run=dry_run)
        return CommandResult(
            command="/delegation-timeout-scan",
            status="ok",
            output=f"Timeout scan found {len(result.candidates)} candidate(s).",
            data={"result": asdict(result)},
        )

    def _delegation_timeout_check(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/delegation-timeout-check",
                status="error",
                output="Usage: /delegation-timeout-check <task_id>",
            )
        task = self.delegation.get_task(task_id)
        latest = self.delegation_execution.latest_execution(task_id)
        candidate = self.delegation_timeout.evaluate_timeout(task, latest)
        return CommandResult(
            command="/delegation-timeout-check",
            status="ok",
            output="Timeout candidate found." if candidate else "No timeout candidate.",
            data={"candidate": asdict(candidate) if candidate else None},
        )

    def _apply_delegation_timeout(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/apply-delegation-timeout",
                status="error",
                output="Usage: /apply-delegation-timeout <task_id>",
            )
        result = self.delegation_timeout.apply_timeout(task_id, dry_run=False)
        return CommandResult(
            command="/apply-delegation-timeout",
            status="ok",
            output=f"Timeout apply processed {len(result.candidates)} candidate(s).",
            data={"result": asdict(result)},
        )

    def _delegation_next(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/delegation-next",
                status="error",
                output="Usage: /delegation-next <agent_id>",
            )
        tasks = self._active_delegation_tasks(agent_id)
        decision = self.delegation_scheduling.select_next_task(agent_id, tasks)
        return CommandResult(
            command="/delegation-next",
            status="ok",
            output=f"Next delegation for {agent_id}: {decision.selected_task_id or 'none'}.",
            data={"decision": asdict(decision)},
        )

    def _delegation_order(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/delegation-order",
                status="error",
                output="Usage: /delegation-order <agent_id>",
            )
        tasks = self._active_delegation_tasks(agent_id)
        decision = self.delegation_scheduling.explain_task_order(agent_id, tasks)
        return CommandResult(
            command="/delegation-order",
            status="ok",
            output=f"{len(decision.ordered_task_ids)} delegation task(s) ordered for {agent_id}.",
            data={"decision": asdict(decision)},
        )

    def _active_delegation_tasks(self, agent_id: str):
        entries = self.delegation_inbox.get_active_tasks(agent_id)
        return [self.delegation.get_task(entry.task_id) for entry in entries]

    @staticmethod
    def _decision_word(decision) -> str:
        if decision.blocked:
            return "blocked"
        if decision.requires_approval:
            return "requires approval"
        if decision.allowed:
            return "allowed"
        return "not allowed"

    @staticmethod
    def _retry_word(decision) -> str:
        if decision.blocked:
            return "blocked"
        if decision.requires_approval:
            return "requires approval"
        if decision.allowed:
            return "allowed"
        return "not allowed"

    def _rebuild_delegation_inbox(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/rebuild-delegation-inbox",
                status="error",
                output="Usage: /rebuild-delegation-inbox <agent_id>",
            )
        entries = self.delegation_inbox.rebuild_agent_inbox(agent_id)
        return CommandResult(
            command="/rebuild-delegation-inbox",
            status="ok",
            output=f"Rebuilt delegation inbox for {agent_id}.",
            data={"entries": [asdict(entry) for entry in entries]},
        )

    def _rebuild_all_delegation_inboxes(self) -> CommandResult:
        rebuilt = self.delegation_inbox.rebuild_all_inboxes()
        return CommandResult(
            command="/rebuild-all-delegation-inboxes",
            status="ok",
            output=f"Rebuilt {len(rebuilt)} delegation inbox(es).",
            data={
                "inboxes": {
                    agent_id: [asdict(entry) for entry in entries]
                    for agent_id, entries in rebuilt.items()
                }
            },
        )

    def _create_delegation(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        try:
            tokens = shlex.split(argument_text)
        except ValueError as exc:
            return CommandResult(command="/create-delegation", status="error", output=str(exc))
        if len(tokens) < 4:
            return CommandResult(
                command="/create-delegation",
                status="error",
                output=(
                    'Usage: /create-delegation <requester> <assignee> "<title>" '
                    '"<description>" [--priority high] [--conversation <id>]'
                ),
            )
        requester, assignee, title, description = tokens[:4]
        priority = "normal"
        conversation_id = None
        index = 4
        while index < len(tokens):
            token = tokens[index]
            if token == "--priority" and index + 1 < len(tokens):
                priority = tokens[index + 1]
                index += 2
                continue
            if token == "--conversation" and index + 1 < len(tokens):
                conversation_id = tokens[index + 1]
                index += 2
                continue
            index += 1
        task = self.delegation.create_task(
            context=context,
            title=title,
            description=description,
            requester_agent_id=requester,
            assignee_agent_id=assignee,
            priority=priority,
            conversation_id=conversation_id,
        )
        return CommandResult(
            command="/create-delegation",
            status="ok",
            output=f"Created delegation {task.task_id}.",
            data={"delegation": asdict(task)},
        )

    def _accept_delegation(self, context: PermissionContext, argument_text: str) -> CommandResult:
        return self._delegation_transition(
            context,
            argument_text,
            "/accept-delegation",
            self.delegation.accept_task,
            "Accepted",
        )

    def _reject_delegation(self, context: PermissionContext, argument_text: str) -> CommandResult:
        return self._delegation_transition(
            context,
            argument_text,
            "/reject-delegation",
            self.delegation.reject_task,
            "Rejected",
        )

    def _start_delegation(self, context: PermissionContext, argument_text: str) -> CommandResult:
        return self._delegation_transition(
            context,
            argument_text,
            "/start-delegation",
            self.delegation.start_task,
            "Started",
        )

    def _complete_delegation(self, context: PermissionContext, argument_text: str) -> CommandResult:
        return self._delegation_transition(
            context,
            argument_text,
            "/complete-delegation",
            self.delegation.complete_task,
            "Completed",
        )

    def _delegation_completion(self, argument_text: str) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/delegation-completion",
                status="error",
                output="Usage: /delegation-completion <task_id>",
            )
        signal = self.delegation.get_completion_signal(task_id)
        if not signal:
            return CommandResult(
                command="/delegation-completion",
                status="ok",
                output=f"Delegation {task_id} has no completion signal.",
                data={"completion": None},
            )
        return CommandResult(
            command="/delegation-completion",
            status="ok",
            output=f"Delegation {task_id} completion signal: {signal.status}.",
            data={"completion": asdict(signal)},
        )

    def _apply_delegation_completion(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command="/apply-delegation-completion",
                status="error",
                output="Usage: /apply-delegation-completion <task_id>",
            )
        task = self.delegation.apply_completion_signal(context, task_id)
        return CommandResult(
            command="/apply-delegation-completion",
            status="ok",
            output=f"Applied completion signal for delegation {task.task_id}.",
            data={"delegation": asdict(task)},
        )

    def _delegation_transition(
        self,
        context: PermissionContext,
        argument_text: str,
        command: str,
        transition,
        verb: str,
    ) -> CommandResult:
        task_id = argument_text.strip()
        if not task_id:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <task_id>"
            )
        task = transition(context, task_id)
        return CommandResult(
            command=command,
            status="ok",
            output=f"{verb} delegation {task.task_id}.",
            data={"delegation": asdict(task)},
        )
