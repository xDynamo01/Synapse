from __future__ import annotations

import json
import shlex
from dataclasses import asdict
from typing import Any

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressRequest,
    InformationAsset,
    InformationOwnership,
    OperatingProfile,
    ProcessingBoundary,
    ProcessingPurpose,
    ProviderTrustProfile,
    TrainingUsePolicy,
    TrustProfileStatus,
)

_HASH = "c5f1aac98ef54ef115dfa9f9d86a283ba2e982f22032c263465a188f5b410d0a"
_NAMES = (
    "intelligence-boundary-status",
    "intelligence-profile-show",
    "intelligence-profile-set",
    "information-asset-show",
    "information-asset-classify",
    "information-asset-reclassify",
    "egress-preview",
    "egress-decision-show",
    "egress-manifest-show",
    "egress-history",
    "provider-trust-list",
    "provider-trust-show",
    "provider-trust-register",
    "provider-trust-update",
    "intelligence-unclassified-list",
    "intelligence-unguarded-paths",
)


class IntelligenceBoundaryCommandHandler(BaseCommandHandler):
    metadata = tuple(
        CommandMetadata(
            name=f"/{name}",
            aliases=(),
            domain="intelligence_boundary",
            handler="IntelligenceBoundaryCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="intelligence-boundary",
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
        runtime = self.intelligence_boundary
        try:
            if command == "/intelligence-boundary-status":
                return self._ok(command, runtime.status())
            if command == "/intelligence-profile-show":
                return self._ok(command, {"profile": runtime.operating_profile().value})
            if command == "/intelligence-profile-set":
                self._admin(context)
                self._require(args, "<profile>")
                profile = runtime.set_operating_profile(
                    OperatingProfile(args[0]), actor_id=context.permission.actor_id
                )
                return self._ok(command, {"profile": profile})
            if command == "/information-asset-show":
                self._require(args, "<asset_id>")
                return self._ok(command, asdict(runtime.get_asset(args[0])))
            if command == "/information-asset-classify":
                self._admin(context)
                raw = self._json(invocation.argument_text)
                return self._ok(command, asdict(runtime.register_asset(self._asset(raw))))
            if command == "/information-asset-reclassify":
                self._admin(context)
                raw = self._json(invocation.argument_text)
                item = runtime.reclassify_asset(
                    raw["asset_id"],
                    DataClassification(raw["classification"]),
                    actor_id=context.permission.actor_id,
                    justification=raw["justification"],
                    approval_id=raw.get("approval_id"),
                    redaction_validated=bool(raw.get("redaction_validated", False)),
                )
                return self._ok(command, asdict(item))
            if command == "/egress-preview":
                raw = self._json(invocation.argument_text)
                return self._ok(command, asdict(runtime.preview_egress(self._egress(raw))))
            if command == "/egress-decision-show":
                self._require(args, "<decision_id>")
                return self._ok(command, asdict(runtime.get_decision(args[0])))
            if command == "/egress-manifest-show":
                self._require(args, "<manifest_id>")
                return self._ok(command, asdict(runtime.get_manifest(args[0])))
            if command == "/egress-history":
                return self._ok(
                    command, {"records": [asdict(item) for item in runtime.ledger_history()]}
                )
            if command == "/provider-trust-list":
                return self._ok(
                    command,
                    {"profiles": [asdict(item) for item in runtime.list_trust_profiles()]},
                )
            if command == "/provider-trust-show":
                self._require(args, "<trust_profile_id>")
                return self._ok(command, asdict(runtime.get_trust_profile(args[0])))
            if command == "/provider-trust-register":
                self._admin(context)
                raw = self._json(invocation.argument_text)
                return self._ok(
                    command, asdict(runtime.register_trust_profile(self._trust(raw)))
                )
            if command == "/provider-trust-update":
                self._admin(context)
                raw = self._json(invocation.argument_text)
                item = runtime.update_trust_profile(
                    raw["trust_profile_id"], dict(raw.get("changes") or {})
                )
                return self._ok(command, asdict(item))
            if command == "/intelligence-unclassified-list":
                self._admin(context)
                return self._ok(
                    command,
                    {"assets": [asdict(item) for item in runtime.list_assets(unclassified=True)]},
                )
            if command == "/intelligence-unguarded-paths":
                self._admin(context)
                status = runtime.status()
                return self._ok(command, {"paths": status["unguarded_paths"]})
        except Exception as exc:
            return CommandResult(
                command,
                "error",
                str(exc),
                {"error_code": getattr(exc, "code", type(exc).__name__)},
            )
        raise UnknownCommandError(command)

    @staticmethod
    def _asset(raw: dict[str, Any]) -> InformationAsset:
        return InformationAsset(
            asset_id=raw["asset_id"],
            owner=InformationOwnership(raw["owner"]),
            source_domain=raw["source_domain"],
            source_reference=raw["source_reference"],
            content_type=raw["content_type"],
            classification=DataClassification(raw["classification"]),
            categories=tuple(raw["categories"]),
            project_id=raw.get("project_id"),
            workspace_id=raw.get("workspace_id"),
            processing_constraints=tuple(raw.get("processing_constraints", ())),
            retention_policy=raw.get("retention_policy", "inherit"),
            training_use_policy=TrainingUsePolicy(
                raw.get("training_use_policy", "prohibited")
            ),
            external_processing_policy=raw.get(
                "external_processing_policy", "policy-controlled"
            ),
            provenance=dict(raw.get("provenance") or {}),
            parent_asset_ids=tuple(raw.get("parent_asset_ids", ())),
            content_handle=raw.get("content_handle"),
            metadata=dict(raw.get("metadata") or {}),
        )

    @staticmethod
    def _egress(raw: dict[str, Any]) -> EgressRequest:
        return EgressRequest(
            asset_ids=tuple(raw["asset_ids"]),
            requester=raw["requester"],
            destination=raw["destination"],
            boundary=ProcessingBoundary(raw["boundary"]),
            purpose=ProcessingPurpose(raw["purpose"]),
            provider_id=raw.get("provider_id"),
            project_id=raw.get("project_id"),
            rfc_id=raw.get("rfc_id"),
            rfc_revision=raw.get("rfc_revision"),
            mission_id=raw.get("mission_id"),
            task_id=raw.get("task_id"),
            requested_transformations=tuple(raw.get("requested_transformations", ())),
            payload_checksum=raw.get("payload_checksum", ""),
            estimated_size=int(raw.get("estimated_size", 0)),
            estimated_tokens=int(raw.get("estimated_tokens", 0)),
            correlation_id=raw.get("correlation_id", ""),
            constraints=tuple(raw.get("constraints", ())),
        )

    @staticmethod
    def _trust(raw: dict[str, Any]) -> ProviderTrustProfile:
        return ProviderTrustProfile(
            trust_profile_id=raw["trust_profile_id"],
            provider_id=raw["provider_id"],
            processing_boundary=ProcessingBoundary(raw["processing_boundary"]),
            organization_controlled=bool(raw.get("organization_controlled", False)),
            tenant_isolated=bool(raw.get("tenant_isolated", False)),
            declared_retention=raw.get("declared_retention", "unknown"),
            declared_training_use=raw.get("declared_training_use", "unknown"),
            contractual_controls=tuple(raw.get("contractual_controls", ())),
            supported_classifications=tuple(
                DataClassification(item) for item in raw.get("supported_classifications", ())
            ),
            blocked_classifications=tuple(
                DataClassification(item) for item in raw.get("blocked_classifications", ())
            ),
            requires_redaction=bool(raw.get("requires_redaction", False)),
            allowed_categories=tuple(raw.get("allowed_categories", ())),
            blocked_categories=tuple(raw.get("blocked_categories", ())),
            verification_level=raw.get(
                "verification_level", "user-configured-assumption"
            ),
            reviewed_at=raw.get("reviewed_at", ""),
            expires_at=raw.get("expires_at"),
            status=TrustProfileStatus(raw.get("status", "draft")),
            provenance=dict(raw.get("provenance") or {}),
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
    def _require(args: list[str], usage: str) -> None:
        if not args:
            raise ValueError(f"Usage: {usage}")

    @staticmethod
    def _admin(context: CommandContext) -> None:
        if context.permission.actor_type not in {"admin", "system"}:
            raise PermissionError("Administrative context required")
