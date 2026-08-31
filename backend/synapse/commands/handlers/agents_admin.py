from __future__ import annotations

import shlex
from dataclasses import asdict

from synapse.agents.provisioning import AgentCreateRequest
from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.decisions.models import DecisionRequest


def _decision_summary(result) -> str:
    if result.blocked:
        return "blocked: " + "; ".join(result.blocked_reasons)
    if result.requires_approval:
        return f"requires approval by {result.approval_required_by}"
    if result.allowed:
        return "allowed"
    return "not allowed"


class AgentsAdminCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/agents",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=("argument_text=''",),
            category="user/admin useful",
            status="active",
            source_sha256="766688c32d63de1d29a6c33db36d29b98fafe7e7077b24cbea94431f394c8f2c",
        ),
        CommandMetadata(
            name="/agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="8c4b3dbe1c86789a8e02ac0987c7705dcc179b66b4213d9bba55d73f4da53c2f",
        ),
        CommandMetadata(
            name="/agent-directory",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=("argument_text=''",),
            category="user/admin useful",
            status="active",
            source_sha256="4f6eab0aff845ff8750c76a5781d486c618178ae65bba8c82a2c1cb02f2ee6e6",
        ),
        CommandMetadata(
            name="/agent-admin",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="d946d3fa1206384c46a2daabfcf35301f8d0873b7845c975de4e42204c64eb4b",
        ),
        CommandMetadata(
            name="/activate-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="acd8ede3a4ecc61d7bc2a0f6f3ce25f0c5fc14f79bc2a5f84753d7a94a3a5e31",
        ),
        CommandMetadata(
            name="/deactivate-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="227b383525f53acda152c9375bc932c84a6f091f2c02ba407ce46e2470a09752",
        ),
        CommandMetadata(
            name="/archive-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e599dae7d17fa2235ddaac38be66f0e15cfa5dc964d6cdad833f17ec55380c94",
        ),
        CommandMetadata(
            name="/restore-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="4878a6644db3229ec806e670d8e749128c62c0ba1f6c6cc68ff959f7daccd457",
        ),
        CommandMetadata(
            name="/delete-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="232cf5cdc0da39b9e904cb8d08ed015060dfa08892bcfd45bab648bfd5dd0929",
        ),
        CommandMetadata(
            name="/agent-audit",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9087b9baecd68b06515385c52eb616f0be2569b704414b494dc294f8eabf58c1",
        ),
        CommandMetadata(
            name="/agent-audit-recent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f7c0d8b7bc34b41352d3e32439eac116e2721cf48712a4ce320d137f63116be1",
        ),
        CommandMetadata(
            name="/agent-audit-summary",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="aced29c9aabfe68534a6567f906d6795b86d5731e98b6db22c8555038da4eabb",
        ),
        CommandMetadata(
            name="/admin-policy",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="75574a4560f8541a151e7f92a860d0b6d91625132420a6208c8309a245722864",
        ),
        CommandMetadata(
            name="/admin-check",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="415e5d690eb87b513d4a727e0055f2c556a9e7d2281107747421edce82007150",
        ),
        CommandMetadata(
            name="/admin-action-requests",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="137c7dd2f039ca8760e6b03136919e3074a0c5ce8198b1a19b331cf7c50c6d2e",
        ),
        CommandMetadata(
            name="/admin-action-request",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="50fa166d4a018f0d3a9df848cbc6dd01709b8e26935d4219b1648f89901eb7a3",
        ),
        CommandMetadata(
            name="/request-admin-action",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="d5d68dd8da1a47cf49affdff17feefc1bb4c61d3d8718436e8cbde1f31f82da0",
        ),
        CommandMetadata(
            name="/approve-admin-action",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="45e093192a9ead9254f10aa75080724f4334ca06f9caf7fe293f34cd01d24e2e",
        ),
        CommandMetadata(
            name="/reject-admin-action",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="210fa32561bec9e7a8a7a2d309c84715a0eecfe2657e07cc0fd40854a2187469",
        ),
        CommandMetadata(
            name="/apply-admin-action",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="8e1ff797e7fcd5aaa211cddd8ed1a73d2b2b1f5a54f7fef9e791d6078c002489",
        ),
        CommandMetadata(
            name="/admin-request-cleanup",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="e9cef170b6da83e2a208418742bb33d10c04f4311ad20b1c330353bea0435365",
        ),
        CommandMetadata(
            name="/admin-request-retention",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="4decac5168caa7c84976ce0aff464fd67e69ec6724924beff957cae64ef6e3bd",
        ),
        CommandMetadata(
            name="/decision-check",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="1c6a851bb7bb04f597d3cc49da1263a93bb80ebb3cd1358b22e088200f90a704",
        ),
        CommandMetadata(
            name="/retention",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="67684a4b8309ff761dc5507c78381c4ab678e6f9f0457396eaf2a2dea415a56f",
        ),
        CommandMetadata(
            name="/retention-domain",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="1a3221a8a1fabdb6a7ae02f8cbe1b068d68582a23765fcb04a92d487ef365b5f",
        ),
        CommandMetadata(
            name="/create-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="90d3c86e0750d4a9f849cd52b0124921bb86c575da18d055604f0f87681beb62",
        ),
        CommandMetadata(
            name="/preview-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="760c77322de822270ba1432d9696c9b3e311b023b9db640446d26400e9a37b9c",
        ),
        CommandMetadata(
            name="/validate-agent",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="e087407acf8523eeffb43ffbccbe887c11c8c23d0ae123074a1d4af5a5efa966",
        ),
        CommandMetadata(
            name="/agent-provisioning-status",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="5862fc9ca83f6327d6cabe2a3a80b02280bbb72da75811f33c7bc4f5b3757145",
        ),
        CommandMetadata(
            name="/agent-provisioning-policy",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="ffb012c2a90dec9d357fd955dd233763a17f8a8eea6a7866c68a54b12d38644c",
        ),
        CommandMetadata(
            name="/agent-provisioning-requests",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="4d23cef640e0cd642d8f65537da564889d7e9b732480eedce322b817089aeba0",
        ),
        CommandMetadata(
            name="/agent-provisioning-request",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="b4d8e145a488fa207bae15cd41ed92a2102a42036a822162b543544ca2b9d8ae",
        ),
        CommandMetadata(
            name="/approve-agent-provisioning",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="22b80252fb834febc7b485e2711adc44445893dba533b9078221a9a60ea8eabd",
        ),
        CommandMetadata(
            name="/reject-agent-provisioning",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="fb89c14615ea81c45524df5cc370af7e3906d49f82decc8f297dcc7c14521e04",
        ),
        CommandMetadata(
            name="/apply-agent-provisioning",
            aliases=(),
            domain="agents_admin",
            handler="AgentsAdminCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="d2921f7f8d3e1635a0c603107b1bd92f0810244552128ac70c808591abf210b5",
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
        if command == "/agents":
            return self._agents(argument_text)
        if command == "/agent":
            return self._agent(argument_text)
        if command == "/agent-directory":
            return self._agent_directory(argument_text)
        if command == "/agent-admin":
            return self._agent_admin(context, argument_text)
        if command == "/activate-agent":
            return self._activate_agent(context, argument_text)
        if command == "/deactivate-agent":
            return self._deactivate_agent(context, argument_text)
        if command == "/archive-agent":
            return self._archive_agent(context, argument_text)
        if command == "/restore-agent":
            return self._restore_agent(context, argument_text)
        if command == "/delete-agent":
            return self._delete_agent(context, argument_text)
        if command == "/agent-audit":
            return self._agent_audit(argument_text)
        if command == "/agent-audit-recent":
            return self._agent_audit_recent(argument_text)
        if command == "/agent-audit-summary":
            return self._agent_audit_summary(argument_text)
        if command == "/admin-policy":
            return self._admin_policy()
        if command == "/admin-check":
            return self._admin_check(context, argument_text)
        if command == "/admin-action-requests":
            return self._admin_action_requests()
        if command == "/admin-action-request":
            return self._admin_action_request(argument_text)
        if command == "/request-admin-action":
            return self._request_admin_action(context, argument_text)
        if command == "/approve-admin-action":
            return self._approve_admin_action(context, argument_text)
        if command == "/reject-admin-action":
            return self._reject_admin_action(context, argument_text)
        if command == "/apply-admin-action":
            return self._apply_admin_action(context, argument_text)
        if command == "/admin-request-cleanup":
            return self._admin_request_cleanup(argument_text)
        if command == "/admin-request-retention":
            return self._admin_request_retention()
        if command == "/decision-check":
            return self._decision_check(context, argument_text)
        if command == "/retention":
            return self._retention()
        if command == "/retention-domain":
            return self._retention_domain(argument_text)
        if command == "/create-agent":
            return self._create_agent(argument_text)
        if command == "/preview-agent":
            return self._preview_agent(argument_text)
        if command == "/validate-agent":
            return self._validate_agent(argument_text)
        if command == "/agent-provisioning-status":
            return self._agent_provisioning_status()
        if command == "/agent-provisioning-policy":
            return self._agent_provisioning_policy()
        if command == "/agent-provisioning-requests":
            return self._agent_provisioning_requests()
        if command == "/agent-provisioning-request":
            return self._agent_provisioning_request(argument_text)
        if command == "/approve-agent-provisioning":
            return self._approve_agent_provisioning(context, argument_text)
        if command == "/reject-agent-provisioning":
            return self._reject_agent_provisioning(context, argument_text)
        if command == "/apply-agent-provisioning":
            return self._apply_agent_provisioning(context, argument_text)
        raise UnknownCommandError(command)

    def _agents(self, argument_text: str = "") -> CommandResult:
        if argument_text.strip().lower() == "detail":
            identities = [
                agent_identity.to_dict()
                for agent_identity in [
                    self.identities.load_identity(agent.id) for agent in self.agents.list_agents()
                ]
            ]
            return CommandResult(
                command="/agents",
                status="ok",
                output=f"{len(identities)} agent identity record(s)",
                data={"agents": identities},
            )
        agents = [asdict(agent) for agent in self.agents.list_agents()]
        return CommandResult(
            command="/agents",
            status="ok",
            output=f"{len(agents)} agent(s)",
            data={"agents": agents},
        )

    def _agent(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip()
        if not agent_id:
            return CommandResult(
                command="/agent",
                status="error",
                output="Usage: /agent <id>",
            )
        identity = self.identities.load_identity(agent_id.lower())
        return CommandResult(
            command="/agent",
            status="ok",
            output=f"{identity.name}: {identity.role}",
            data={"agent": identity.to_dict()},
        )

    def _agent_directory(self, argument_text: str = "") -> CommandResult:
        include_archived = argument_text.strip().lower() in {"all", "include_archived", "archived"}
        agents = [asdict(item) for item in self.provisioning.admin.list_agents(include_archived)]
        return CommandResult(
            command="/agent-directory",
            status="ok",
            output=f"{len(agents)} agent(s).",
            data={"agents": agents},
        )

    def _agent_admin(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/agent-admin", status="error", output="Usage: /agent-admin <agent_id>"
            )
        status = self.provisioning.admin.get_agent_admin_status(agent_id)
        validation = self.provisioning.admin.validate_agent_admin_state(agent_id, context)
        return CommandResult(
            command="/agent-admin",
            status="ok",
            output=f"Agent {agent_id}: {status.status}.",
            data={"admin": asdict(status), "validation": asdict(validation)},
        )

    def _activate_agent(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        result = self.provisioning.admin.activate_agent(agent_id, context)
        return CommandResult(
            command="/activate-agent",
            status="ok",
            output=f"Activated agent {agent_id}.",
            data={"activation": asdict(result)},
        )

    def _deactivate_agent(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        result = self.provisioning.admin.deactivate_agent(agent_id, context)
        return CommandResult(
            command="/deactivate-agent",
            status="ok",
            output=f"Deactivated agent {agent_id}.",
            data={"activation": asdict(result)},
        )

    def _archive_agent(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        result = self.provisioning.admin.archive_agent(agent_id, context)
        return CommandResult(
            command="/archive-agent",
            status="ok",
            output=f"Archived agent {agent_id}.",
            data={"archive": asdict(result)},
        )

    def _restore_agent(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        result = self.provisioning.admin.restore_agent(agent_id, context)
        return CommandResult(
            command="/restore-agent",
            status="ok",
            output=f"Restored agent {agent_id}.",
            data={"archive": asdict(result)},
        )

    def _delete_agent(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        force = "--force" in parts
        parts = [part for part in parts if part != "--force"]
        if len(parts) != 2:
            return CommandResult(
                command="/delete-agent",
                status="error",
                output='Usage: /delete-agent <agent_id> "DELETE <agent_id>" [--force]',
            )
        result = self.provisioning.admin.delete_agent(
            parts[0].lower(), parts[1], context, force=force
        )
        return CommandResult(
            command="/delete-agent",
            status="ok",
            output=f"Deleted agent {result.agent_id}.",
            data={"deletion": asdict(result)},
        )

    def _agent_audit(self, argument_text: str) -> CommandResult:
        parts = argument_text.split()
        if not parts:
            return CommandResult(
                command="/agent-audit",
                status="error",
                output="Usage: /agent-audit <agent_id> [limit]",
            )
        agent_id = parts[0].lower()
        limit = int(parts[1]) if len(parts) > 1 else 50
        records = [asdict(record) for record in self.audit.list_agent_audit(agent_id, limit)]
        return CommandResult(
            command="/agent-audit",
            status="ok",
            output=f"{len(records)} audit record(s) for {agent_id}.",
            data={"records": records},
        )

    def _agent_audit_recent(self, argument_text: str) -> CommandResult:
        limit = int(argument_text.strip()) if argument_text.strip() else 100
        records = [asdict(record) for record in self.audit.list_recent_audit(limit)]
        return CommandResult(
            command="/agent-audit-recent",
            status="ok",
            output=f"{len(records)} recent agent audit record(s).",
            data={"records": records},
        )

    def _agent_audit_summary(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/agent-audit-summary",
                status="error",
                output="Usage: /agent-audit-summary <agent_id>",
            )
        summary = self.audit.get_agent_audit_summary(agent_id)
        return CommandResult(
            command="/agent-audit-summary",
            status="ok",
            output=f"{summary.total_records} audit record(s) for {agent_id}.",
            data={"summary": asdict(summary)},
        )

    def _admin_policy(self) -> CommandResult:
        policy = self.admin_policy.current_policy()
        return CommandResult(
            command="/admin-policy",
            status="ok",
            output="Admin policy loaded.",
            data={"policy": policy},
        )

    def _admin_check(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = argument_text.split()
        if len(parts) != 2:
            return CommandResult(
                command="/admin-check",
                status="error",
                output="Usage: /admin-check <action> <agent_id>",
            )
        action, agent_id = parts[0], parts[1].lower()
        try:
            decision = self.provisioning.admin.check_admin_action(action, agent_id, context)
        except Exception as exc:
            direct_decision = self.admin_policy.check(context, action, agent_id)
            return CommandResult(
                command="/admin-check",
                status="error",
                output=str(exc),
                data={"decision": direct_decision.to_dict()},
            )
        return CommandResult(
            command="/admin-check",
            status="ok",
            output=f"Admin action {action} is allowed for {agent_id}.",
            data={"decision": decision.to_dict() if decision else {"allowed": True}},
        )

    def _admin_action_requests(self) -> CommandResult:
        requests = [asdict(item) for item in self.provisioning.admin.list_admin_action_requests()]
        return CommandResult(
            command="/admin-action-requests",
            status="ok",
            output=f"{len(requests)} admin action request(s).",
            data={"requests": requests},
        )

    def _admin_action_request(self, argument_text: str) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/admin-action-request",
                status="error",
                output="Usage: /admin-action-request <id>",
            )
        request = self.provisioning.admin.get_admin_action_request(request_id)
        return CommandResult(
            command="/admin-action-request",
            status="ok",
            output=f"Admin action request {request.id}: {request.status}.",
            data={"request": asdict(request)},
        )

    def _request_admin_action(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        parts = argument_text.split()
        if len(parts) < 2:
            return CommandResult(
                command="/request-admin-action",
                status="error",
                output="Usage: /request-admin-action <action> <agent_id>",
            )
        request = self.provisioning.admin.request_admin_action(
            action=parts[0],
            agent_id=parts[1].lower(),
            actor_agent_id=context.actor_id,
            context=context,
        )
        return CommandResult(
            command="/request-admin-action",
            status="ok",
            output=f"Requested approval for {request.action} on {request.agent_id}.",
            data={"request": asdict(request)},
        )

    def _approve_admin_action(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/approve-admin-action",
                status="error",
                output="Usage: /approve-admin-action <id>",
            )
        request = self.provisioning.admin.approve_admin_action_request(request_id, context)
        return CommandResult(
            command="/approve-admin-action",
            status="ok",
            output=f"Approved admin action request {request_id}.",
            data={"request": asdict(request)},
        )

    def _reject_admin_action(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/reject-admin-action",
                status="error",
                output="Usage: /reject-admin-action <id>",
            )
        request = self.provisioning.admin.reject_admin_action_request(request_id, context)
        return CommandResult(
            command="/reject-admin-action",
            status="ok",
            output=f"Rejected admin action request {request_id}.",
            data={"request": asdict(request)},
        )

    def _apply_admin_action(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/apply-admin-action",
                status="error",
                output="Usage: /apply-admin-action <id>",
            )
        result = self.provisioning.admin.apply_admin_action_request(request_id, context)
        return CommandResult(
            command="/apply-admin-action",
            status="ok",
            output=f"Applied admin action request {request_id}.",
            data={"result": asdict(result)},
        )

    def _admin_request_cleanup(self, argument_text: str) -> CommandResult:
        dry_run = "--apply" not in argument_text.split()
        result = self.provisioning.admin.cleanup_admin_action_requests(dry_run=dry_run)
        mode = "dry-run" if result.dry_run else "applied"
        return CommandResult(
            command="/admin-request-cleanup",
            status="ok",
            output=(
                f"Admin request cleanup {mode}: "
                f"{result.deleted} deleted, {len(result.candidates)} candidate(s)."
            ),
            data={"cleanup": asdict(result)},
        )

    def _admin_request_retention(self) -> CommandResult:
        status = self.provisioning.admin.admin_action_request_retention_status()
        return CommandResult(
            command="/admin-request-retention",
            status="ok",
            output=f"{status['total_requests']} admin action request(s).",
            data={"retention": status},
        )

    def _decision_check(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = argument_text.split()
        if len(parts) < 2:
            return CommandResult(
                command="/decision-check",
                status="error",
                output="Usage: /decision-check <category> <action>",
            )
        category, action = parts[0], parts[1]
        target_agent_id = (
            context.actor_id if context.actor_type == "agent" else self._default_agent_id()
        )
        request = DecisionRequest(
            category=category,
            action=action,
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            capability_id=action if category == "capability" else None,
            target_agent_id=target_agent_id,
        )
        result = self.decisions.evaluate(request)
        status = "ok" if result.allowed else "error"
        return CommandResult(
            command="/decision-check",
            status=status,
            output=_decision_summary(result),
            data={"decision": result.to_dict()},
        )

    def _retention(self) -> CommandResult:
        status = self.retention.retention_status()
        return CommandResult(
            command="/retention",
            status="ok",
            output=f"{status.total_domains} retention domain(s).",
            data={"retention": asdict(status)},
        )

    def _retention_domain(self, argument_text: str) -> CommandResult:
        domain_id = argument_text.strip()
        if not domain_id:
            return CommandResult(
                command="/retention-domain",
                status="error",
                output="Usage: /retention-domain <domain_id>",
            )
        domain = self.retention.get_domain(domain_id)
        return CommandResult(
            command="/retention-domain",
            status="ok",
            output=f"Retention domain {domain.domain_id}.",
            data={"domain": asdict(domain)},
        )

    def _create_agent(self, argument_text: str) -> CommandResult:
        try:
            parts = shlex.split(argument_text)
        except ValueError as exc:
            return CommandResult(command="/create-agent", status="error", output=str(exc))
        if len(parts) < 3:
            return CommandResult(
                command="/create-agent",
                status="error",
                output='Usage: /create-agent <agent_id> "<display_name>" "<role>"',
            )
        result = self.provisioning.create_agent(
            AgentCreateRequest(
                agent_id=parts[0],
                display_name=parts[1],
                role=parts[2],
                autonomy_level="manual",
            )
        )
        return CommandResult(
            command="/create-agent",
            status="ok",
            output=f"Created agent {result.agent_id}.",
            data={"provisioning": asdict(result)},
        )

    def _preview_agent(self, argument_text: str) -> CommandResult:
        try:
            parts = shlex.split(argument_text)
        except ValueError as exc:
            return CommandResult(command="/preview-agent", status="error", output=str(exc))
        if len(parts) < 3:
            return CommandResult(
                command="/preview-agent",
                status="error",
                output='Usage: /preview-agent <agent_id> "<display_name>" "<role>"',
            )
        result = self.provisioning.create_agent(
            AgentCreateRequest(
                agent_id=parts[0],
                display_name=parts[1],
                role=parts[2],
                autonomy_level="manual",
                dry_run=True,
            )
        )
        return CommandResult(
            command="/preview-agent",
            status="ok",
            output=f"Provisioning preview for {result.agent_id}.",
            data={"provisioning": asdict(result)},
        )

    def _validate_agent(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/validate-agent",
                status="error",
                output="Usage: /validate-agent <agent_id>",
            )
        result = self.provisioning.validate_agent_files(agent_id)
        return CommandResult(
            command="/validate-agent",
            status="ok" if result.valid else "error",
            output=f"Agent {agent_id} validation {'passed' if result.valid else 'failed'}.",
            data={"validation": asdict(result)},
        )

    def _agent_provisioning_status(self) -> CommandResult:
        status = self.provisioning.get_agent_provisioning_status()
        return CommandResult(
            command="/agent-provisioning-status",
            status="ok",
            output=f"{status['total_agents']} agent(s).",
            data={"provisioning": status},
        )

    def _agent_provisioning_policy(self) -> CommandResult:
        policy = self.provisioning.current_policy()
        return CommandResult(
            command="/agent-provisioning-policy",
            status="ok",
            output="Agent provisioning policy loaded.",
            data={"policy": policy},
        )

    def _agent_provisioning_requests(self) -> CommandResult:
        requests = [asdict(item) for item in self.provisioning.list_provisioning_requests()]
        return CommandResult(
            command="/agent-provisioning-requests",
            status="ok",
            output=f"{len(requests)} provisioning request(s).",
            data={"requests": requests},
        )

    def _agent_provisioning_request(self, argument_text: str) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/agent-provisioning-request",
                status="error",
                output="Usage: /agent-provisioning-request <id>",
            )
        request = self.provisioning.get_provisioning_request(request_id)
        return CommandResult(
            command="/agent-provisioning-request",
            status="ok",
            output=f"Provisioning request {request.id}: {request.status}.",
            data={"request": asdict(request)},
        )

    def _approve_agent_provisioning(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/approve-agent-provisioning",
                status="error",
                output="Usage: /approve-agent-provisioning <id>",
            )
        request = self.provisioning.approve_provisioning_request(context, request_id)
        return CommandResult(
            command="/approve-agent-provisioning",
            status="ok",
            output=f"Approved provisioning request {request.id}. Apply separately.",
            data={"request": asdict(request)},
        )

    def _reject_agent_provisioning(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/reject-agent-provisioning",
                status="error",
                output="Usage: /reject-agent-provisioning <id>",
            )
        request = self.provisioning.reject_provisioning_request(context, request_id)
        return CommandResult(
            command="/reject-agent-provisioning",
            status="ok",
            output=f"Rejected provisioning request {request.id}.",
            data={"request": asdict(request)},
        )

    def _apply_agent_provisioning(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        request_id = argument_text.strip()
        if not request_id:
            return CommandResult(
                command="/apply-agent-provisioning",
                status="error",
                output="Usage: /apply-agent-provisioning <id>",
            )
        result = self.provisioning.apply_approved_provisioning_request(context, request_id)
        return CommandResult(
            command="/apply-agent-provisioning",
            status="ok",
            output=f"Applied provisioning request {request_id}.",
            data={"provisioning": asdict(result)},
        )

    def _default_agent_id(self) -> str:
        agent_id = self.services.default_agent_id()
        if not agent_id:
            raise ValidationError("No default agent is configured.")
        return str(agent_id)
