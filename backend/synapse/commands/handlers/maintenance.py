from __future__ import annotations

import shlex
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.exceptions import ValidationError
from synapse.maintenance.models import (
    MaintenanceExecutionRequest,
    MaintenanceInspectionRequest,
    MaintenancePlanRequest,
    MaintenanceScope,
    MaintenanceScopeKind,
)


def _metadata(name: str) -> CommandMetadata:
    return CommandMetadata(
        name=name,
        aliases=(),
        domain="maintenance",
        handler="MaintenanceCommandHandler",
        argument_names=("argument_text",),
        defaults=(),
        category="operational",
        status="active",
        source_sha256="data-maintenance-v1",
    )


class MaintenanceCommandHandler(BaseCommandHandler):
    metadata = tuple(
        _metadata(name)
        for name in (
            "/maintenance-status",
            "/maintenance-inspect",
            "/maintenance-plan",
            "/maintenance-plan-show",
            "/maintenance-execute",
            "/maintenance-cancel",
            "/maintenance-history",
            "/maintenance-contributors",
        )
    )

    def execute(
        self, command_context: CommandContext, invocation: CommandInvocation
    ) -> CommandResult:
        command = invocation.command_name
        argument = invocation.argument_text.strip()
        context = command_context.permission
        correlation_id = invocation.correlation_id
        data: dict[str, Any]
        if command == "/maintenance-status":
            self.permissions.require(context, "maintenance.admin")
            data = asdict(self.maintenance.status())
        elif command == "/maintenance-contributors":
            self.permissions.require(context, "maintenance.admin")
            data = {"contributors": [asdict(item) for item in self.maintenance.list_contributors()]}
        elif command == "/maintenance-inspect":
            inspection_request = MaintenanceInspectionRequest(
                scope=_parse_scope(argument),
                correlation_id=correlation_id or str(uuid4()),
            )
            data = asdict(self.maintenance.inspect(context, inspection_request))
        elif command == "/maintenance-plan":
            plan_request = _parse_plan(argument, correlation_id)
            data = asdict(self.maintenance.create_plan(context, plan_request))
        elif command == "/maintenance-plan-show":
            if not argument:
                return self._maintenance_usage(command, f"{command} <plan_id>")
            self.permissions.require(context, "maintenance.admin")
            data = asdict(self.maintenance.get_plan(argument))
        elif command == "/maintenance-execute":
            parts = shlex.split(argument)
            if len(parts) not in {4, 5} or parts[3].lower() != "confirm":
                return self._maintenance_usage(
                    command,
                    f"{command} <plan_id> <checksum> <revision> confirm [approval_id]",
                )
            execution_request = MaintenanceExecutionRequest(
                plan_id=parts[0],
                checksum=parts[1],
                expected_revision=int(parts[2]),
                confirmed=True,
                approval_id=parts[4] if len(parts) == 5 else None,
                correlation_id=correlation_id or str(uuid4()),
            )
            data = asdict(self.maintenance.execute(context, execution_request))
        elif command == "/maintenance-cancel":
            parts = shlex.split(argument)
            if len(parts) != 2:
                return self._maintenance_usage(command, f"{command} <plan_id> <revision>")
            data = asdict(self.maintenance.cancel(context, parts[0], int(parts[1])))
        elif command == "/maintenance-history":
            self.permissions.require(context, "maintenance.admin")
            limit = int(argument or "100")
            data = {"history": [asdict(item) for item in self.maintenance.history(limit)]}
        else:
            raise UnknownCommandError(command)
        return CommandResult(
            command=command,
            status="ok",
            output=f"{command} completed.",
            data=data,
        )

    @staticmethod
    def _maintenance_usage(command: str, usage: str) -> CommandResult:
        return CommandResult(command, "error", f"Usage: {usage}")


def _parse_scope(argument: str) -> MaintenanceScope:
    token = argument.strip() or "all"
    if token == "all":
        return MaintenanceScope()
    if "=" not in token:
        raise ValidationError(
            "Scope must be all or kind=value using a registered maintenance scope"
        )
    kind, value = token.split("=", 1)
    if any(part in value for part in ("/", "\\", "..")):
        raise ValidationError("Maintenance scopes cannot contain path syntax")
    try:
        return MaintenanceScope(MaintenanceScopeKind(kind), value)
    except ValueError as exc:
        raise ValidationError(f"Invalid maintenance scope: {kind}") from exc


def _parse_plan(argument: str, correlation_id: str | None) -> MaintenancePlanRequest:
    scope = MaintenanceScope()
    hours = 24
    expires = 1800
    dry_run = True
    for token in shlex.split(argument):
        if token == "--apply":
            dry_run = False
        elif token.startswith("hours="):
            hours = int(token.removeprefix("hours="))
        elif token.startswith("expires="):
            expires = int(token.removeprefix("expires="))
        elif token == "all" or "=" in token:
            scope = _parse_scope(token)
        else:
            raise ValidationError(f"Unknown maintenance plan option: {token}")
    return MaintenancePlanRequest(
        scope=scope,
        older_than_hours=hours,
        expires_in_seconds=expires,
        dry_run=dry_run,
        correlation_id=correlation_id or str(uuid4()),
    )
