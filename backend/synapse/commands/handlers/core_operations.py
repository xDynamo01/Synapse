from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.permissions import PermissionContext


class CoreOperationsCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/tasks",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="588fb67e5e4cd7569102505a331cf42cb2b5a7310a22714c709f666b3060f445",
        ),
        CommandMetadata(
            name="/memory",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2e7f1725feb333018dc74aac91b6a5d921de8a65ca5e3808723a5fa1480612d8",
        ),
        CommandMetadata(
            name="/call",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text", "source_agent_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="55f3b43d841e71e4eae0c50984705330aa986593d841f2d7f6ef4e4cb5b12092",
        ),
        CommandMetadata(
            name="/task",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="eb1011f95f820fc0630a203932b56f76626ee63f4f9936f09dbf8da8fecc8cf9",
        ),
        CommandMetadata(
            name="/remember",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="1564c754c3243853fee4fcb5c50ffb8cc4b10c957c83673462346e3dcea624e3",
        ),
        CommandMetadata(
            name="/search",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "query"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2fe4db81f958e5468f4f03d4689a4db66043c727cdf16785877fe4682e2ff5d8",
        ),
        CommandMetadata(
            name="/approvals",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="08e41eaca1dbcbfd7a931b41b03f75940a8e8352d1f9c50e3027188911ccc676",
        ),
        CommandMetadata(
            name="/approve",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "approval_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="775e4211b35108493e8c4aedefd5bb757793a73f0cd75277c82d4f1c2df15ccd",
        ),
        CommandMetadata(
            name="/reject",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "approval_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e42179baf24f19ad8bd2e63574662ca6348a9a1e75840cfa7567d945f863aa68",
        ),
        CommandMetadata(
            name="/inbox",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="37250d6c6560db2a01e474aef58074fe7e4698407065437eb3b6b184d533f00c",
        ),
        CommandMetadata(
            name="/process-inbox",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="3c17748c1ebf648b6157b89fed25890de968532b63a74a1fdbc81c5a337eefb4",
        ),
        CommandMetadata(
            name="/process-delegations",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c2a42c563e26d99177da635bcc35922f16c0b7746a94f3f99e490bdd959bc9ff",
        ),
        CommandMetadata(
            name="/worker-status",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="ae5afbe3fc83ef6b0498aebec7064485217a8ba51b3e77a40b2f1bdd116372ce",
        ),
        CommandMetadata(
            name="/jobs",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("argument_text",),
            defaults=("argument_text=''",),
            category="user/admin useful",
            status="active",
            source_sha256="4a056dc686eb69797d6ed3d3277a6a42c0f4a98d8d09ede9aa3846d06e79b18c",
        ),
        CommandMetadata(
            name="/enqueue-inbox",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="833644c1be8abefad2d54aac5d8ef840dd14a10e98bb95370c86b7347dce277a",
        ),
        CommandMetadata(
            name="/enqueue-delegations",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="8a13fd56e452250a6b863346f3a915cc0dbf8abd622022cf1fb74d06749aa263",
        ),
        CommandMetadata(
            name="/run-jobs",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c11e3a1aabff9d4f8fa23efefa125733318147917c138b93b7ee84725f918159",
        ),
        CommandMetadata(
            name="/cancel-job",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="0499493f6481ed243d11e9d7e16dd896e59d6febbe464ab3550eac5245224868",
        ),
        CommandMetadata(
            name="/daemon-status",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="f10ec5767c572cba319dab7fc8f58a173a64e6dbec93d6aef227f4050495ae01",
        ),
        CommandMetadata(
            name="/daemon-run-once",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="c2648435845d3bd396d9ad55017ea79e58ca74bea263ce3b69a752140f18bb61",
        ),
        CommandMetadata(
            name="/trace",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("correlation_id",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="a676b239a47f75084918bc7190349cff468027afdb24d8c32198626827ec9ece",
        ),
        CommandMetadata(
            name="/presence",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2c5ea45f02ff66eede3b75d3b5074803274ce33c341559730ca8ef209c8d5c4f",
        ),
        CommandMetadata(
            name="/lifecycle",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e22712d3d7bfdb75ac75eb4c243329f9ba7a95c5428a0b6138141aaa922524a5",
        ),
        CommandMetadata(
            name="/wake",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6d702cd25098dfe2f8d375e85a333585a7af974a7798cd3928c6e400298d9f2a",
        ),
        CommandMetadata(
            name="/sleep",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="826e4f8afdd5abf3d565c111ace43ced7b229c7b4c0cabf8486735dde3b4eb70",
        ),
        CommandMetadata(
            name="/notifications",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2028731f10fddffa59111e1fd723d84527aeaf56963d2504c9c7e42fc5d1a56a",
        ),
        CommandMetadata(
            name="/read-notification",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context", "notification_id"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="d8d9a6b0638310a9394f75c0c52599b84a6b78a965b0463f48af2d87197c8097",
        ),
        CommandMetadata(
            name="/recurring-jobs",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c5590d83baee2fa0034bd31bfdcc8e90867e359e6c577a6aac54c3d9ae4eaa48",
        ),
        CommandMetadata(
            name="/run-recurring",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=("context",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c3fb67608fef07b33dfe09ea162e52a1ef04a04bc9818bd946ccd90a4bde1d01",
        ),
        CommandMetadata(
            name="/scheduler-lock",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="888f435697bfddc19c83a398f329586dd0942b0575358ed2575f7f529af02720",
        ),
        CommandMetadata(
            name="/runner-status",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="9c7f3542f1f8319f0c91043c098d680461cd969c86b3a556e23075fed4cca7ae",
        ),
        CommandMetadata(
            name="/runner-heartbeat",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="29a0ebbd643a4ce43f51c160894049c4c5d95c04438469f56195c6aeaedbbc1e",
        ),
        CommandMetadata(
            name="/health",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="14b79fedca7f4d9f4463252723c58f5955d51dbba96f1e3c2d7b02df0375a977",
        ),
        CommandMetadata(
            name="/readiness",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a19ce5853bd31815d05cf5f069fb241964ddfe157d5db0e6eb5fe53486e4ec32",
        ),
        CommandMetadata(
            name="/readiness-issues",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="55394a0179c17cf2f7a3825e773ef456d83e644af13a0e2a413f0560f4f595d7",
        ),
        CommandMetadata(
            name="/readiness-actions",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9aee298385101e897f48cbcf012223361d4e11b3c9f93869cf3fda17075e66ec",
        ),
        CommandMetadata(
            name="/migrations",
            aliases=(),
            domain="core_operations",
            handler="CoreOperationsCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="26ebb474d681055e98c4df0d3be34ad9996cccc81cabc0dc5f7f7249c18a3a85",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        source_agent_id = command_context.source_agent_id
        context = command_context.permission
        if command == "/tasks":
            return self._tasks()
        if command == "/memory":
            return self._memory(context)
        if command == "/call":
            return self._call(context, argument_text, source_agent_id)
        if command == "/task":
            return self._task(context, argument_text)
        if command == "/remember":
            return self._remember(context, argument_text)
        if command == "/search":
            return self._search(context, argument_text)
        if command == "/approvals":
            return self._approvals()
        if command == "/approve":
            return self._approve(context, argument_text)
        if command == "/reject":
            return self._reject(context, argument_text)
        if command == "/inbox":
            return self._inbox(context, argument_text)
        if command == "/process-inbox":
            return self._process_inbox(context, argument_text)
        if command == "/process-delegations":
            return self._process_delegations(context, argument_text)
        if command == "/worker-status":
            return self._worker_status()
        if command == "/jobs":
            return self._jobs(argument_text)
        if command == "/enqueue-inbox":
            return self._enqueue_inbox(context, argument_text)
        if command == "/enqueue-delegations":
            return self._enqueue_delegations(context, argument_text)
        if command == "/run-jobs":
            return self._run_jobs(context)
        if command == "/cancel-job":
            return self._cancel_job(context, argument_text)
        if command == "/daemon-status":
            return self._daemon_status()
        if command == "/daemon-run-once":
            return self._daemon_run_once(context)
        if command == "/trace":
            return self._trace(argument_text)
        if command == "/presence":
            return self._presence(argument_text)
        if command == "/lifecycle":
            return self._lifecycle(argument_text)
        if command == "/wake":
            return self._wake(argument_text)
        if command == "/sleep":
            return self._sleep(argument_text)
        if command == "/notifications":
            return self._notifications(argument_text)
        if command == "/read-notification":
            return self._read_notification(context, argument_text)
        if command == "/recurring-jobs":
            return self._recurring_jobs()
        if command == "/run-recurring":
            return self._run_recurring(context)
        if command == "/scheduler-lock":
            return self._scheduler_lock()
        if command == "/runner-status":
            return self._runner_status()
        if command == "/runner-heartbeat":
            return self._runner_heartbeat()
        if command == "/health":
            return self._health()
        if command == "/readiness":
            return self._readiness()
        if command == "/readiness-issues":
            return self._readiness_issues()
        if command == "/readiness-actions":
            return self._readiness_actions()
        if command == "/migrations":
            return self._migrations()
        raise UnknownCommandError(command)

    @staticmethod
    def _parse_key_value_arguments(parts: list[str]) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        for part in parts:
            key, separator, value = part.partition("=")
            if separator:
                arguments[key] = value
        return arguments

    def _tasks(self) -> CommandResult:
        tasks = [asdict(task) for task in self.tasks.list_tasks()]
        return CommandResult(
            command="/tasks",
            status="ok",
            output=f"{len(tasks)} task(s)",
            data={"tasks": tasks},
        )

    def _memory(self, context: PermissionContext) -> CommandResult:
        records = [asdict(item) for item in self.services.list_memory(context)]
        return CommandResult(
            command="/memory",
            status="ok",
            output=f"Loaded {len(records)} memory record(s).",
            data={"memory": records},
        )

    def _call(
        self,
        context: PermissionContext,
        argument_text: str,
        source_agent_id: str | None,
    ) -> CommandResult:
        to_agent_id, _, body = argument_text.partition(" ")
        if not to_agent_id or not body.strip():
            return CommandResult(
                command="/call",
                status="error",
                output="Usage: /call <agent> <message>",
            )

        from_agent_id = source_agent_id or self._default_agent_id()
        message = self.tools.execute(
            "send_agent_message",
            context,
            {
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "subject": "Command Runtime call",
                "body": body.strip(),
            },
        )
        return CommandResult(
            command="/call",
            status="ok",
            output=f"Message sent to {to_agent_id}.",
            data={"message": message},
        )

    def _task(self, context: PermissionContext, argument_text: str) -> CommandResult:
        title, agent_id = self._parse_task_arguments(argument_text)
        if not title:
            return CommandResult(
                command="/task",
                status="error",
                output="Usage: /task <title> --agent <agent>",
            )

        metadata: dict[str, str] = {}
        if agent_id:
            metadata["agent_id"] = agent_id
            metadata["assigned_agent"] = agent_id

        task = self.tools.execute(
            "create_task",
            context,
            {
                "title": title,
                "description": "",
                "metadata": metadata,
            },
        )
        return CommandResult(
            command="/task",
            status="ok",
            output=f"Task created: {title}",
            data={"task": task},
        )

    def _remember(self, context: PermissionContext, text: str) -> CommandResult:
        if not text:
            return CommandResult(
                command="/remember",
                status="error",
                output="Usage: /remember <text>",
            )
        record = self.services.create_memory(
            context,
            scope="user",
            owner_id=context.actor_id,
            source="command:/remember",
            content=text,
        )
        return CommandResult(
            command="/remember",
            status="ok",
            output="Saved explicit user memory.",
            data={"memory": asdict(record)},
        )

    def _search(self, context: PermissionContext, query: str) -> CommandResult:
        if not query:
            return CommandResult(
                command="/search",
                status="error",
                output="Usage: /search <query>",
            )
        result = self.tools.execute("web_search", context, {"query": query})
        search_status = str(result.get("status", "unavailable"))
        status = "ok" if search_status in {"results", "no_results"} else search_status
        return CommandResult(
            command="/search",
            status=status,
            output=result.get("message", "Search executed."),
            data={"search": result},
        )

    def _approvals(self) -> CommandResult:
        pending = [asdict(approval) for approval in self.approvals.list_pending()]
        return CommandResult(
            command="/approvals",
            status="ok",
            output=f"{len(pending)} pending approval(s)",
            data={"approvals": pending},
        )

    def _approve(self, context: PermissionContext, approval_id: str) -> CommandResult:
        if not approval_id:
            return CommandResult(
                command="/approve",
                status="error",
                output="Usage: /approve <approval_id>",
            )
        approval, tool_result = self.approval_resume.approve_and_resume(context, approval_id)
        status = "resumed" if tool_result.success else "approved"
        output = (
            f"Approved and executed {approval_id}."
            if tool_result.success
            else f"Approved {approval_id}, but resume did not execute."
        )
        return CommandResult(
            command="/approve",
            status=status,
            output=output,
            data={"approval": asdict(approval), "tool_result": asdict(tool_result)},
        )

    def _reject(self, context: PermissionContext, approval_id: str) -> CommandResult:
        if not approval_id:
            return CommandResult(
                command="/reject",
                status="error",
                output="Usage: /reject <approval_id>",
            )
        approval = self.approvals.reject(context, approval_id)
        return CommandResult(
            command="/reject",
            status="ok",
            output=f"Rejected {approval_id}.",
            data={"approval": asdict(approval)},
        )

    def _inbox(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/inbox",
                status="error",
                output="Usage: /inbox <agent_id>",
            )
        messages = [asdict(message) for message in self.worker.list_inbox(context, agent_id)]
        return CommandResult(
            command="/inbox",
            status="ok",
            output=f"{len(messages)} inbox message(s) for {agent_id}.",
            data={"messages": messages},
        )

    def _process_inbox(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/process-inbox",
                status="error",
                output="Usage: /process-inbox <agent_id>",
            )
        results = [asdict(result) for result in self.worker.process_inbox(context, agent_id)]
        return CommandResult(
            command="/process-inbox",
            status="ok",
            output=f"Processed {len(results)} inbox message(s) for {agent_id}.",
            data={"results": results},
        )

    def _process_delegations(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        parts = argument_text.split()
        agent_id = parts[0].strip().lower() if parts else ""
        if not agent_id:
            return CommandResult(
                command="/process-delegations",
                status="error",
                output="Usage: /process-delegations <agent_id> [limit]",
            )
        limit = int(parts[1]) if len(parts) > 1 else 1
        results = [
            asdict(result)
            for result in self.worker.process_delegations(context, agent_id, limit=limit)
        ]
        return CommandResult(
            command="/process-delegations",
            status="ok",
            output=f"Processed {len(results)} delegation task(s) for {agent_id}.",
            data={"results": results},
        )

    def _worker_status(self) -> CommandResult:
        status = asdict(self.worker.status())
        return CommandResult(
            command="/worker-status",
            status="ok",
            output="Worker status loaded.",
            data={"worker": status},
        )

    def _jobs(self, argument_text: str = "") -> CommandResult:
        status = argument_text.strip() or None
        jobs = [asdict(job) for job in self.scheduler.list_jobs(status=status)]
        return CommandResult(
            command="/jobs",
            status="ok",
            output=f"{len(jobs)} job(s).",
            data={"jobs": jobs},
        )

    def _enqueue_inbox(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/enqueue-inbox",
                status="error",
                output="Usage: /enqueue-inbox <agent_id>",
            )
        job = self.scheduler.enqueue(
            context,
            "process_agent_inbox",
            {"agent_id": agent_id},
        )
        return CommandResult(
            command="/enqueue-inbox",
            status="ok",
            output=f"Enqueued inbox processing for {agent_id}.",
            data={"job": asdict(job)},
        )

    def _enqueue_delegations(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = argument_text.split()
        agent_id = parts[0].strip().lower() if parts else ""
        if not agent_id:
            return CommandResult(
                command="/enqueue-delegations",
                status="error",
                output="Usage: /enqueue-delegations <agent_id> [limit]",
            )
        limit = int(parts[1]) if len(parts) > 1 else 1
        job = self.scheduler.enqueue(
            context,
            "process_agent_delegations",
            {"agent_id": agent_id, "limit": limit},
        )
        return CommandResult(
            command="/enqueue-delegations",
            status="ok",
            output=f"Enqueued delegation processing for {agent_id}.",
            data={"job": asdict(job)},
        )

    def _run_jobs(self, context: PermissionContext) -> CommandResult:
        jobs = [asdict(job) for job in self.scheduler.run_all_pending(context)]
        return CommandResult(
            command="/run-jobs",
            status="ok",
            output=f"Ran {len(jobs)} job(s).",
            data={"jobs": jobs},
        )

    def _cancel_job(self, context: PermissionContext, argument_text: str) -> CommandResult:
        job_id = argument_text.strip()
        if not job_id:
            return CommandResult(
                command="/cancel-job",
                status="error",
                output="Usage: /cancel-job <job_id>",
            )
        job = self.scheduler.cancel_job(context, job_id)
        return CommandResult(
            command="/cancel-job",
            status="ok",
            output=f"Cancelled job {job_id}.",
            data={"job": asdict(job)},
        )

    def _daemon_status(self) -> CommandResult:
        status = asdict(self.daemon.status())
        return CommandResult(
            command="/daemon-status",
            status="ok",
            output="Daemon status loaded.",
            data={"daemon": status},
        )

    def _daemon_run_once(self, context: PermissionContext) -> CommandResult:
        status = self.daemon.run_once(context)
        return CommandResult(
            command="/daemon-run-once",
            status="ok",
            output=f"Daemon tick completed with {len(status.last_jobs_run)} job(s).",
            data={"daemon": asdict(status)},
        )

    def _presence(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if agent_id:
            presence = self.presence.get(agent_id)
            return CommandResult(
                command="/presence",
                status="ok",
                output=f"Presence for {agent_id}: {presence.state}",
                data={"presence": asdict(presence)},
            )
        presences = [asdict(presence) for presence in self.presence.list_all()]
        return CommandResult(
            command="/presence",
            status="ok",
            output=f"{len(presences)} presence record(s).",
            data={"presence": presences},
        )

    def _lifecycle(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if agent_id:
            lifecycle = self.lifecycle.get(agent_id)
            return CommandResult(
                command="/lifecycle",
                status="ok",
                output=f"Lifecycle for {agent_id}: {lifecycle.state}",
                data={"lifecycle": asdict(lifecycle)},
            )
        lifecycles = [asdict(lifecycle) for lifecycle in self.lifecycle.list_all()]
        return CommandResult(
            command="/lifecycle",
            status="ok",
            output=f"{len(lifecycles)} lifecycle record(s).",
            data={"lifecycle": lifecycles},
        )

    def _wake(self, argument_text: str) -> CommandResult:
        agent_id, _, reason = argument_text.strip().partition(" ")
        if not agent_id:
            return CommandResult(
                command="/wake",
                status="error",
                output="Usage: /wake <agent_id>",
            )
        lifecycle = self.lifecycle.wake(agent_id.lower(), reason.strip() or "command wake")
        return CommandResult(
            command="/wake",
            status="ok",
            output=f"Woke {agent_id.lower()}.",
            data={"lifecycle": asdict(lifecycle)},
        )

    def _sleep(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/sleep",
                status="error",
                output="Usage: /sleep <agent_id>",
            )
        lifecycle = self.lifecycle.sleep(agent_id)
        return CommandResult(
            command="/sleep",
            status="ok",
            output=f"Put {agent_id} into idle lifecycle state.",
            data={"lifecycle": asdict(lifecycle)},
        )

    def _notifications(self, argument_text: str) -> CommandResult:
        argument = argument_text.strip().lower()
        if argument == "cleanup":
            result = self.notifications.cleanup_notifications()
            return CommandResult(
                command="/notifications",
                status="ok",
                output=f"Notification cleanup deleted {result.deleted} notification(s).",
                data={"cleanup": asdict(result)},
            )
        unread_only = argument == "unread"
        notifications = (
            self.notifications.list_unread()
            if unread_only
            else self.notifications.list_notifications()
        )
        payload = [asdict(notification) for notification in notifications]
        return CommandResult(
            command="/notifications",
            status="ok",
            output=f"{len(payload)} notification(s).",
            data={"notifications": payload},
        )

    def _read_notification(
        self,
        context: PermissionContext,
        notification_id: str,
    ) -> CommandResult:
        notification_id = notification_id.strip()
        if not notification_id:
            return CommandResult(
                command="/read-notification",
                status="error",
                output="Usage: /read-notification <id>",
            )
        notification = self.notifications.mark_read(notification_id, context)
        return CommandResult(
            command="/read-notification",
            status="ok",
            output=f"Notification read: {notification.title}",
            data={"notification": asdict(notification)},
        )

    def _recurring_jobs(self) -> CommandResult:
        recurring = [asdict(job) for job in self.scheduler.load_recurring_jobs()]
        return CommandResult(
            command="/recurring-jobs",
            status="ok",
            output=f"{len(recurring)} recurring job(s).",
            data={"recurring_jobs": recurring},
        )

    def _run_recurring(self, context: PermissionContext) -> CommandResult:
        jobs = [asdict(job) for job in self.scheduler.enqueue_due_recurring_jobs(context)]
        return CommandResult(
            command="/run-recurring",
            status="ok",
            output=f"Enqueued {len(jobs)} recurring job(s).",
            data={"jobs": jobs},
        )

    def _scheduler_lock(self) -> CommandResult:
        status = self.scheduler.lock_status()
        state = "locked" if status["locked"] and not status["stale"] else "unlocked"
        return CommandResult(
            command="/scheduler-lock",
            status="ok",
            output=f"Scheduler lock is {state}.",
            data={"lock": status},
        )

    def _runner_status(self) -> CommandResult:
        identity = self.runner_identity.load()
        return CommandResult(
            command="/runner-status",
            status="ok",
            output=f"Runner {identity.runner_id}: {identity.status}",
            data={"runner": asdict(identity)},
        )

    def _runner_heartbeat(self) -> CommandResult:
        identity = self.runner_identity.heartbeat()
        return CommandResult(
            command="/runner-heartbeat",
            status="ok",
            output=f"Heartbeat updated for runner {identity.runner_id}.",
            data={"runner": asdict(identity)},
        )

    def _health(self) -> CommandResult:
        summary = self.health.summary()
        return CommandResult(
            command="/health",
            status="ok",
            output=f"Homelab health: {summary.status}",
            data={"health": asdict(summary)},
        )

    def _readiness(self) -> CommandResult:
        summary = self.readiness.evaluate()
        return CommandResult(
            command="/readiness",
            status="ok",
            output=f"Operational readiness: {summary.state}",
            data={"readiness": asdict(summary)},
        )

    def _readiness_issues(self) -> CommandResult:
        issues = [asdict(issue) for issue in self.readiness.blocking_issues()]
        return CommandResult(
            command="/readiness-issues",
            status="ok",
            output=f"{len(issues)} blocking readiness issue(s).",
            data={"issues": issues},
        )

    def _readiness_actions(self) -> CommandResult:
        actions = self.readiness.recommended_actions()
        return CommandResult(
            command="/readiness-actions",
            status="ok",
            output=f"{len(actions)} recommended action(s).",
            data={"actions": actions},
        )

    def _migrations(self) -> CommandResult:
        status = self.migrations.migration_status()
        return CommandResult(
            command="/migrations",
            status="ok",
            output=(
                f"{len(status.current_versions)} record type(s), "
                f"{status.migrations_available} migration(s) available."
            ),
            data={"migrations": asdict(status)},
        )

    @staticmethod
    def _parse_task_arguments(argument_text: str) -> tuple[str, str | None]:
        marker = " --agent "
        if marker not in argument_text:
            return argument_text.strip(), None
        title, _, agent_id = argument_text.partition(marker)
        return title.strip(), agent_id.strip() or None
