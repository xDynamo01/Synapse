from __future__ import annotations

import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from synapse.admin_policy.runtime import AdminPolicyRuntime
from synapse.agents.audit import AgentAuditRuntime
from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.registry import AgentRegistry
from synapse.approvals.manager import ApprovalManager
from synapse.capabilities.registry import CapabilityRegistry
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.lifecycle.runtime import LifecycleRuntime
from synapse.observability.correlation import current_correlation_fields
from synapse.presence.runtime import PresenceRuntime

ADMIN_STATUSES = {"active", "inactive"}
SAFE_AGENT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
ADMIN_ACTION_REQUEST_STATUSES = {
    "awaiting_approval",
    "approved",
    "rejected",
    "cancelled",
    "applied",
    "failed",
}
ADMIN_APPROVABLE_ACTIONS = {
    "agent.activate",
    "agent.deactivate",
    "agent.archive",
    "agent.restore",
}


@dataclass(frozen=True)
class AgentDirectoryEntry:
    agent_id: str
    display_name: str
    role: str
    status: str
    lifecycle_state: str | None = None
    presence_state: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    capabilities_count: int = 0
    risk_summary: str = "unknown"
    is_seed_agent: bool = False
    is_archived: bool = False


@dataclass(frozen=True)
class AgentAdminStatus:
    agent_id: str
    status: str = "active"
    is_archived: bool = False
    reason: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentArchiveResult:
    agent_id: str
    is_archived: bool
    status: str


@dataclass(frozen=True)
class AgentActivationResult:
    agent_id: str
    status: str
    is_archived: bool


@dataclass(frozen=True)
class AgentDeleteResult:
    agent_id: str
    deleted: bool
    dependencies: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentAdminValidationResult:
    agent_id: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentAdminActionRequest:
    action: str
    agent_id: str
    policy_decision: dict[str, Any]
    reasons: list[str] = field(default_factory=list)
    status: str = "awaiting_approval"
    approval_id: str | None = None
    actor_agent_id: str | None = None
    reason: str | None = None
    schema_version: int = 1
    record_type: str = "agent_admin_action_request"
    correlation_id: str | None = None
    causation_id: str | None = None
    parent_id: str | None = None
    source: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class AgentAdminActionStatus:
    total_requests: int
    pending_requests: int
    requests: list[dict[str, Any]]


