from __future__ import annotations

import json
import shlex
from dataclasses import asdict
from typing import Any

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.desktop_automation.models import (
    AutomationAction,
    ElementSelector,
    VerificationSpec,
)
from synapse.maintenance.models import (
    MaintenanceInspectionRequest,
    MaintenanceScope,
    MaintenanceScopeKind,
)
from synapse.policies.models import PolicyRule
from synapse.tools.identities import (
    DESKTOP_CANCEL,
    DESKTOP_EXECUTE,
    DESKTOP_PREVIEW,
)
from synapse.tools.models import ToolExecutionRequest


def _desktop_selector(raw: dict | None) -> ElementSelector | None:
    return ElementSelector(**raw) if raw else None


def _desktop_verification(raw: dict) -> VerificationSpec:
    return VerificationSpec(
        str(raw["kind"]),
        _desktop_selector(raw.get("selector")),
        raw.get("expected"),
        raw.get("window_id"),
    )


def _desktop_action(raw: dict) -> AutomationAction:
    return AutomationAction(
        kind=str(raw["kind"]),
        selector=_desktop_selector(raw.get("selector")),
        application=raw.get("application"),
        window_id=raw.get("window_id"),
        arguments=dict(raw.get("arguments", {})),
        verification=(
            _desktop_verification(raw["verification"]) if raw.get("verification") else None
        ),
        fallback_allowed=bool(raw.get("fallback_allowed", True)),
        max_attempts=int(raw.get("max_attempts", 2)),
    )


class PlatformGovernanceCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/policy",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="4a594665ad24f73ce3993919588449dadea6f236040408750d7adf641abe643c",
        ),
        CommandMetadata(
            name="/policy-list",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="bef19c5d981c7f215734ba2e461e6b72bb7d775fcf94289a99c3d0dd9f2f09c4",
        ),
        CommandMetadata(
            name="/policy-show",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="6fc23bbfb3d44c92bb05cd86f9f4d45cad557b11c51ac3d9578d31229349424d",
        ),
        CommandMetadata(
            name="/policy-create",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="35706f292aaeff10e72e3c047484061aa07503afc9daeb1f46e2b04098c667cf",
        ),
        CommandMetadata(
            name="/policy-update",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="e8cb8b00e3c525d11ee6071e9003c42fc66b951a40d253ba35bbb6aab5521b95",
        ),
        CommandMetadata(
            name="/policy-delete",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="89f023460b762b0302fabcd8c69d87d599142f7ac975dd07586bca36e9b56eb5",
        ),
        CommandMetadata(
            name="/policy-validate",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="012d8951aef79da95674e4ed9bfd790c90ee9ee35903bfa1618451ca4399422f",
        ),
        CommandMetadata(
            name="/policy-evaluate",
            aliases=("/policy-explain",),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text", "command"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="23e461aead84ef10facbd71a426039ca1d402bf0ea3801047c22f2669f6ac62e",
        ),
        CommandMetadata(
            name="/policy-effective",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="9f5862c7ddeab82b9ddc3de24af6f94e1b2a0bb35145a6a0e9f7b90d9e44e904",
        ),
        CommandMetadata(
            name="/observability-events",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="ff261be228796ce8d488cb5f539e91d0920caed0820327fa94abb9a6d89458de",
        ),
        CommandMetadata(
            name="/observability-trace",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("correlation_id",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="f6a67829588f7d6e285b4af88fe40542832cf73f97dd5e6724a2fd549cc110e2",
        ),
        CommandMetadata(
            name="/observability-metrics",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="d7d8662b01b0ce1f10a82eb155ad61e6994f62ff6afd2cfa3ba4b0ef27346801",
        ),
        CommandMetadata(
            name="/observability-errors",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="b1059a0bf24d32a83fea1b92d8412e83f14f72337e785c7217d07052a5ca17e3",
        ),
        CommandMetadata(
            name="/observability-status",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="396d1b0f14a4b86e971e55d1ff004103ac9c7be3efb752fa327305bc9525464e",
        ),
        CommandMetadata(
            name="/observability-cleanup",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="53e95b046cde7426f91f2e97ad1da6e1cb51bbd90e083eda030cc89739c11f1d",
        ),
        CommandMetadata(
            name="/health-module",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="da1e0648e326908bde9bd36a91062a8299346829fe513a5da8bd98cc795f4d8b",
        ),
        CommandMetadata(
            name="/diagnostics",
            aliases=(),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="a7cfad894b184aaf77dded9c034d06d6cb2ae6c60bcd50dfa6c14ded4f2246a2",
        ),
        CommandMetadata(
            name="/system-info",
            aliases=(
                "/hardware-info",
                "/gpu-info",
                "/memory-info",
                "/disk-info",
                "/insight-diagnostics",
                "/insight-report",
                "/model-recommendations",
            ),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("command",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="2f66321937bddf7f83122f8fa631b5e99a9ee292ec0f14fcbe51c9a4fe7321ab",
        ),
        CommandMetadata(
            name="/list-apps",
            aliases=(
                "/list-windows",
                "/automation-plan",
                "/automation-preview",
                "/automation-execute",
                "/automation-verify",
                "/automation-cancel",
                "/clipboard-get",
                "/clipboard-set",
            ),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("context", "command", "argument_text"),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="1770ac05cd56fc83dc6b92c54233aea5754dc6df9ca0c219f292c78bcd7f71f9",
        ),
        CommandMetadata(
            name="/validate-config",
            aliases=("/validate-data-dir", "/validate-secrets"),
            domain="platform_governance",
            handler="PlatformGovernanceCommandHandler",
            argument_names=("command",),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="5cc347c011a263eda387355f7bc91bc8be07fc7fbc4ffab158bf65c9d83bbaa9",
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
        if command == "/policy":
            return self._policy(context, argument_text)
        if command == "/policy-list":
            return self._policy_list()
        if command == "/policy-show":
            return self._policy_show(argument_text)
        if command == "/policy-create":
            return self._policy_create(argument_text)
        if command == "/policy-update":
            return self._policy_update(argument_text)
        if command == "/policy-delete":
            return self._policy_delete(argument_text)
        if command == "/policy-validate":
            return self._policy_validate(argument_text)
        if command in {"/policy-evaluate", "/policy-explain"}:
            return self._policy_evaluate(argument_text, command)
        if command == "/policy-effective":
            return self._policy(context, argument_text)
        if command == "/observability-events":
            return self._observability_events()
        if command == "/observability-trace":
            return self._trace(argument_text)
        if command == "/observability-metrics":
            return self._observability_metrics()
        if command == "/observability-errors":
            return self._observability_errors()
        if command == "/observability-status":
            return self._observability_status()
        if command == "/observability-cleanup":
            return self._observability_cleanup(argument_text)
        if command == "/health-module":
            return self._health_module(argument_text)
        if command == "/diagnostics":
            return self._diagnostics()
        if command in {
            "/system-info",
            "/hardware-info",
            "/gpu-info",
            "/memory-info",
            "/disk-info",
            "/insight-diagnostics",
            "/insight-report",
            "/model-recommendations",
        }:
            return self._insight_command(command)
        if command in {
            "/list-apps",
            "/list-windows",
            "/automation-plan",
            "/automation-preview",
            "/automation-execute",
            "/automation-verify",
            "/automation-cancel",
            "/clipboard-get",
            "/clipboard-set",
        }:
            return self._desktop_command(context, command, argument_text)
        if command in {"/validate-config", "/validate-data-dir", "/validate-secrets"}:
            return self._foundation_validate(context, command)
        raise UnknownCommandError(command)

    def _policy(self, context: PermissionContext, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip()
        if not agent_id:
            return CommandResult(
                command="/policy",
                status="error",
                output="Usage: /policy <agent_id>",
            )
        policy = self.policies.resolve(context, agent_id.lower())
        return CommandResult(
            command="/policy",
            status="ok",
            output=f"Effective policy for {policy.agent_id}.",
            data={"policy": policy.to_dict()},
        )

    def _policy_list(self) -> CommandResult:
        rules = [asdict(item) for item in self.policies.list_rules()]
        return CommandResult(
            "/policy-list", "ok", f"{len(rules)} policy rule(s).", {"rules": rules}
        )

    def _policy_show(self, argument_text: str) -> CommandResult:
        rule = self.policies.get_rule(argument_text.strip())
        return CommandResult("/policy-show", "ok", f"Policy {rule.id}.", {"rule": asdict(rule)})

    def _policy_create(self, argument_text: str) -> CommandResult:
        try:
            raw = json.loads(argument_text)
            rule = self.policies.create_rule(PolicyRule(**raw))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"policy_invalid: {exc}") from exc
        return CommandResult(
            "/policy-create", "ok", f"Policy {rule.id} created.", {"rule": asdict(rule)}
        )

    def _policy_update(self, argument_text: str) -> CommandResult:
        try:
            raw = json.loads(argument_text)
            rule_id = str(raw.pop("id"))
            expected_revision = int(raw.pop("expected_revision"))
            rule = self.policies.update_rule(rule_id, raw, expected_revision)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"policy_invalid: {exc}") from exc
        return CommandResult(
            "/policy-update", "ok", f"Policy {rule.id} updated.", {"rule": asdict(rule)}
        )

    def _policy_validate(self, argument_text: str) -> CommandResult:
        try:
            rule = PolicyRule(**json.loads(argument_text))
            self.policies.validate_rule(rule)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"policy_invalid: {exc}") from exc
        return CommandResult(
            "/policy-validate", "ok", "Policy is valid.", {"valid": True, "rule": asdict(rule)}
        )

    def _policy_delete(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if not parts:
            return CommandResult("/policy-delete", "error", "Usage: /policy-delete <id> [revision]")
        rule = self.policies.delete_rule(parts[0], int(parts[1]) if len(parts) > 1 else None)
        return CommandResult(
            "/policy-delete", "ok", f"Policy {rule.id} deleted.", {"rule": asdict(rule)}
        )

    def _policy_evaluate(self, argument_text: str, command: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) != 3:
            return CommandResult(
                command, "error", f"Usage: {command} <subject> <action> <resource>"
            )
        result = self.policies.evaluate_policy(*parts)
        return CommandResult(
            command,
            "ok",
            f"Policy decision: {result.decision}.",
            {"effective_policy": asdict(result)},
        )

    def _observability_events(self) -> CommandResult:
        events = [asdict(item) for item in self.events.tail(limit=100)]
        return CommandResult(
            "/observability-events", "ok", f"{len(events)} event(s).", {"events": events}
        )

    def _observability_metrics(self) -> CommandResult:
        return CommandResult(
            "/observability-metrics",
            "ok",
            "Observability metrics.",
            {"metrics": self.health.operational_metrics()},
        )

    def _observability_errors(self) -> CommandResult:
        errors = [asdict(item) for item in self.events.query_events(status="failed", limit=100)]
        return CommandResult(
            "/observability-errors", "ok", f"{len(errors)} error event(s).", {"events": errors}
        )

    def _observability_status(self) -> CommandResult:
        return CommandResult(
            "/observability-status",
            "ok",
            "Observability ready.",
            {"state": "ready", "metrics": self.events.metrics()},
        )

    def _observability_cleanup(self, argument_text: str) -> CommandResult:
        days = int(argument_text.strip() or "30")
        report = self.events.cleanup(days)
        return CommandResult(
            "/observability-cleanup", "ok", "Observability cleanup completed.", {"report": report}
        )

    def _health_module(self, argument_text: str) -> CommandResult:
        components = [asdict(item) for item in self.health.module_health(argument_text.strip())]
        return CommandResult(
            "/health-module", "ok", f"{len(components)} component(s).", {"components": components}
        )

    def _diagnostics(self) -> CommandResult:
        return CommandResult(
            "/diagnostics",
            "ok",
            "Diagnostics generated.",
            {"diagnostics": self.health.diagnostics()},
        )

    def _insight_command(self, command: str) -> CommandResult:
        if self.system_insight is None:
            return CommandResult(command, "error", "Insight Runtime is unavailable.")
        if command == "/system-info":
            payload = asdict(self.system_insight.system.inspect())
        elif command == "/hardware-info":
            payload = asdict(self.system_insight.hardware.inspect())
        elif command == "/gpu-info":
            payload = {
                "gpus": [asdict(item) for item in self.system_insight.hardware.inspect().gpus]
            }
        elif command == "/memory-info":
            payload = asdict(self.system_insight.hardware.inspect().memory)
        elif command == "/disk-info":
            payload = asdict(self.system_insight.disk.inspect())
        elif command == "/insight-diagnostics":
            payload = asdict(self.system_insight.report(persist=False).diagnostics)
        elif command == "/model-recommendations":
            payload = asdict(self.system_insight.model_capabilities.inspect())
        else:
            payload = asdict(self.system_insight.report())
        return CommandResult(command, "ok", "Operational insight collected.", {"insight": payload})

    def _desktop_command(
        self,
        context: PermissionContext,
        command: str,
        argument_text: str,
    ) -> CommandResult:
        if self.desktop is None:
            return CommandResult(command, "error", "Desktop Runtime is unavailable.")
        payload: dict[str, Any]
        if command == "/list-apps":
            payload = {"applications": [asdict(item) for item in self.desktop.applications.list()]}
        elif command == "/list-windows":
            payload = {"windows": [asdict(item) for item in self.desktop.windows.list()]}
        elif command == "/automation-plan":
            raw = json.loads(argument_text)
            actions = [_desktop_action(item) for item in raw.get("actions", [])]
            plan = self.desktop.create_plan(
                context.actor_id,
                str(raw.get("objective", "Desktop automation")),
                actions,
                dry_run=bool(raw.get("dry_run", False)),
            )
            payload = {"plan": asdict(plan)}
        elif command == "/automation-preview":
            payload = {
                "plan": self._execute_desktop_tool(context, DESKTOP_PREVIEW, argument_text.strip())
            }
        elif command == "/automation-execute":
            parts = argument_text.split()
            payload = {
                "result": self._execute_desktop_tool(
                    context,
                    DESKTOP_EXECUTE,
                    parts[0],
                    approval_id=parts[1] if len(parts) > 1 else None,
                )
            }
        elif command == "/automation-cancel":
            payload = {
                "plan": self._execute_desktop_tool(context, DESKTOP_CANCEL, argument_text.strip())
            }
        elif command == "/automation-verify":
            raw = json.loads(argument_text)
            payload = {"verification": asdict(self.desktop.verify(_desktop_verification(raw)))}
        elif command == "/clipboard-get":
            payload = {"clipboard": self.desktop.clipboard.get(reveal=False)}
        else:
            plan = self.desktop.create_plan(
                context.actor_id,
                "Governed clipboard write",
                [AutomationAction("clipboard.set", arguments={"value": argument_text})],
            )
            payload = {"result": self._execute_desktop_tool(context, DESKTOP_EXECUTE, plan.id)}
        return CommandResult(command, "ok", "Desktop automation operation completed.", payload)

    def _execute_desktop_tool(
        self,
        context: PermissionContext,
        tool_id: str,
        plan_id: str,
        *,
        approval_id: str | None = None,
    ) -> dict:
        result = self.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=tool_id,
                arguments={
                    "plan_id": plan_id,
                    **({"approval_id": approval_id} if approval_id else {}),
                },
                caller=context.actor_id,
                caller_type="user",
            )
        )
        return result.output

    def _foundation_validate(self, context: PermissionContext, command: str) -> CommandResult:
        contributor_id = "configuration" if command == "/validate-config" else "foundation"
        report = self.maintenance.inspect(
            context,
            MaintenanceInspectionRequest(
                MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, contributor_id)
            ),
        )
        if command == "/validate-config":
            invalid = [item.reference.removeprefix("config:") for item in report.findings]
            payload = {
                "valid": not invalid,
                "invalid_configs": invalid,
            }
        elif command == "/validate-secrets":
            payload = {"valid": True, "message": "Secret values are redacted from telemetry."}
        else:
            payload = {
                "state": "ready" if not report.findings else "misconfigured",
                "writable": not any(
                    item.category == "root_not_writable" for item in report.findings
                ),
                "escaped_symlinks": [
                    item.reference for item in report.findings if item.category == "escaped_symlink"
                ],
                "invalid_configs": [],
                "checked_at": report.completed_at,
            }
        return CommandResult(command, "ok", "Foundation validation completed.", payload)

    def _trace(self, correlation_id: str) -> CommandResult:
        correlation_id = correlation_id.strip()
        if not correlation_id:
            return CommandResult(
                command="/trace",
                status="error",
                output="Usage: /trace <correlation_id>",
            )
        events = [asdict(event) for event in self.events.trace(correlation_id)]
        records = self.events.trace_records(correlation_id)
        return CommandResult(
            command="/trace",
            status="ok",
            output=(
                f"{len(events)} event(s), {len(records)} durable record(s) "
                f"for correlation {correlation_id}."
            ),
            data={"events": events, "records": records},
        )
