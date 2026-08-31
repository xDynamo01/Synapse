from __future__ import annotations

import json
import shlex
from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.skills.models import SkillAssignment, SkillResolutionRequest, SkillScope

_HASH = "e253d8187af4777d1886226f674202cfe95790c17e16cca7c7d21697a16decd6"
_NAMES = (
    "skill-list",
    "skill-show",
    "skill-versions",
    "skill-resolve",
    "skill-inspect",
    "skill-validate",
    "skill-install",
    "skill-enable",
    "skill-disable",
    "skill-uninstall",
    "skill-assign",
    "skill-unassign",
    "skill-agent-list",
    "skill-lease-list",
    "skill-status",
    "skill-conflicts",
)


class SkillsCommandHandler(BaseCommandHandler):
    metadata = tuple(
        CommandMetadata(
            name=f"/{name}",
            aliases=(),
            domain="skills",
            handler="SkillsCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="skills",
            status="active",
            source_sha256=_HASH,
        )
        for name in _NAMES
    )

    def execute(self, context: CommandContext, invocation: CommandInvocation) -> CommandResult:
        command = invocation.command_name
        args = shlex.split(invocation.argument_text)
        try:
            if command == "/skill-list":
                items = [asdict(item) for item in self.skills.list(" ".join(args))]
                return self._ok(command, {"skills": items})
            if command == "/skill-show":
                self._require(args, "<skill_id> [version]")
                package = self.skills.get(args[0], args[1] if len(args) > 1 else None)
                return self._ok(
                    command, {"manifest": asdict(package.manifest), "checksum": package.checksum}
                )
            if command == "/skill-versions":
                self._require(args, "<skill_id>")
                return self._ok(command, {"versions": self.skills.versions(args[0])})
            if command == "/skill-resolve":
                self._require(args, "<objective or skill IDs>")
                result = self.skills.resolve(SkillResolutionRequest(" ".join(args)))
                return self._ok(command, asdict(result))
            if command in {"/skill-inspect", "/skill-validate", "/skill-install"}:
                self._admin(context)
                self._require(args, "<package_ref>")
                if command == "/skill-inspect":
                    package = self.skills.inspect(args[0])
                    data = {"manifest": asdict(package.manifest), "checksum": package.checksum}
                elif command == "/skill-validate":
                    data = self.skills.validate(args[0])
                else:
                    package = self.skills.install(args[0], actor_id=context.permission.actor_id)
                    data = {"manifest": asdict(package.manifest), "checksum": package.checksum}
                return self._ok(command, data)
            if command in {"/skill-enable", "/skill-disable"}:
                self._admin(context)
                self._require(args, "<skill_id> <version>", 2)
                status = "active" if command.endswith("enable") else "disabled"
                return self._ok(
                    command,
                    {"manifest": asdict(self.skills.set_status(args[0], args[1], status).manifest)},
                )
            if command == "/skill-uninstall":
                self._admin(context)
                self._require(args, "<skill_id> <version>", 2)
                self.skills.uninstall(args[0], args[1])
                return self._ok(command, {"uninstalled": True})
            if command == "/skill-assign":
                self._admin(context)
                self._require(args, "<agent_id> <skill_id> <version_constraint>", 3)
                item = SkillAssignment(
                    args[0],
                    args[1],
                    args[2],
                    SkillScope.AGENT,
                    assigned_by=context.permission.actor_id,
                )
                return self._ok(command, asdict(self.skills.assign(item)))
            if command == "/skill-unassign":
                self._admin(context)
                self._require(args, "<assignment_id>")
                self.skills.unassign(args[0])
                return self._ok(command, {"unassigned": True})
            if command == "/skill-agent-list":
                self._require(args, "<agent_id>")
                return self._ok(command, {"assignments": self.skills.assignment_summaries(args[0])})
            if command == "/skill-lease-list":
                return self._ok(
                    command, {"leases": self.skills.list_leases(args[0] if args else None)}
                )
            if command == "/skill-status":
                return self._ok(command, self.skills.status())
            if command == "/skill-conflicts":
                items = [
                    {
                        "skill_id": p.manifest.skill_id,
                        "conflicts": [asdict(x) for x in p.manifest.conflicts],
                    }
                    for p in self.skills.registry.packages()
                    if p.manifest.conflicts
                ]
                return self._ok(command, {"conflicts": items})
        except Exception as exc:
            return CommandResult(
                command, "error", str(exc), {"error_code": getattr(exc, "code", type(exc).__name__)}
            )
        raise UnknownCommandError(command)

    @staticmethod
    def _ok(command: str, data: dict) -> CommandResult:
        return CommandResult(command, "ok", json.dumps(data, default=str, sort_keys=True), data)

    @staticmethod
    def _require(args: list[str], usage: str, count: int = 1) -> None:
        if len(args) < count:
            raise ValueError(f"Usage: {usage}")

    @staticmethod
    def _admin(context: CommandContext) -> None:
        if context.permission.actor_type not in {"admin", "system"}:
            raise PermissionError("Administrative context required")