@dataclass(frozen=True)
class AgentAdminActionResult:
    request_id: str
    action: str
    agent_id: str
    status: str
    applied: bool = False
    approval_id: str | None = None
    result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentAdminCleanupResult:
    dry_run: bool
    scanned: int
    deleted: int
    preserved: int
    candidates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class AgentAdminRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        agents: AgentRegistry,
        identities: AgentIdentityRuntime,
        capabilities: CapabilityRegistry,
        event_bus: EventBus,
        presence: PresenceRuntime | None = None,
        lifecycle: LifecycleRuntime | None = None,
        audit: AgentAuditRuntime | None = None,
        admin_policy: AdminPolicyRuntime | None = None,
        approvals: ApprovalManager | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.agents = agents
        self.identities = identities
        self.capabilities = capabilities
        self.event_bus = event_bus
        self.presence = presence
        self.lifecycle = lifecycle
        self.audit = audit
        self.admin_policy = admin_policy
        self.approvals = approvals
        self.primary_agent: Any | None = None

    def list_agents(self, include_archived: bool = False) -> list[AgentDirectoryEntry]:
        entries = [self._directory_entry(agent.id) for agent in self.agents.list_agents()]
        if not include_archived:
            entries = [entry for entry in entries if not entry.is_archived]
        return sorted(entries, key=lambda item: item.agent_id)

    def get_agent_admin_status(self, agent_id: str) -> AgentAdminStatus:
        self._require_agent_exists(agent_id)
        return self._read_admin(agent_id)

    def activate_agent(
        self,
        agent_id: str,
        context: PermissionContext | None = None,
        _skip_policy: bool = False,
    ) -> AgentActivationResult:
        if not _skip_policy:
            self.check_admin_action("agent.activate", agent_id, context)
        validation = self.validate_agent_admin_state(
            agent_id, context=context, _skip_policy=_skip_policy
        )
        if not validation.valid:
            self.event_bus.emit("agent.admin.validation_failed", agent_id, asdict(validation))
            self._audit(
                agent_id,
                "agent.admin.validation_failed",
                "failed",
                reason="; ".join(validation.errors),
                details=asdict(validation),
            )
            raise ValidationError("; ".join(validation.errors))
        current = self._read_admin(agent_id)
        updated = self._write_admin(
            AgentAdminStatus(
                agent_id=agent_id,
                status="active",
                is_archived=current.is_archived,
                reason="activated",
                created_at=current.created_at or datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
                metadata=current.metadata,
            )
        )
        self.event_bus.emit("agent.activated", agent_id, asdict(updated))
        self.event_bus.emit("agent.admin.status_changed", agent_id, asdict(updated))
        self._audit(agent_id, "agent.activated", "success", details=asdict(updated))
        return AgentActivationResult(
            agent_id=agent_id, status=updated.status, is_archived=updated.is_archived
        )

    def deactivate_agent(
        self,
        agent_id: str,
        context: PermissionContext | None = None,
        _skip_policy: bool = False,
    ) -> AgentActivationResult:
        self._protect_primary(agent_id, "deactivate")
        if not _skip_policy:
            self.check_admin_action("agent.deactivate", agent_id, context)
        self._require_agent_exists(agent_id)
        current = self._read_admin(agent_id)
        updated = self._write_admin(
            AgentAdminStatus(
                agent_id=agent_id,
                status="inactive",
                is_archived=current.is_archived,
                reason="deactivated",
                created_at=current.created_at or datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
                metadata=current.metadata,
            )
        )
        self._set_offline(agent_id)
        self.event_bus.emit("agent.deactivated", agent_id, asdict(updated))
        self.event_bus.emit("agent.admin.status_changed", agent_id, asdict(updated))
        self._audit(agent_id, "agent.deactivated", "success", details=asdict(updated))
        return AgentActivationResult(
            agent_id=agent_id, status=updated.status, is_archived=updated.is_archived
        )

    def archive_agent(
        self,
        agent_id: str,
        context: PermissionContext | None = None,
        _skip_policy: bool = False,
    ) -> AgentArchiveResult:
        self._protect_primary(agent_id, "archive")
        if not _skip_policy:
            self.check_admin_action("agent.archive", agent_id, context)
        self._require_agent_exists(agent_id)
        current = self._read_admin(agent_id)
        if current.is_archived:
            raise ValidationError(f"Agent is already archived: {agent_id}")
        updated = self._write_admin(
            AgentAdminStatus(
                agent_id=agent_id,
                status="inactive",
                is_archived=True,
                reason="archived",
                created_at=current.created_at or datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
                metadata=current.metadata,
            )
        )
        self._set_offline(agent_id)
        self.event_bus.emit("agent.archived", agent_id, asdict(updated))
        self.event_bus.emit("agent.admin.status_changed", agent_id, asdict(updated))
        self._audit(agent_id, "agent.archived", "success", details=asdict(updated))
        return AgentArchiveResult(agent_id=agent_id, is_archived=True, status=updated.status)

    def restore_agent(
        self,
        agent_id: str,
        context: PermissionContext | None = None,
        _skip_policy: bool = False,
    ) -> AgentArchiveResult:
        if not _skip_policy:
            self.check_admin_action("agent.restore", agent_id, context)
        self._require_agent_exists(agent_id)
        current = self._read_admin(agent_id)
        if not current.is_archived:
            raise ValidationError(f"Agent is not archived: {agent_id}")
        updated = self._write_admin(
            AgentAdminStatus(
                agent_id=agent_id,
                status="active",
                is_archived=False,
                reason="restored",
                created_at=current.created_at or datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
                metadata=current.metadata,
            )
        )
        self.event_bus.emit("agent.restored", agent_id, asdict(updated))
        self.event_bus.emit("agent.admin.status_changed", agent_id, asdict(updated))
        self._audit(agent_id, "agent.restored", "success", details=asdict(updated))
        return AgentArchiveResult(agent_id=agent_id, is_archived=False, status=updated.status)

    def delete_agent(
        self,
        agent_id: str,
        confirmation: str,
        context: PermissionContext | None = None,
        *,
        force: bool = False,
    ) -> AgentDeleteResult:
        safe_id = agent_id.strip().lower()
        if not SAFE_AGENT_ID.fullmatch(safe_id) or safe_id != agent_id.strip():
            raise ValidationError("Invalid agent_id")
        self.check_admin_action("agent.delete", safe_id, context)
        self._protect_primary(safe_id, "delete")
        self._require_agent_exists(safe_id)
        if confirmation != f"DELETE {safe_id}":
            raise ValidationError(f"Permanent deletion requires confirmation: DELETE {safe_id}")
        status = self._read_admin(safe_id)
        if status.status == "active":
            raise ValidationError("Active agent must be deactivated before permanent deletion")
        dependencies = self._agent_dependencies(safe_id)
        if dependencies and not force:
            raise ValidationError(
                "Agent has dependent records; archive it or use explicit force: "
                + ", ".join(dependencies)
            )

        agent_root = self.data_dir.resolve(f"agents/{safe_id}")
        staging_root = self.data_dir.resolve(f"agent_deletion_staging/{uuid4()}/{safe_id}")
        staging_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(agent_root, staging_root)
            shutil.rmtree(staging_root)
            if staging_root.parent.exists():
                staging_root.parent.rmdir()
        except Exception as exc:
            if staging_root.exists() and not agent_root.exists():
                agent_root.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging_root, agent_root)
            raise ValidationError(f"Agent deletion failed and was rolled back: {safe_id}") from exc

        result = AgentDeleteResult(agent_id=safe_id, deleted=True, dependencies=dependencies)
        self.event_bus.emit("agent.deleted", safe_id, asdict(result))
        if self.audit:
            self.audit.append_provisioning_record(
                agent_id=safe_id,
                action="agent.deleted",
                status="success",
                actor_agent_id=context.actor_id if context else None,
                actor_type=context.actor_type if context else "system",
                details=asdict(result),
            )
        return result

    def validate_agent_admin_state(
        self,
        agent_id: str,
        context: PermissionContext | None = None,
        _skip_policy: bool = False,
    ) -> AgentAdminValidationResult:
        if not _skip_policy:
            self.check_admin_action("agent.validate", agent_id, context)
        errors: list[str] = []
        warnings: list[str] = []
        try:
            self.agents.get(agent_id)
            self.identities.load_identity(agent_id)
        except Exception as exc:
            errors.append(str(exc) or type(exc).__name__)
        admin = self._read_admin(agent_id, missing_ok=True)
        if admin.status not in ADMIN_STATUSES:
            errors.append(f"invalid admin status: {admin.status}")
        if admin.is_archived and admin.status == "active":
            warnings.append("archived agent should not be active")
        return AgentAdminValidationResult(
            agent_id=agent_id,
            valid=not errors,
            errors=errors,
            warnings=warnings,
        )

    def request_admin_action(
        self,
        action: str,
        agent_id: str,
        actor_agent_id: str | None = None,
        reason: str | None = None,
        correlation_id: str | None = None,
        context: PermissionContext | None = None,
    ) -> AgentAdminActionRequest:
        if action not in ADMIN_APPROVABLE_ACTIONS:
            raise ValidationError(f"Admin action cannot be requested for approval: {action}")
        self._require_agent_exists(agent_id)
        context = context or PermissionContext(
            actor_id=actor_agent_id or "admin_action",
            actor_type="user",
        )
        decision = self._policy_decision(context, action, agent_id)
        if decision.blocked_reasons:
            self._audit(
                agent_id,
                "admin.action.failed",
                "blocked",
                reason="; ".join(decision.blocked_reasons),
                details=decision.to_dict(),
            )
            raise ValidationError("; ".join(decision.blocked_reasons))
        if not decision.requires_approval:
            raise ValidationError(f"Admin action does not require approval: {action}")

        fields = current_correlation_fields()
        if correlation_id:
            fields["correlation_id"] = correlation_id
        request = AgentAdminActionRequest(
            action=action,
            agent_id=agent_id.lower(),
            policy_decision=decision.to_dict(),
            reasons=list(decision.reasons),
            actor_agent_id=actor_agent_id or context.actor_id,
            reason=reason,
            **fields,
        )
        approval = self._require_approvals().create_request(
            context=context,
            tool_name="agent_admin_action",
            tool_args={
                "request_type": "agent_admin_action",
                "admin_action_request_id": request.id,
                "action": request.action,
                "target_agent_id": request.agent_id,
                "policy_decision": request.policy_decision,
                "reasons": request.reasons,
            },
            risk_level="high",
            reason=reason or f"Admin action requires approval: {action} on {agent_id}",
            tool_call_id=f"agent-admin-action:{request.id}",
        )
        request = self._transition_admin_request(request, "awaiting_approval", approval.id)
        self.event_bus.emit("agent.admin_action.requested", request.agent_id, asdict(request))
        self.event_bus.emit(
            "agent.admin_action.awaiting_approval", request.agent_id, asdict(request)
        )
        self._audit(request.agent_id, "admin.action.requested", "success", details=asdict(request))
        self._audit(
            request.agent_id,
            "admin.action.awaiting_approval",
            "success",
            details=asdict(request),
        )
        return request

    def approve_admin_action_request(
        self,
        request_id: str,
        context: PermissionContext | None = None,
    ) -> AgentAdminActionRequest:
        request = self.get_admin_action_request(request_id)
        if request.status != "awaiting_approval":
            raise ValidationError(f"Admin action request is not awaiting approval: {request_id}")
        if not request.approval_id:
            raise ValidationError(f"Admin action request has no approval: {request_id}")
        context = context or PermissionContext(actor_id=request.actor_agent_id or "admin_action")
        self._require_approvals().approve(context, request.approval_id)
        updated = self._transition_admin_request(request, "approved")
        self.event_bus.emit("agent.admin_action.approved", updated.agent_id, asdict(updated))
        self._audit(
            updated.agent_id,
            "admin.action.approved",
            "success",
            details=asdict(updated),
        )
        return updated

    def reject_admin_action_request(
        self,
        request_id: str,
        context: PermissionContext | None = None,
    ) -> AgentAdminActionRequest:
        request = self.get_admin_action_request(request_id)
        if request.status != "awaiting_approval":
            raise ValidationError(f"Admin action request is not awaiting approval: {request_id}")
        if not request.approval_id:
            raise ValidationError(f"Admin action request has no approval: {request_id}")
        context = context or PermissionContext(actor_id=request.actor_agent_id or "admin_action")
        self._require_approvals().reject(context, request.approval_id)
        updated = self._transition_admin_request(request, "rejected")
        self.event_bus.emit("agent.admin_action.rejected", updated.agent_id, asdict(updated))
        self._audit(
            updated.agent_id,
            "admin.action.rejected",
            "success",
            details=asdict(updated),
        )
        return updated

    def apply_admin_action_request(
        self,
        request_id: str,
        context: PermissionContext | None = None,
    ) -> AgentAdminActionResult:
        request = self.get_admin_action_request(request_id)
        if request.status == "applied":
            raise ValidationError(f"Admin action request already applied: {request_id}")
        if request.status != "approved":
            raise ValidationError(f"Admin action request is not approved: {request_id}")
        context = context or PermissionContext(actor_id=request.actor_agent_id or "admin_action")
        self._require_agent_exists(request.agent_id)
        decision = self._policy_decision(context, request.action, request.agent_id)
        if decision.blocked_reasons:
            failed = self._transition_admin_request(request, "failed")
            self.event_bus.emit(
                "agent.admin_action.failed",
                failed.agent_id,
                {**asdict(failed), "error": "; ".join(decision.blocked_reasons)},
            )
            self._audit(
                failed.agent_id,
                "admin.action.failed",
                "blocked",
                reason="; ".join(decision.blocked_reasons),
                details=asdict(failed),
            )
            raise ValidationError("; ".join(decision.blocked_reasons))
        try:
            result_payload = self._apply_admin_action_direct(request, context)
            applied = self._transition_admin_request(request, "applied")
            result = AgentAdminActionResult(
                request_id=applied.id,
                action=applied.action,
                agent_id=applied.agent_id,
                status=applied.status,
                applied=True,
                approval_id=applied.approval_id,
                result=result_payload,
            )
            self.event_bus.emit("agent.admin_action.applied", applied.agent_id, asdict(result))
            self._audit(applied.agent_id, "admin.action.applied", "success", details=asdict(result))
            if applied.approval_id and self.approvals:
                self.approvals.mark_resumed(context, applied.approval_id, asdict(result))
            return result
        except Exception as exc:
            failed = self._transition_admin_request(request, "failed")
            self.event_bus.emit(
                "agent.admin_action.failed",
                failed.agent_id,
                {**asdict(failed), "error": str(exc) or type(exc).__name__},
            )
            self._audit(
                failed.agent_id,
                "admin.action.failed",
                "failed",
                reason=str(exc) or type(exc).__name__,
                details=asdict(failed),
            )
            raise

    def list_admin_action_requests(self) -> list[AgentAdminActionRequest]:
        return [
            self._read_admin_request(path)
            for path in sorted(self._admin_requests_root().glob("*.yaml"))
        ]

    def get_admin_action_request(self, request_id: str) -> AgentAdminActionRequest:
        path = self._admin_request_path(request_id)
        if not path.exists():
            raise NotFound(f"Agent admin action request not found: {request_id}")
        return self._read_admin_request(path)

    def cleanup_admin_action_requests(self, dry_run: bool = True) -> AgentAdminCleanupResult:
        policy = self._load_retention_policy()
        if dry_run is None:
            dry_run = bool(policy["dry_run_default"])
        self.event_bus.emit(
            "agent.admin_request_cleanup.started",
            "agent_admin",
            {"dry_run": dry_run, "policy": policy},
        )
        try:
            if not policy["enabled"]:
                requests = self.list_admin_action_requests()
                result = AgentAdminCleanupResult(
                    dry_run=dry_run,
                    scanned=len(requests),
                    deleted=0,
                    preserved=len(requests),
                    candidates=[],
                    errors=[],
                )
                self.event_bus.emit(
                    "agent.admin_request_cleanup.completed",
                    "agent_admin",
                    asdict(result),
                )
                return result

            requests = self.list_admin_action_requests()
            by_id = {request.id: request for request in requests}
            candidates = self._retention_candidates(requests, policy)
            candidate_ids = [request.id for request in candidates]
            errors: list[str] = []
            deleted = 0
            if not dry_run:
                for request in candidates:
                    try:
                        self._admin_request_path(request.id).unlink(missing_ok=True)
                        deleted += 1
                    except Exception as exc:
                        errors.append(f"{request.id}: {str(exc) or type(exc).__name__}")
            preserved = len(
                [
                    request
                    for request_id, request in by_id.items()
                    if request_id not in set(candidate_ids)
                ]
            )
            result = AgentAdminCleanupResult(
                dry_run=dry_run,
                scanned=len(requests),
                deleted=deleted,
                preserved=preserved,
                candidates=candidate_ids,
                errors=errors,
            )
            self.event_bus.emit(
                "agent.admin_request_cleanup.completed",
                "agent_admin",
                asdict(result),
            )
            return result
        except Exception as exc:
            self.event_bus.emit(
                "agent.admin_request_cleanup.failed",
                "agent_admin",
                {
                    "dry_run": dry_run,
                    "error": str(exc) or type(exc).__name__,
                    "error_type": type(exc).__name__,
                    "policy": policy,
                },
            )
            raise

    def admin_action_request_retention_status(self) -> dict[str, Any]:
        policy = self._load_retention_policy()
        requests = self.list_admin_action_requests()
        counts: dict[str, int] = {}
        for request in requests:
            counts[request.status] = counts.get(request.status, 0) + 1
        return {
            "policy": policy,
            "total_requests": len(requests),
            "counts": counts,
            "dry_run_default": policy["dry_run_default"],
        }

    def check_admin_action(
        self,
        action: str,
        agent_id: str,
        context: PermissionContext | None = None,
    ):
        normalized_agent_id = agent_id.strip().lower()
        if not self.admin_policy:
            self._audit(
                normalized_agent_id,
                action,
                "allowed",
                reason="admin policy not configured",
            )
            return None
        decision = self.admin_policy.check(context, action, normalized_agent_id)
        if decision.allowed:
            self._audit(
                normalized_agent_id,
                action,
                "allowed",
                details=decision.to_dict(),
            )
            return decision
        if decision.requires_approval:
            self._audit(
                normalized_agent_id,
                action,
                "requires_approval",
                reason="; ".join(decision.reasons),
                details=decision.to_dict(),
            )
            raise ValidationError(
                f"Admin action requires approval before execution: {action} on {normalized_agent_id}"
            )
        self._audit(
            normalized_agent_id,
            action,
            "blocked",
            reason="; ".join(decision.blocked_reasons),
            details=decision.to_dict(),
        )
        raise ValidationError("; ".join(decision.blocked_reasons))

    def assert_agent_runnable(self, agent_id: str) -> None:
        admin = self._read_admin(agent_id, missing_ok=True)
        if admin.is_archived:
            raise ValidationError(f"Agent is archived: {agent_id}")
        if admin.status != "active":
            raise ValidationError(f"Agent is not active: {agent_id}")

    def initialize_agent(self, agent_id: str) -> AgentAdminStatus:
        current = self._read_admin(agent_id, missing_ok=True)
        if self._admin_path(agent_id).exists():
            return current
        now = datetime.now(UTC).isoformat()
        return self._write_admin(
            AgentAdminStatus(
                agent_id=agent_id,
                status="active",
                is_archived=False,
                reason="provisioned",
                created_at=now,
                updated_at=now,
            )
        )

    def _directory_entry(self, agent_id: str) -> AgentDirectoryEntry:
        agent = self.agents.get(agent_id)
        admin = self._read_admin(agent_id, missing_ok=True)
        config = load_structured_file(self.data_dir.resolve(f"agents/{agent_id}/CONFIG.yaml"))
        lifecycle_state = self.lifecycle.get(agent_id).state if self.lifecycle else None
        presence_state = self.presence.get(agent_id).state if self.presence else None
        capabilities = config.get("capabilities", {})
        allowed_capabilities = (
            capabilities.get("allow", []) if isinstance(capabilities, dict) else []
        )
        return AgentDirectoryEntry(
            agent_id=agent_id,
            display_name=agent.name,
            role=agent.role,
            status=admin.status,
            lifecycle_state=lifecycle_state,
            presence_state=presence_state,
            created_at=config.get("created_at") or admin.created_at,
            updated_at=config.get("updated_at") or admin.updated_at,
            capabilities_count=len(allowed_capabilities),
            risk_summary=self._risk_summary(allowed_capabilities),
            is_seed_agent=config.get("record_type") != "agent_config",
            is_archived=admin.is_archived,
        )

    def _risk_summary(self, capability_ids: list[str]) -> str:
        risk = "low"
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        for capability_id in capability_ids:
            try:
                capability = self.capabilities.get(capability_id)
            except Exception:
                continue
            if order[capability.risk_level] > order[risk]:
                risk = capability.risk_level
        return risk

    def _require_agent_exists(self, agent_id: str) -> None:
        try:
            self.agents.get(agent_id)
        except NotFound:
            raise

    def _protect_primary(self, agent_id: str, action: str) -> None:
        if self.primary_agent is None:
            return
        state = self.primary_agent.get_state()
        if state.profile and state.profile.agent_id == agent_id:
            raise ValidationError(
                f"Active primary agent cannot be {action}d; replace the primary first"
            )

    def _agent_dependencies(self, agent_id: str) -> list[str]:
        dependencies: list[str] = []
        for domain in ("conversations", "tasks", "delegation"):
            root = self.data_dir.resolve(domain)
            if not root.exists():
                continue
            if any(self._file_references_agent(path, agent_id) for path in root.rglob("*")):
                dependencies.append(domain)
        return dependencies

    @staticmethod
    def _file_references_agent(path, agent_id: str) -> bool:
        if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml", ".json", ".jsonl"}:
            return False
        try:
            return f'"{agent_id}"' in path.read_text(
                encoding="utf-8"
            ) or f": {agent_id}" in path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False

    def _policy_decision(
        self,
        context: PermissionContext,
        action: str,
        agent_id: str,
    ):
        if not self.admin_policy:
            raise ValidationError("Admin policy is not configured")
        return self.admin_policy.check(context, action, agent_id.lower())

    def _apply_admin_action_direct(
        self,
        request: AgentAdminActionRequest,
        context: PermissionContext,
    ) -> dict[str, Any]:
        if request.action == "agent.activate":
            return asdict(self.activate_agent(request.agent_id, context, _skip_policy=True))
        if request.action == "agent.deactivate":
            return asdict(self.deactivate_agent(request.agent_id, context, _skip_policy=True))
        if request.action == "agent.archive":
            return asdict(self.archive_agent(request.agent_id, context, _skip_policy=True))
        if request.action == "agent.restore":
            return asdict(self.restore_agent(request.agent_id, context, _skip_policy=True))
        raise ValidationError(f"Unsupported admin action: {request.action}")

    def _require_approvals(self) -> ApprovalManager:
        if not self.approvals:
            raise ValidationError("Admin action approvals are not configured.")
        return self.approvals

    def _transition_admin_request(
        self,
        request: AgentAdminActionRequest,
        status: str,
        approval_id: str | None = None,
    ) -> AgentAdminActionRequest:
        if status not in ADMIN_ACTION_REQUEST_STATUSES:
            raise ValidationError(f"Invalid admin action request status: {status}")
        updated = AgentAdminActionRequest(
            id=request.id,
            action=request.action,
            agent_id=request.agent_id,
            policy_decision=request.policy_decision,
            reasons=request.reasons,
            status=status,
            approval_id=approval_id or request.approval_id,
            actor_agent_id=request.actor_agent_id,
            reason=request.reason,
            schema_version=request.schema_version,
            record_type=request.record_type,
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
            parent_id=request.parent_id,
            source=request.source,
            created_at=request.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )
        return self._write_admin_request(updated)

    def _admin_requests_root(self):
        return self.data_dir.resolve("agent_admin_requests")

    def _admin_request_path(self, request_id: str):
        return self.data_dir.resolve(f"agent_admin_requests/{request_id}.yaml")

    def _write_admin_request(
        self,
        request: AgentAdminActionRequest,
    ) -> AgentAdminActionRequest:
        dump_structured_file(self._admin_request_path(request.id), asdict(request))
        return request

    def _read_admin_request(self, path) -> AgentAdminActionRequest:
        raw = load_structured_file(path)
        raw.setdefault("schema_version", 1)
        raw.setdefault("record_type", "agent_admin_action_request")
        raw.setdefault("reasons", [])
        raw.setdefault("policy_decision", {})
        raw.setdefault("approval_id", None)
        raw.setdefault("actor_agent_id", None)
        raw.setdefault("reason", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("parent_id", None)
        raw.setdefault("source", None)
        return AgentAdminActionRequest(**raw)

    def _load_retention_policy(self) -> dict[str, Any]:
        raw = load_structured_file(
            self.data_dir.resolve("config/agent_admin_retention_policy.yaml")
        )
        policy = raw.get("agent_admin_retention", raw)
        if not isinstance(policy, dict):
            policy = {}
        return {
            "enabled": bool(policy.get("enabled", True)),
            "delete_applied_after_days": int(policy.get("delete_applied_after_days", 30)),
            "delete_rejected_after_days": int(policy.get("delete_rejected_after_days", 30)),
            "delete_failed_after_days": int(policy.get("delete_failed_after_days", 60)),
            "delete_cancelled_after_days": int(policy.get("delete_cancelled_after_days", 30)),
            "preserve_awaiting_approval": bool(policy.get("preserve_awaiting_approval", True)),
            "preserve_approved_not_applied": bool(
                policy.get("preserve_approved_not_applied", True)
            ),
            "max_requests": int(policy.get("max_requests", 500)),
            "dry_run_default": bool(policy.get("dry_run_default", True)),
        }

    def _retention_candidates(
        self,
        requests: list[AgentAdminActionRequest],
        policy: dict[str, Any],
    ) -> list[AgentAdminActionRequest]:
        candidates: list[AgentAdminActionRequest] = []
        now = datetime.now(UTC)
        for request in requests:
            if request.status == "awaiting_approval":
                continue
            if request.status == "approved" and policy["preserve_approved_not_applied"]:
                continue
            days = self._retention_days_for_status(request.status, policy)
            if days is None:
                continue
            updated_at = datetime.fromisoformat(request.updated_at)
            if updated_at <= now - timedelta(days=days):
                candidates.append(request)

        candidate_ids = {request.id for request in candidates}
        max_requests = int(policy["max_requests"])
        if max_requests >= 0 and len(requests) - len(candidates) > max_requests:
            eligible = [
                request
                for request in sorted(requests, key=lambda item: item.updated_at)
                if request.id not in candidate_ids
                and request.status != "awaiting_approval"
                and not (request.status == "approved" and policy["preserve_approved_not_applied"])
            ]
            while len(requests) - len(candidates) > max_requests and eligible:
                request = eligible.pop(0)
                candidates.append(request)
                candidate_ids.add(request.id)
        return candidates

    @staticmethod
    def _retention_days_for_status(status: str, policy: dict[str, Any]) -> int | None:
        mapping = {
            "applied": "delete_applied_after_days",
            "rejected": "delete_rejected_after_days",
            "failed": "delete_failed_after_days",
            "cancelled": "delete_cancelled_after_days",
        }
        key = mapping.get(status)
        return int(policy[key]) if key else None

    def _read_admin(self, agent_id: str, missing_ok: bool = False) -> AgentAdminStatus:
        path = self._admin_path(agent_id)
        if not path.exists():
            if not missing_ok:
                self._require_agent_exists(agent_id)
            return AgentAdminStatus(agent_id=agent_id)
        raw = load_structured_file(path)
        raw.setdefault("status", "active")
        raw.setdefault("is_archived", False)
        raw.setdefault("reason", None)
        raw.setdefault("created_at", None)
        raw.setdefault("updated_at", None)
        raw.setdefault("metadata", {})
        return AgentAdminStatus(
            agent_id=agent_id, **{key: value for key, value in raw.items() if key != "agent_id"}
        )

    def _write_admin(self, status: AgentAdminStatus) -> AgentAdminStatus:
        dump_structured_file(self._admin_path(status.agent_id), asdict(status))
        return status

    def _admin_path(self, agent_id: str):
        return self.data_dir.resolve(f"agents/{agent_id}/ADMIN.yaml")

    def _set_offline(self, agent_id: str) -> None:
        if self.lifecycle:
            self.lifecycle.shutdown(agent_id)
        elif self.presence:
            self.presence.set_state(agent_id, "offline", "Agent disabled", {"actor_id": agent_id})

    def _audit(
        self,
        agent_id: str,
        action: str,
        status: str,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.audit:
            self.audit.append_record(
                agent_id=agent_id,
                action=action,
                status=status,
                actor_type="system",
                reason=reason,
                details=details or {},
            )
