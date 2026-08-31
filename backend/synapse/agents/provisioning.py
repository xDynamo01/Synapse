from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from synapse.agents.admin import AgentAdminRuntime
from synapse.agents.audit import AgentAuditRuntime
from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.provisioning_policy import (
    AgentProvisioningPolicyRuntime,
    AgentProvisioningRiskDecision,
)
from synapse.agents.registry import AgentRegistry
from synapse.approvals.manager import ApprovalManager
from synapse.capabilities.registry import CapabilityRegistry
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.observability.correlation import current_correlation_fields

SAFE_AGENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
PROVISIONING_STATUSES = {
    "draft",
    "awaiting_approval",
    "approved",
    "rejected",
    "cancelled",
    "applied",
    "failed",
    "expired",
}


class AgentProvisioningError(ValidationError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


@dataclass(frozen=True)
class AgentCreateRequest:
    agent_id: str
    display_name: str
    role: str
    description: str = ""
    focus_areas: list[str] = field(default_factory=list)
    communication_style: str = "concise"
    autonomy_level: str = "manual"
    default_model: str | None = None
    default_provider: str | None = None
    system_prompt: str | None = None
    soul_content: str | None = None
    skills_content: str | None = None
    capabilities_allow: list[str] = field(default_factory=list)
    capabilities_deny: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    operational_rules: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    initial_memory: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    overwrite: bool = False
    can_delegate: bool = False
    dry_run: bool = False
    agent_kind: str = "persistent"


@dataclass(frozen=True)
class AgentUpdateRequest:
    display_name: str | None = None
    role: str | None = None
    description: str | None = None
    focus_areas: list[str] | None = None
    communication_style: str | None = None
    autonomy_level: str | None = None
    default_model: str | None = None
    default_provider: str | None = None
    system_prompt: str | None = None
    soul_content: str | None = None
    skills_content: str | None = None
    capabilities_allow: list[str] | None = None
    capabilities_deny: list[str] | None = None
    preferred_tools: list[str] | None = None
    forbidden_tools: list[str] | None = None
    permissions: list[str] | None = None
    operational_rules: list[str] | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentValidationResult:
    agent_id: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentProvisionResult:
    agent_id: str
    created: bool
    updated: bool = False
    status: str = "applied"
    provisioning_request_id: str | None = None
    approval_id: str | None = None
    files: list[str] = field(default_factory=list)
    validation: AgentValidationResult | None = None
    dry_run: bool = False
    preview: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentProvisioningRequest:
    agent_id: str
    action: str
    payload: dict[str, Any]
    risk_level: str
    risk_reasons: list[str]
    configuration_hash: str
    risk_decision: dict[str, Any] = field(default_factory=dict)
    status: str = "draft"
    approval_id: str | None = None
    schema_version: int = 1
    record_type: str = "agent_provisioning_request"
    correlation_id: str | None = None
    causation_id: str | None = None
    parent_id: str | None = None
    source: str | None = None
    requester_id: str | None = None
    requester_type: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class AgentProvisioningStatus:
    total_requests: int
    pending_requests: int
    requests: list[dict[str, Any]]


class AgentProvisioningRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        capabilities: CapabilityRegistry,
        event_bus: EventBus,
        approvals: ApprovalManager | None = None,
        policy: AgentProvisioningPolicyRuntime | None = None,
        admin: AgentAdminRuntime | None = None,
        audit: AgentAuditRuntime | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.capabilities = capabilities
        self.event_bus = event_bus
        self.approvals = approvals
        self.policy = policy or AgentProvisioningPolicyRuntime(data_dir, capabilities)
        self.admin = admin
        self.audit = audit

    def validate_create_request(self, request: AgentCreateRequest) -> AgentValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        agent_id = request.agent_id.strip().lower()
        if not SAFE_AGENT_ID.match(agent_id):
            errors.append("agent_id must use lowercase letters, numbers, underscore, or hyphen")
        if ".." in request.agent_id or "/" in request.agent_id or "\\" in request.agent_id:
            errors.append("agent_id cannot contain path traversal")
        if not request.display_name.strip():
            errors.append("display_name is required")
        if not request.role.strip():
            errors.append("role is required")
        if not isinstance(request.can_delegate, bool):
            errors.append("can_delegate must be boolean")
        if not isinstance(request.dry_run, bool):
            errors.append("dry_run must be boolean")
        if request.agent_kind != "persistent":
            errors.append("AgentProvisioning creates persistent agents only")
        if request.autonomy_level not in {"manual", "assisted", "autonomous"}:
            errors.append("autonomy_level must be manual, assisted, or autonomous")
        if request.autonomy_level != "manual":
            warnings.append("new agents should start with conservative manual autonomy")
        self._validate_capability_ids(request.capabilities_allow, errors)
        self._validate_capability_ids(request.capabilities_deny, errors)
        for capability_id in request.capabilities_allow:
            capability = self._capability_or_none(capability_id)
            if capability and capability.risk_level in {"high", "critical"}:
                warnings.append(
                    f"capability {capability_id} is {capability.risk_level} risk "
                    "and remains subject to approval policy"
                )
        result = AgentValidationResult(
            agent_id=agent_id,
            valid=not errors,
            errors=errors,
            warnings=warnings,
        )
        self.event_bus.emit("agent.provisioning.validated", "agent_provisioning", asdict(result))
        return result

    def create_agent(
        self,
        request: AgentCreateRequest,
        context: PermissionContext | None = None,
    ) -> AgentProvisionResult:
        validation = self.validate_create_request(request)
        if not validation.valid:
            self.event_bus.emit("agent.validation.failed", "agent_provisioning", asdict(validation))
            self._audit(
                validation.agent_id,
                "agent.provisioning.failed",
                "failed",
                reason="; ".join(validation.errors),
                details=asdict(validation),
            )
            code = (
                "invalid_agent_id"
                if any("agent_id" in error for error in validation.errors)
                else "invalid_request"
            )
            raise AgentProvisioningError(code, "; ".join(validation.errors))
        risk = self._risk_for_create(request)
        if not risk.allowed:
            self.event_bus.emit(
                "agent.provisioning.failed",
                validation.agent_id,
                {"blocked_reasons": risk.blocked_reasons},
            )
            self._audit(
                validation.agent_id,
                "agent.provisioning.failed",
                "blocked",
                reason="; ".join(risk.blocked_reasons),
                details=risk.to_dict(),
            )
            raise AgentProvisioningError(
                "invalid_request",
                "; ".join(risk.blocked_reasons),
                risk.to_dict(),
            )
        if request.dry_run:
            return self._dry_run_result(request, validation, risk)
        if risk.requires_approval:
            pending = self.request_create_agent(request, context=context, risk=risk)
            return AgentProvisionResult(
                agent_id=pending.agent_id,
                created=False,
                status=pending.status,
                provisioning_request_id=pending.id,
                approval_id=pending.approval_id,
                validation=validation,
            )

        return self._create_agent_direct(request, validation=validation)

    def update_agent(
        self,
        agent_id: str,
        request: AgentUpdateRequest,
        context: PermissionContext | None = None,
    ) -> AgentProvisionResult:
        safe_id = self._safe_existing_agent_id(agent_id)
        config_path = self.data_dir.resolve(f"agents/{safe_id}/CONFIG.yaml")
        if not config_path.exists():
            raise NotFound(f"Agent not found: {safe_id}")
        risk = self._risk_for_update(request)
        if not risk.allowed:
            self.event_bus.emit(
                "agent.provisioning.failed",
                safe_id,
                {"blocked_reasons": risk.blocked_reasons},
            )
            self._audit(
                safe_id,
                "agent.provisioning.failed",
                "blocked",
                reason="; ".join(risk.blocked_reasons),
                details=risk.to_dict(),
            )
            raise AgentProvisioningError(
                "invalid_request",
                "; ".join(risk.blocked_reasons),
                risk.to_dict(),
            )
        if risk.requires_approval:
            pending = self._request_update_agent(safe_id, request, context=context, risk=risk)
            return AgentProvisionResult(
                agent_id=safe_id,
                created=False,
                updated=False,
                status=pending.status,
                provisioning_request_id=pending.id,
                approval_id=pending.approval_id,
            )

        raw = load_structured_file(config_path)
        result = self._apply_update_to_agent(safe_id, raw, request)
        self.event_bus.emit("agent.updated", safe_id, asdict(result))
        self._audit(safe_id, "agent.updated", "success", details=asdict(result))
        return result

    def request_create_agent(
        self,
        request: AgentCreateRequest,
        context: PermissionContext | None = None,
        risk: AgentProvisioningRiskDecision | None = None,
    ) -> AgentProvisioningRequest:
        validation = self.validate_create_request(request)
        if not validation.valid:
            self.event_bus.emit("agent.validation.failed", "agent_provisioning", asdict(validation))
            raise AgentProvisioningError("invalid_request", "; ".join(validation.errors))
        risk = risk or self._risk_for_create(request)
        if not risk.allowed:
            raise AgentProvisioningError("invalid_request", "; ".join(risk.blocked_reasons))
        if not risk.requires_approval:
            raise AgentProvisioningError(
                "approval_not_required",
                "Agent create request does not require approval",
            )
        payload = asdict(request)
        configuration_hash = self._configuration_hash(payload)
        requester_id = context.actor_id if context else "agent_provisioning"
        for existing in self.list_provisioning_requests():
            if (
                existing.agent_id == validation.agent_id
                and existing.action == "create"
                and existing.status in {"awaiting_approval", "approved"}
                and existing.configuration_hash == configuration_hash
                and existing.requester_id == requester_id
            ):
                return existing
        pending = AgentProvisioningRequest(
            agent_id=validation.agent_id,
            action="create",
            payload=payload,
            risk_level=risk.risk_level,
            risk_reasons=list(risk.reasons),
            configuration_hash=configuration_hash,
            risk_decision=risk.to_dict(),
            status="awaiting_approval",
            requester_id=requester_id,
            requester_type=context.actor_type if context else "system",
            **current_correlation_fields(),
        )
        approval = self._create_approval_request(pending, context)
        pending = self._transition_request(pending, "awaiting_approval", approval_id=approval.id)
        self.event_bus.emit("agent.provisioning.requested", pending.agent_id, asdict(pending))
        self.event_bus.emit(
            "agent.provisioning.awaiting_approval", pending.agent_id, asdict(pending)
        )
        self._audit(
            pending.agent_id,
            "agent.provisioning.requested",
            "success",
            reason="approval required",
            details=asdict(pending),
        )
        return pending

    def approve_provisioning_request(
        self,
        context: PermissionContext,
        request_id: str,
    ) -> AgentProvisioningRequest:
        request = self.get_provisioning_request(request_id)
        if request.status != "awaiting_approval":
            raise AgentProvisioningError(
                self._approval_state_code(request.status),
                f"Provisioning request is not awaiting approval: {request_id}",
            )
        if not request.approval_id:
            raise AgentProvisioningError(
                "approval_required",
                f"Provisioning request has no approval: {request_id}",
            )
        self._validate_approval_binding(request)
        self._require_approvals().approve(context, request.approval_id)
        updated = self._transition_request(request, "approved")
        self.event_bus.emit("agent.provisioning.approved", context.actor_id, asdict(updated))
        self._audit(
            updated.agent_id,
            "agent.provisioning.approved",
            "success",
            actor_agent_id=context.actor_id,
            actor_type=context.actor_type,
            details=asdict(updated),
        )
        return updated

    def reject_provisioning_request(
        self,
        context: PermissionContext,
        request_id: str,
    ) -> AgentProvisioningRequest:
        request = self.get_provisioning_request(request_id)
        if request.status != "awaiting_approval":
            raise AgentProvisioningError(
                self._approval_state_code(request.status),
                f"Provisioning request is not awaiting approval: {request_id}",
            )
        if not request.approval_id:
            raise AgentProvisioningError(
                "approval_required",
                f"Provisioning request has no approval: {request_id}",
            )
        self._validate_approval_binding(request)
        self._require_approvals().reject(context, request.approval_id)
        updated = self._transition_request(request, "rejected")
        self.event_bus.emit("agent.provisioning.rejected", context.actor_id, asdict(updated))
        self._audit(
            updated.agent_id,
            "agent.provisioning.rejected",
            "success",
            actor_agent_id=context.actor_id,
            actor_type=context.actor_type,
            details=asdict(updated),
        )
        return updated

    def apply_approved_provisioning_request(
        self,
        context: PermissionContext,
        request_id: str,
    ) -> AgentProvisionResult:
        request = self.get_provisioning_request(request_id)
        if request.status == "applied":
            raise AgentProvisioningError(
                "duplicate_application",
                f"Provisioning request already applied: {request_id}",
            )
        if request.status != "approved":
            raise AgentProvisioningError(
                self._approval_state_code(request.status),
                f"Provisioning request is not approved: {request_id}",
            )
        self._validate_approval_binding(request, expected_status="approved")
        try:
            if request.action == "create":
                create_request = AgentCreateRequest(**request.payload)
                result = self._create_agent_direct(create_request)
            elif request.action == "update":
                update_request = AgentUpdateRequest(**request.payload)
                raw = load_structured_file(
                    self.data_dir.resolve(f"agents/{request.agent_id}/CONFIG.yaml")
                )
                result = self._apply_update_to_agent(request.agent_id, raw, update_request)
            else:
                raise AgentProvisioningError(
                    "provisioning_failed",
                    f"Unknown provisioning action: {request.action}",
                )
            self._transition_request(request, "applied")
            self.event_bus.emit("agent.provisioning.applied", context.actor_id, asdict(result))
            self._audit(
                request.agent_id,
                "agent.provisioning.applied",
                "success",
                actor_agent_id=context.actor_id,
                actor_type=context.actor_type,
                details=asdict(result),
            )
            return result
        except Exception as exc:
            failed = self._transition_request(request, "failed")
            self.event_bus.emit(
                "agent.provisioning.failed",
                context.actor_id,
                {**asdict(failed), "error": str(exc) or type(exc).__name__},
            )
            self._audit(
                request.agent_id,
                "agent.provisioning.failed",
                "failed",
                actor_agent_id=context.actor_id,
                actor_type=context.actor_type,
                reason=str(exc) or type(exc).__name__,
                details=asdict(failed),
            )
            raise

    def list_provisioning_requests(self) -> list[AgentProvisioningRequest]:
        return [self._read_request(path) for path in sorted(self._requests_root().glob("*.yaml"))]

    def get_provisioning_request(self, request_id: str) -> AgentProvisioningRequest:
        path = self._request_path(request_id)
        if not path.exists():
            raise NotFound(f"Agent provisioning request not found: {request_id}")
        return self._read_request(path)

    def validate_agent_files(self, agent_id: str) -> AgentValidationResult:
        safe_id = self._safe_existing_agent_id(agent_id)
        errors: list[str] = []
        warnings: list[str] = []
        for filename in ("CONFIG.yaml", "SOUL.md", "SKILLS.md", "MEMORY.md"):
            path = self.data_dir.resolve(f"agents/{safe_id}/{filename}")
            if not path.exists():
                errors.append(f"missing {filename}")
        config = load_structured_file(self.data_dir.resolve(f"agents/{safe_id}/CONFIG.yaml"))
        if config:
            if config.get("record_type") != "agent_config":
                warnings.append("CONFIG.yaml has no agent_config record_type")
            if not config.get("schema_version"):
                warnings.append("CONFIG.yaml has no schema_version")
            capabilities = config.get("capabilities", {})
            if isinstance(capabilities, dict):
                self._validate_capability_ids(capabilities.get("allow", []), errors)
                self._validate_capability_ids(capabilities.get("deny", []), errors)
        result = AgentValidationResult(
            agent_id=safe_id,
            valid=not errors,
            errors=errors,
            warnings=warnings,
        )
        if not result.valid:
            self.event_bus.emit("agent.validation.failed", safe_id, asdict(result))
        return result

    def get_agent_provisioning_status(self) -> dict[str, Any]:
        agents = []
        for path in sorted(self.data_dir.resolve("agents").iterdir()):
            if not path.is_dir():
                continue
            config = load_structured_file(path / "CONFIG.yaml")
            agents.append(
                {
                    "agent_id": path.name,
                    "provisioned": config.get("record_type") == "agent_config",
                    "schema_version": config.get("schema_version"),
                }
            )
        requests = self.list_provisioning_requests()
        status = AgentProvisioningStatus(
            total_requests=len(requests),
            pending_requests=len([item for item in requests if item.status == "awaiting_approval"]),
            requests=[asdict(item) for item in requests],
        )
        return {"agents": agents, "total_agents": len(agents), "provisioning": asdict(status)}

    def _validate_capability_ids(self, capability_ids: list[str], errors: list[str]) -> None:
        for capability_id in capability_ids:
            if not self._capability_or_none(str(capability_id)):
                errors.append(f"unknown capability: {capability_id}")

    def _capability_or_none(self, capability_id: str):
        try:
            return self.capabilities.get(capability_id)
        except NotFound:
            return None

    def _config_payload(
        self,
        request: AgentCreateRequest,
        agent_id: str,
        updated_at: str,
        created_at: str,
    ) -> dict[str, Any]:
        permissions = self._permissions_for_capabilities(request.capabilities_allow)
        permissions.update(request.permissions)
        return {
            "schema_version": 1,
            "record_type": "agent_config",
            "agent_kind": request.agent_kind,
            "created_at": created_at,
            "updated_at": updated_at,
            "id": agent_id,
            "name": request.display_name,
            "role": request.role,
            "description": request.description,
            "preferred_model": self._preferred_model(
                request.default_provider,
                request.default_model,
            ),
            "default_model": request.default_model,
            "default_provider": request.default_provider,
            "system_prompt": request.system_prompt,
            "autonomy": request.autonomy_level or "manual",
            "autonomy_profile": request.autonomy_level or "manual",
            "can_delegate": request.can_delegate,
            "focus_areas": list(request.focus_areas),
            "preferred_tools": list(request.preferred_tools),
            "allowed_tools": list(request.preferred_tools),
            "forbidden_tools": list(request.forbidden_tools),
            "communication_style": request.communication_style or "concise",
            "operational_rules": list(request.operational_rules),
            "tags": list(request.tags),
            "skills": list(request.focus_areas),
            "permissions": sorted(permissions),
            "capabilities": {
                "allow": list(request.capabilities_allow),
                "deny": list(request.capabilities_deny),
            },
            "metadata": dict(request.metadata),
        }

    def _create_agent_direct(
        self,
        request: AgentCreateRequest,
        validation: AgentValidationResult | None = None,
    ) -> AgentProvisionResult:
        validation = validation or self.validate_create_request(request)
        if not validation.valid:
            raise AgentProvisioningError("invalid_request", "; ".join(validation.errors))
        agent_id = validation.agent_id
        config_path = self.data_dir.resolve(f"agents/{agent_id}/CONFIG.yaml")
        if config_path.exists() and not request.overwrite:
            raise AgentProvisioningError(
                "duplicate_agent_id",
                f"Agent already exists: {agent_id}",
            )
        started_payload = {
            "agent_id": agent_id,
            "overwrite": request.overwrite,
        }
        self.event_bus.emit("agent.provisioning.started", agent_id, started_payload)
        now = datetime.now(UTC).isoformat()
        config = self._config_payload(request, agent_id, now, created_at=now)
        try:
            files = self._write_agent_files(
                agent_id=agent_id,
                config=config,
                soul=self._soul_markdown(request),
                skills=self._skills_markdown(request),
                memory=request.initial_memory or f"# {request.display_name} Memory\n\n",
                overwrite=request.overwrite,
            )
        except AgentProvisioningError:
            raise
        except Exception as exc:
            raise AgentProvisioningError(
                "provisioning_failed",
                f"Agent provisioning failed: {agent_id}",
            ) from exc
        result = AgentProvisionResult(
            agent_id=agent_id,
            created=True,
            status="applied",
            files=files,
            validation=validation,
        )
        self.event_bus.emit("agent.created", agent_id, asdict(result))
        self.event_bus.emit("agent.provisioning.completed", agent_id, asdict(result))
        self._audit(agent_id, "agent.created", "success", details=asdict(result))
        return result

    def _dry_run_result(
        self,
        request: AgentCreateRequest,
        validation: AgentValidationResult,
        risk: AgentProvisioningRiskDecision,
    ) -> AgentProvisionResult:
        agent_id = validation.agent_id
        config = self._config_payload(
            request,
            agent_id,
            updated_at="<generated>",
            created_at="<generated>",
        )
        preview = {
            "config": config,
            "files": self._agent_files(agent_id),
            "permissions": config["permissions"],
            "tools": {
                "allowed": config["allowed_tools"],
                "forbidden": config["forbidden_tools"],
            },
            "capabilities": config["capabilities"],
            "risk": risk.to_dict(),
            "requires_approval": risk.requires_approval,
            "conflicts": ["agent already exists"]
            if self.data_dir.resolve(f"agents/{agent_id}/CONFIG.yaml").exists()
            else [],
            "validations": asdict(validation),
            "destination": f"agents/{agent_id}",
        }
        result = AgentProvisionResult(
            agent_id=agent_id,
            created=False,
            status="dry_run",
            validation=validation,
            dry_run=True,
            preview=preview,
        )
        self.event_bus.emit("agent.provisioning.previewed", agent_id, asdict(result))
        return result

    def _permissions_for_capabilities(self, capability_ids: list[str]) -> set[str]:
        permissions: set[str] = set()
        for capability_id in capability_ids:
            capability = self._capability_or_none(capability_id)
            if capability:
                permissions.update(capability.required_permissions)
        return permissions

    def _write_agent_files(
        self,
        agent_id: str,
        config: dict[str, Any],
        soul: str,
        skills: str,
        memory: str,
        overwrite: bool = False,
    ) -> list[str]:
        files = self._agent_files(agent_id)
        operation_id = str(uuid4())
        staging_root = self.data_dir.resolve(f"agent_provisioning_staging/{operation_id}")
        staging_data = DataDir(staging_root)
        staged_base = staging_root / "agents" / agent_id
        final_base = self.data_dir.resolve(f"agents/{agent_id}")
        backup_base = staging_root / "backup" / agent_id
        backup_created = False
        try:
            dump_structured_file(staged_base / "CONFIG.yaml", config)
            (staged_base / "SOUL.md").write_text(soul, encoding="utf-8")
            (staged_base / "SKILLS.md").write_text(skills, encoding="utf-8")
            (staged_base / "MEMORY.md").write_text(memory, encoding="utf-8")
            (staged_base / "INBOX.md").write_text("# Inbox\n", encoding="utf-8")

            AgentRegistry(staging_data).get(agent_id)
            AgentIdentityRuntime(staging_data).load_identity(agent_id)

            if final_base.exists():
                if not overwrite:
                    raise AgentProvisioningError(
                        "duplicate_agent_id",
                        f"Agent already exists: {agent_id}",
                    )
                backup_base.parent.mkdir(parents=True, exist_ok=True)
                os.replace(final_base, backup_base)
                backup_created = True
            final_base.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_base, final_base)
            if backup_created:
                shutil.rmtree(backup_base)
            return files
        except Exception as exc:
            rollback_error: Exception | None = None
            try:
                if backup_created and backup_base.exists() and not final_base.exists():
                    os.replace(backup_base, final_base)
            except Exception as restore_exc:
                rollback_error = restore_exc
            self.event_bus.emit(
                "agent.provisioning.rolled_back",
                agent_id,
                {
                    "agent_id": agent_id,
                    "error": str(exc) or type(exc).__name__,
                    "rollback_error": (
                        str(rollback_error) or type(rollback_error).__name__
                        if rollback_error
                        else None
                    ),
                },
            )
            if rollback_error:
                raise AgentProvisioningError(
                    "rollback_failed",
                    f"Agent provisioning rollback failed: {agent_id}",
                ) from rollback_error
            if isinstance(exc, AgentProvisioningError):
                raise
            code = (
                "registry_validation_failed"
                if isinstance(exc, NotFound)
                else "identity_validation_failed"
                if isinstance(exc, ValidationError)
                else "provisioning_failed"
            )
            raise AgentProvisioningError(
                code,
                f"Agent provisioning failed: {agent_id}",
            ) from exc
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root, ignore_errors=True)

    @staticmethod
    def _agent_files(agent_id: str) -> list[str]:
        return [
            f"agents/{agent_id}/CONFIG.yaml",
            f"agents/{agent_id}/SOUL.md",
            f"agents/{agent_id}/SKILLS.md",
            f"agents/{agent_id}/MEMORY.md",
            f"agents/{agent_id}/INBOX.md",
        ]

    @staticmethod
    def _soul_markdown(request: AgentCreateRequest) -> str:
        if request.soul_content is not None:
            return request.soul_content
        focus = "\n".join(f"- {item}" for item in request.focus_areas) or "- General support"
        rules = (
            "\n".join(f"- {item}" for item in request.operational_rules) or "- Respect permissions."
        )
        prompt = request.system_prompt or "Follow the configured role and operational rules."
        return (
            f"# {request.display_name}\n\n"
            f"Role: {request.role}\n\n"
            f"{request.description}\n\n"
            "## System Prompt\n\n"
            f"{prompt}\n\n"
            "## Focus Areas\n\n"
            f"{focus}\n\n"
            "## Operational Rules\n\n"
            f"{rules}\n"
        )

    @staticmethod
    def _skills_markdown(request: AgentCreateRequest) -> str:
        if request.skills_content is not None:
            return request.skills_content
        skills = request.focus_areas or ["general_support"]
        lines = "\n".join(f"- {item}" for item in skills)
        return f"# {request.display_name} Skills\n\n{lines}\n"

    def _safe_existing_agent_id(self, agent_id: str) -> str:
        safe_id = agent_id.strip().lower()
        if not SAFE_AGENT_ID.match(safe_id):
            raise AgentProvisioningError("invalid_agent_id", "Invalid agent_id")
        return safe_id

    def current_policy(self) -> dict[str, Any]:
        return self.policy.load_policy().to_dict()

    def _risk_for_create(self, request: AgentCreateRequest) -> AgentProvisioningRiskDecision:
        return self.policy.evaluate_create(
            capabilities_allow=request.capabilities_allow,
            autonomy_level=request.autonomy_level,
            preferred_tools=request.preferred_tools,
            forbidden_tools=request.forbidden_tools,
            can_delegate=request.can_delegate,
            permissions=request.permissions,
        )

    def _risk_for_update(self, request: AgentUpdateRequest) -> AgentProvisioningRiskDecision:
        return self.policy.evaluate_update(
            capabilities_allow=request.capabilities_allow or [],
            autonomy_level=request.autonomy_level,
            preferred_tools=request.preferred_tools or [],
            forbidden_tools=request.forbidden_tools or [],
            preferred_tools_were_provided=request.preferred_tools is not None,
            permissions=request.permissions or [],
        )

    def _request_update_agent(
        self,
        agent_id: str,
        request: AgentUpdateRequest,
        context: PermissionContext | None,
        risk: AgentProvisioningRiskDecision,
    ) -> AgentProvisioningRequest:
        pending = AgentProvisioningRequest(
            agent_id=agent_id,
            action="update",
            payload=asdict(request),
            risk_level=risk.risk_level,
            risk_reasons=list(risk.reasons),
            configuration_hash=self._configuration_hash(asdict(request)),
            risk_decision=risk.to_dict(),
            status="awaiting_approval",
            **current_correlation_fields(),
        )
        approval = self._create_approval_request(pending, context)
        pending = self._transition_request(pending, "awaiting_approval", approval_id=approval.id)
        self.event_bus.emit("agent.provisioning.requested", agent_id, asdict(pending))
        self.event_bus.emit("agent.provisioning.awaiting_approval", agent_id, asdict(pending))
        self._audit(
            agent_id,
            "agent.provisioning.requested",
            "success",
            reason="approval required",
            details=asdict(pending),
        )
        return pending

    def _create_approval_request(
        self,
        request: AgentProvisioningRequest,
        context: PermissionContext | None,
    ):
        context = context or PermissionContext(actor_id="agent_provisioning", actor_type="system")
        return self._require_approvals().create_request(
            context=context,
            tool_name="agent_provisioning",
            tool_args={
                "request_type": "agent_provisioning",
                "provisioning_request_id": request.id,
                "agent_id": request.agent_id,
                "action": request.action,
                "requested_capabilities": request.payload.get("capabilities_allow", []),
                "autonomy_level": request.payload.get("autonomy_level"),
                "risk_reasons": request.risk_reasons,
                "risk_decision": request.risk_decision,
                "configuration_hash": request.configuration_hash,
                "requester_id": request.requester_id,
                "requested_permissions": request.payload.get("permissions", []),
                "requested_tools": request.payload.get("preferred_tools", []),
            },
            risk_level=request.risk_level,
            reason=f"Agent provisioning requires approval: {request.agent_id}",
            tool_call_id=f"agent-provisioning:{request.id}",
        )

    def _require_approvals(self) -> ApprovalManager:
        if not self.approvals:
            raise AgentProvisioningError(
                "approval_required",
                "Agent provisioning approvals are not configured.",
            )
        return self.approvals

    def _requests_root(self):
        return self.data_dir.resolve("agent_provisioning")

    def _request_path(self, request_id: str):
        return self.data_dir.resolve(f"agent_provisioning/{request_id}.yaml")

    def _write_request(self, request: AgentProvisioningRequest) -> AgentProvisioningRequest:
        if request.status not in PROVISIONING_STATUSES:
            raise AgentProvisioningError(
                "provisioning_failed",
                f"Invalid provisioning status: {request.status}",
            )
        try:
            dump_structured_file(self._request_path(request.id), asdict(request))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise AgentProvisioningError(
                "provisioning_failed",
                f"Could not persist provisioning request: {request.id}",
            ) from exc
        return request

    def _read_request(self, path) -> AgentProvisioningRequest:
        try:
            raw = load_structured_file(path)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise AgentProvisioningError(
                "provisioning_failed",
                f"Invalid provisioning request: {path.stem}",
            ) from exc
        raw.setdefault("schema_version", 1)
        raw.setdefault("record_type", "agent_provisioning_request")
        raw.setdefault("risk_decision", {})
        raw.setdefault("configuration_hash", self._configuration_hash(raw.get("payload", {})))
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("parent_id", None)
        raw.setdefault("source", None)
        raw.setdefault("requester_id", None)
        raw.setdefault("requester_type", None)
        return AgentProvisioningRequest(**raw)

    def _transition_request(
        self,
        request: AgentProvisioningRequest,
        status: str,
        approval_id: str | None = None,
    ) -> AgentProvisioningRequest:
        updated = AgentProvisioningRequest(
            id=request.id,
            agent_id=request.agent_id,
            action=request.action,
            payload=request.payload,
            risk_level=request.risk_level,
            risk_reasons=request.risk_reasons,
            configuration_hash=request.configuration_hash,
            risk_decision=request.risk_decision,
            status=status,
            approval_id=approval_id or request.approval_id,
            schema_version=request.schema_version,
            record_type=request.record_type,
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
            parent_id=request.parent_id,
            source=request.source,
            requester_id=request.requester_id,
            requester_type=request.requester_type,
            created_at=request.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )
        return self._write_request(updated)

    def _validate_approval_binding(
        self,
        request: AgentProvisioningRequest,
        expected_status: str = "pending",
    ) -> None:
        if not request.approval_id:
            raise AgentProvisioningError(
                "approval_required",
                f"Provisioning request has no approval: {request.id}",
            )
        if self._configuration_hash(request.payload) != request.configuration_hash:
            raise AgentProvisioningError(
                "approval_mismatch",
                f"Provisioning configuration changed after approval request: {request.id}",
            )
        try:
            approval = self._require_approvals().get_status(request.approval_id)
        except NotFound as exc:
            raise AgentProvisioningError(
                "approval_required",
                f"Approval request not found: {request.approval_id}",
            ) from exc
        if approval.status == "expired":
            if request.status == "awaiting_approval":
                self._transition_request(request, "expired")
            raise AgentProvisioningError(
                "approval_expired",
                f"Approval request expired: {request.approval_id}",
            )
        if approval.status != expected_status:
            raise AgentProvisioningError(
                self._approval_state_code(approval.status),
                f"Approval request is {approval.status}: {request.approval_id}",
            )
        expected = {
            "provisioning_request_id": request.id,
            "agent_id": request.agent_id,
            "configuration_hash": request.configuration_hash,
            "requester_id": request.requester_id,
            "action": request.action,
            "requested_permissions": request.payload.get("permissions", []),
            "requested_tools": request.payload.get("preferred_tools", []),
        }
        if any(approval.tool_args.get(key) != value for key, value in expected.items()):
            raise AgentProvisioningError(
                "approval_mismatch",
                f"Approval request does not match provisioning request: {request.id}",
            )

    @staticmethod
    def _approval_state_code(status: str) -> str:
        return {
            "rejected": "approval_rejected",
            "expired": "approval_expired",
            "awaiting_approval": "approval_required",
            "pending": "approval_required",
        }.get(status, "approval_required")

    @staticmethod
    def _configuration_hash(payload: dict[str, Any]) -> str:
        normalized = dict(payload)
        normalized.pop("dry_run", None)
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _apply_update_to_agent(
        self,
        safe_id: str,
        raw: dict[str, Any],
        request: AgentUpdateRequest,
    ) -> AgentProvisionResult:
        self._apply_update(raw, request)
        raw["updated_at"] = datetime.now(UTC).isoformat()
        raw.setdefault("schema_version", 1)
        raw.setdefault("record_type", "agent_config")
        dump_structured_file(self.data_dir.resolve(f"agents/{safe_id}/CONFIG.yaml"), raw)
        if request.soul_content is not None:
            self.data_dir.resolve(f"agents/{safe_id}/SOUL.md").write_text(
                request.soul_content,
                encoding="utf-8",
            )
        elif any(
            value is not None
            for value in (
                request.display_name,
                request.role,
                request.description,
                request.system_prompt,
            )
        ):
            self.data_dir.resolve(f"agents/{safe_id}/SOUL.md").write_text(
                self._soul_from_config(raw),
                encoding="utf-8",
            )
        if request.skills_content is not None:
            self.data_dir.resolve(f"agents/{safe_id}/SKILLS.md").write_text(
                request.skills_content,
                encoding="utf-8",
            )
        return AgentProvisionResult(
            agent_id=safe_id,
            created=False,
            updated=True,
            status="applied",
            files=[f"agents/{safe_id}/CONFIG.yaml"],
            validation=self.validate_agent_files(safe_id),
        )

    def _audit(
        self,
        agent_id: str,
        action: str,
        status: str,
        actor_agent_id: str | None = None,
        actor_type: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.audit:
            append = (
                self.audit.append_record
                if self.data_dir.resolve(f"agents/{agent_id}/CONFIG.yaml").exists()
                else self.audit.append_provisioning_record
            )
            append(
                agent_id=agent_id,
                action=action,
                status=status,
                actor_agent_id=actor_agent_id,
                actor_type=actor_type or "system",
                reason=reason,
                details=details or {},
            )

    def _apply_update(self, raw: dict[str, Any], request: AgentUpdateRequest) -> None:
        mapping = {
            "display_name": "name",
            "role": "role",
            "description": "description",
            "focus_areas": "focus_areas",
            "communication_style": "communication_style",
            "default_model": "default_model",
            "default_provider": "default_provider",
            "system_prompt": "system_prompt",
            "permissions": "permissions",
            "preferred_tools": "preferred_tools",
            "forbidden_tools": "forbidden_tools",
            "operational_rules": "operational_rules",
            "tags": "tags",
            "metadata": "metadata",
        }
        payload = asdict(request)
        for request_key, config_key in mapping.items():
            if payload[request_key] is not None:
                raw[config_key] = payload[request_key]
        if request.preferred_tools is not None:
            raw["allowed_tools"] = list(request.preferred_tools)
        if request.default_model is not None or request.default_provider is not None:
            raw["preferred_model"] = self._preferred_model(
                raw.get("default_provider"),
                raw.get("default_model"),
            )
        if request.autonomy_level is not None:
            raw["autonomy"] = request.autonomy_level
            raw["autonomy_profile"] = request.autonomy_level
        if request.capabilities_allow is not None or request.capabilities_deny is not None:
            capabilities = raw.setdefault("capabilities", {})
            if request.capabilities_allow is not None:
                errors: list[str] = []
                self._validate_capability_ids(request.capabilities_allow, errors)
                if errors:
                    raise AgentProvisioningError("invalid_request", "; ".join(errors))
                capabilities["allow"] = request.capabilities_allow
            if request.capabilities_deny is not None:
                errors = []
                self._validate_capability_ids(request.capabilities_deny, errors)
                if errors:
                    raise AgentProvisioningError("invalid_request", "; ".join(errors))
                capabilities["deny"] = request.capabilities_deny
            raw["permissions"] = sorted(
                self._permissions_for_capabilities(capabilities.get("allow", []))
            )

    @staticmethod
    def _preferred_model(provider: str | None, model: str | None) -> str | None:
        if provider and model:
            return f"{provider}/{model}"
        return model or provider

    @staticmethod
    def _soul_from_config(raw: dict[str, Any]) -> str:
        prompt = raw.get("system_prompt") or "Follow the configured role and operational rules."
        focus = "\n".join(f"- {item}" for item in raw.get("focus_areas", []))
        rules = "\n".join(f"- {item}" for item in raw.get("operational_rules", []))
        return (
            f"# {raw.get('name', raw.get('id', 'Agent'))}\n\n"
            f"Role: {raw.get('role', '')}\n\n"
            f"{raw.get('description', '')}\n\n"
            "## System Prompt\n\n"
            f"{prompt}\n\n"
            "## Focus Areas\n\n"
            f"{focus or '- General support'}\n\n"
            "## Operational Rules\n\n"
            f"{rules or '- Respect permissions.'}\n"
        )
