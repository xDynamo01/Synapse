from __future__ import annotations

import json
import shlex
from dataclasses import asdict
from typing import Any

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.project_governance.models import (
    AcceptanceCriterion,
    ChangeClass,
    ProjectManifest,
    ReviewDecision,
    ReviewRole,
    RFCGateRequest,
    RFCManifest,
    RFCReview,
    RFCStatus,
)

_HASH = "79470464ca007d34bdb625e687ca11b039f60144410937d08b831c31a607f031"
_NAMES = (
    "project-list",
    "project-show",
    "project-register",
    "project-update",
    "project-archive",
    "project-context",
    "rfc-list",
    "rfc-show",
    "rfc-create",
    "rfc-revise",
    "rfc-validate",
    "rfc-review",
    "rfc-approve",
    "rfc-reject",
    "rfc-supersede",
    "rfc-gate",
    "implementation-plan-list",
    "implementation-plan-show",
    "implementation-plan-validate",
    "evidence-list",
    "evidence-show",
    "acceptance-status",
)


class ProjectGovernanceCommandHandler(BaseCommandHandler):
    metadata = tuple(
        CommandMetadata(
            name=f"/{name}",
            aliases=(),
            domain="project_governance",
            handler="ProjectGovernanceCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="project-governance",
            status="active",
            source_sha256=_HASH,
        )
        for name in _NAMES
    )

    @property
    def operation_names(self) -> tuple[str, ...]:
        return ()

    def execute(self, context: CommandContext, invocation: CommandInvocation) -> CommandResult:
        command = invocation.command_name
        args = shlex.split(invocation.argument_text)
        runtime = self.project_governance
        actor = context.permission.actor_id
        try:
            if command == "/project-list":
                return self._ok(command, {"projects": [asdict(x) for x in runtime.projects.list()]})
            if command == "/project-show":
                self._require(args, "<project_id>")
                return self._ok(command, asdict(runtime.projects.get(args[0])))
            if command == "/project-register":
                self._admin(context)
                raw = self._json(invocation.argument_text)
                item = ProjectManifest(
                    raw["project_id"],
                    raw["name"],
                    raw["description"],
                    raw["root_reference"],
                    raw["owner"],
                    raw["default_policy_id"],
                    primary_agent_id=raw.get("primary_agent_id"),
                    allowed_provider_profiles=tuple(raw.get("allowed_provider_profiles", ())),
                    classification_policy=dict(raw.get("classification_policy") or {}),
                    rfc_policy=dict(raw.get("rfc_policy") or {}),
                    quality_gate_policy=dict(raw.get("quality_gate_policy") or {}),
                    skill_scope=dict(raw.get("skill_scope") or {}),
                    metadata=dict(raw.get("metadata") or {}),
                )
                return self._ok(command, asdict(runtime.projects.register(item, actor_id=actor)))
            if command == "/project-update":
                self._admin(context)
                self._require(args, "<project_id> <json>", 2)
                updates = json.loads(" ".join(args[1:]))
                return self._ok(
                    command, asdict(runtime.projects.update(args[0], updates, actor_id=actor))
                )
            if command == "/project-archive":
                self._admin(context)
                self._require(args, "<project_id>")
                return self._ok(command, asdict(runtime.projects.archive(args[0], actor_id=actor)))
            if command == "/project-context":
                self._require(args, "<project_id>")
                return self._ok(command, asdict(runtime.read_project_context(args[0])))
            if command == "/rfc-list":
                self._require(args, "<project_id>")
                return self._ok(command, {"rfcs": [asdict(x) for x in runtime.rfcs.list(args[0])]})
            if command == "/rfc-show":
                self._require(args, "<project_id> <rfc_id>", 2)
                return self._ok(command, asdict(runtime.rfcs.get(args[0], args[1])))
            if command == "/rfc-create":
                raw = self._json(invocation.argument_text)
                rfc_manifest = self._rfc(raw)
                created = runtime.rfcs.create(
                    rfc_manifest, str(raw["markdown"]), actor_id=actor
                )
                return self._ok(command, asdict(created))
            if command == "/rfc-revise":
                raw = self._json(invocation.argument_text)
                item = runtime.rfcs.revise(
                    raw["project_id"],
                    raw["rfc_id"],
                    raw["markdown"],
                    actor_id=actor,
                    change_summary=raw["change_summary"],
                    updates=dict(raw.get("updates") or {}),
                )
                return self._ok(command, asdict(item))
            if command == "/rfc-validate":
                self._require(args, "<project_id> <rfc_id>", 2)
                return self._ok(command, asdict(runtime.validation.validate(args[0], args[1])))
            if command in {"/rfc-review", "/rfc-approve", "/rfc-reject"}:
                raw = self._json(invocation.argument_text)
                review = self._review(runtime, raw)
                if command == "/rfc-review":
                    result: Any = runtime.reviews.record(review)
                elif command == "/rfc-approve":
                    result = runtime.reviews.approve(review)
                else:
                    result = runtime.reviews.reject(review)
                return self._ok(command, asdict(result))
            if command == "/rfc-supersede":
                self._admin(context)
                self._require(args, "<project_id> <rfc_id> <replacement_rfc_id>", 3)
                runtime.rfcs.get(args[0], args[2])
                item = runtime.rfcs.transition(
                    args[0],
                    args[1],
                    RFCStatus.SUPERSEDED,
                    actor_id=actor,
                    extra={"superseded_by": args[2]},
                )
                return self._ok(command, asdict(item))
            if command == "/rfc-gate":
                raw = self._json(invocation.argument_text)
                decision = runtime.evaluate_gate(
                    RFCGateRequest(
                        raw["project_id"],
                        raw["requested_change"],
                        tuple(raw.get("domains", ())),
                        tuple(raw.get("contracts", ())),
                        raw.get("mission_id"),
                        tuple(raw.get("skill_ids", ())),
                        raw.get("plan_reference"),
                        actor,
                        raw.get("correlation_id"),
                        raw.get("rfc_id"),
                        raw.get("rfc_revision"),
                        raw.get("rfc_checksum"),
                        dict(raw.get("impact") or {}),
                    )
                )
                return self._ok(command, asdict(decision))
            if command == "/implementation-plan-list":
                self._require(args, "<project_id>")
                return self._ok(
                    command, {"plans": [asdict(x) for x in runtime.plans.list(args[0])]}
                )
            if command in {"/implementation-plan-show", "/implementation-plan-validate"}:
                self._require(args, "<plan_id>")
                item = (
                    runtime.plans.validate(args[0])
                    if command.endswith("validate")
                    else runtime.plans.get(args[0])
                )
                return self._ok(command, asdict(item))
            if command == "/evidence-list":
                self._require(args, "<project_id>")
                return self._ok(
                    command, {"evidence": [asdict(x) for x in runtime.evidence.list(args[0])]}
                )
            if command == "/evidence-show":
                self._require(args, "<evidence_id>")
                return self._ok(command, runtime.evidence.store.get(args[0]))
            if command == "/acceptance-status":
                self._require(args, "<plan_id>")
                plan = runtime.plans.get(args[0])
                return self._ok(
                    command, {"criteria": [asdict(x) for x in plan.acceptance_criteria]}
                )
        except Exception as exc:
            return CommandResult(
                command,
                "error",
                str(exc),
                {"error_code": getattr(exc, "code", type(exc).__name__)},
            )
        raise UnknownCommandError(command)

    @staticmethod
    def _rfc(raw: dict[str, Any]) -> RFCManifest:
        criteria = tuple(
            AcceptanceCriterion(
                item["criterion_id"],
                item["description"],
                item["type"],
                item["verification_method"],
                bool(item.get("required", True)),
                tuple(item.get("evidence_types", ())),
            )
            for item in raw.get("acceptance_criteria", ())
        )
        return RFCManifest(
            raw["rfc_id"],
            raw["project_id"],
            raw["title"],
            tuple(raw["authors"]),
            tuple(raw["reviewers"]),
            tuple(raw["affected_domains"]),
            tuple(raw["affected_contracts"]),
            ChangeClass(raw["change_classification"]),
            risk_level=raw.get("risk_level", "medium"),
            acceptance_criteria=criteria,
            invariants=tuple(raw.get("invariants", ())),
            out_of_scope=tuple(raw.get("out_of_scope", ())),
        )

    @staticmethod
    def _review(runtime: Any, raw: dict[str, Any]) -> RFCReview:
        current = runtime.rfcs.get(raw["project_id"], raw["rfc_id"])
        return RFCReview(
            raw["project_id"],
            raw["rfc_id"],
            current.revision,
            raw["reviewer_id"],
            raw["reviewer_type"],
            ReviewRole(raw["role"]),
            ReviewDecision(raw["decision"]),
            raw["comment"],
            raw["reference_type"],
            raw["reference_id"],
        )

    @staticmethod
    def _json(text: str) -> dict[str, Any]:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Command payload must be a JSON object")
        return value

    @staticmethod
    def _ok(command: str, data: dict[str, Any]) -> CommandResult:
        return CommandResult(command, "ok", json.dumps(data, default=str, sort_keys=True), data)

    @staticmethod
    def _require(args: list[str], usage: str, count: int = 1) -> None:
        if len(args) < count:
            raise ValueError(f"Usage: {usage}")

    @staticmethod
    def _admin(context: CommandContext) -> None:
        if context.permission.actor_type not in {"admin", "system"}:
            raise PermissionError("Administrative context required")
