from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse.auth.devices import DeviceRegistry
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, PermissionDenied, ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.observability.correlation import current_correlation_fields

APPROVAL_STATUSES = {"pending", "approved", "rejected", "expired", "resumed"}
RISK_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class ApprovalPolicy:
    required_risk_levels: list[str] = field(default_factory=lambda: ["high", "critical"])
    bypass_agents: list[str] = field(default_factory=list)
    approver_device_permissions: list[str] = field(default_factory=lambda: ["approve_actions"])
    explicit_permission_bypasses_approval: bool = False
    default_expires_minutes: int | None = None


@dataclass(frozen=True)
class ApprovalRequest:
    agent_id: str
    tool_name: str
    tool_args: dict[str, Any]
    risk_level: str
    reason: str
    tool_call_id: str
    session_id: str | None = None
    original_message_id: str | None = None
    project_id: str | None = None
    status: str = "pending"
    approved_by: str | None = None
    expires_at: str | None = None
    resumed_at: str | None = None
    resume_result: dict[str, Any] | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    parent_id: str | None = None
    source: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ApprovalManager:
    def __init__(
        self,
        data_dir: DataDir,
        permissions: PermissionManager,
        devices: DeviceRegistry,
        event_bus: EventBus,
    ):
        self.data_dir = data_dir
        self.permissions = permissions
        self.devices = devices
        self.event_bus = event_bus
        self.policy = self._load_policy()

    def requires_approval(
        self,
        agent_id: str,
        risk_level: str,
        permission_explicitly_granted: bool,
    ) -> bool:
        if risk_level not in RISK_LEVELS:
            raise ValidationError(f"Invalid risk level: {risk_level}")
        if agent_id in self.policy.bypass_agents:
            return False
        if (
            permission_explicitly_granted
            and self.policy.explicit_permission_bypasses_approval
        ):
            return False
        return risk_level in set(self.policy.required_risk_levels)

    def create_request(
        self,
        context: PermissionContext,
        tool_name: str,
        tool_args: dict[str, Any],
        risk_level: str,
        reason: str,
        tool_call_id: str,
        session_id: str | None = None,
        original_message_id: str | None = None,
        project_id: str | None = None,
    ) -> ApprovalRequest:
        expires_at = None
        if self.policy.default_expires_minutes is not None:
            expires_at = (
                datetime.now(UTC) + timedelta(minutes=self.policy.default_expires_minutes)
            ).isoformat()
        request = ApprovalRequest(
            agent_id=context.actor_id,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=risk_level,
            reason=reason,
            tool_call_id=tool_call_id,
            session_id=session_id,
            original_message_id=original_message_id,
            project_id=project_id,
            expires_at=expires_at,
            **current_correlation_fields(),
        )
        self._write(request)
        self.event_bus.emit("approval.requested", context.actor_id, asdict(request))
        return request

    def list_pending(self) -> list[ApprovalRequest]:
        return [request for request in self._list_all() if request.status == "pending"]

    def approve(self, context: PermissionContext, approval_id: str) -> ApprovalRequest:
        self.permissions.require(context, "approvals.approve")
        self._require_device_can_approve(context)
        request = self.get_status(approval_id)
        if request.status != "pending":
            raise ValidationError(f"Approval request is not pending: {approval_id}")
        updated = self._transition(request, "approved", approved_by=context.actor_id)
        self.event_bus.emit("approval.approved", context.actor_id, asdict(updated))
        return updated

    def reject(self, context: PermissionContext, approval_id: str) -> ApprovalRequest:
        self.permissions.require(context, "approvals.reject")
        self._require_device_can_approve(context)
        request = self.get_status(approval_id)
        if request.status != "pending":
            raise ValidationError(f"Approval request is not pending: {approval_id}")
        updated = self._transition(request, "rejected", approved_by=context.actor_id)
        self.event_bus.emit("approval.rejected", context.actor_id, asdict(updated))
        return updated

    def expire(self, context: PermissionContext, approval_id: str) -> ApprovalRequest:
        request = self.get_status(approval_id)
        if request.status != "pending":
            raise ValidationError(f"Approval request is not pending: {approval_id}")
        updated = self._transition(request, "expired")
        self.event_bus.emit("approval.expired", context.actor_id, asdict(updated))
        return updated

    def get_status(self, approval_id: str) -> ApprovalRequest:
        path = self._path(approval_id)
        if not path.exists():
            raise NotFound(f"Approval request not found: {approval_id}")
        request = self._read(path)
        if request.status == "pending" and request.expires_at:
            expires_at = datetime.fromisoformat(request.expires_at)
            if expires_at <= datetime.now(UTC):
                return self.expire(PermissionContext(actor_id="system"), approval_id)
        return request

    def get_resumable_request(self, approval_id: str) -> ApprovalRequest:
        request = self.get_status(approval_id)
        if request.status != "approved":
            raise ValidationError(f"Approval request is not resumable: {approval_id}")
        return request

    def mark_resumed(
        self,
        context: PermissionContext,
        approval_id: str,
        resume_result: dict[str, Any],
    ) -> ApprovalRequest:
        request = self.get_resumable_request(approval_id)
        updated = self._transition(
            request,
            "resumed",
            approved_by=request.approved_by,
            resumed_at=datetime.now(UTC).isoformat(),
            resume_result=resume_result,
        )
        self.event_bus.emit("approval.resumed", context.actor_id, asdict(updated))
        return updated

    def assert_approved_for_tool(
        self,
        approval_id: str,
        agent_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        risk_level: str,
    ) -> ApprovalRequest:
        request = self.get_status(approval_id)
        if request.status != "approved":
            raise PermissionDenied(f"Approval request is {request.status}: {approval_id}")
        if request.agent_id != agent_id:
            raise PermissionDenied(f"Approval request belongs to another agent: {approval_id}")
        if request.tool_name != tool_name:
            raise PermissionDenied(f"Approval request belongs to another tool: {approval_id}")
        if request.risk_level != risk_level:
            raise PermissionDenied(f"Approval request risk level changed: {approval_id}")
        if request.tool_args != tool_args:
            raise PermissionDenied(f"Approval request arguments changed: {approval_id}")
        return request

    def _transition(
        self,
        request: ApprovalRequest,
        status: str,
        approved_by: str | None = None,
        resumed_at: str | None = None,
        resume_result: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        if status not in APPROVAL_STATUSES:
            raise ValidationError(f"Invalid approval status: {status}")
        updated = ApprovalRequest(
            id=request.id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            tool_args=request.tool_args,
            risk_level=request.risk_level,
            reason=request.reason,
            tool_call_id=request.tool_call_id,
            session_id=request.session_id,
            original_message_id=request.original_message_id,
            project_id=request.project_id,
            status=status,
            approved_by=approved_by or request.approved_by,
            expires_at=request.expires_at,
            resumed_at=resumed_at or request.resumed_at,
            resume_result=resume_result if resume_result is not None else request.resume_result,
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
            parent_id=request.parent_id,
            source=request.source,
            created_at=request.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write(updated)
        return updated

    def _require_device_can_approve(self, context: PermissionContext) -> None:
        if not context.device_id:
            return
        device = self.devices.get_device(context.device_id)
        if not device or device.revoked or not device.trusted:
            raise PermissionDenied(f"Device cannot approve actions: {context.device_id}")
        required = set(self.policy.approver_device_permissions)
        if required and not required.intersection(set(device.permissions)):
            raise PermissionDenied(f"Device lacks approval permission: {context.device_id}")

    def _load_policy(self) -> ApprovalPolicy:
        raw = load_structured_file(self.data_dir.resolve("config/approval_policy.yaml"))
        approval = raw.get("approval", raw)
        return ApprovalPolicy(
            required_risk_levels=[
                str(item) for item in approval.get("required_risk_levels", ["high", "critical"])
            ],
            bypass_agents=[str(item) for item in approval.get("bypass_agents", [])],
            approver_device_permissions=[
                str(item)
                for item in approval.get("approver_device_permissions", ["approve_actions"])
            ],
            explicit_permission_bypasses_approval=bool(
                approval.get("explicit_permission_bypasses_approval", False)
            ),
            default_expires_minutes=approval.get("default_expires_minutes"),
        )

    def _list_all(self) -> list[ApprovalRequest]:
        approvals_dir = self.data_dir.resolve("approvals")
        return [self._read(path) for path in sorted(approvals_dir.glob("*.yaml"))]

    def _path(self, approval_id: str) -> Path:
        return self.data_dir.resolve(f"approvals/{approval_id}.yaml")

    def _write(self, request: ApprovalRequest) -> None:
        dump_structured_file(self._path(request.id), asdict(request))

    @staticmethod
    def _read(path: Path) -> ApprovalRequest:
        raw = load_structured_file(path)
        raw.setdefault("tool_call_id", raw.get("id", "unknown"))
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("parent_id", None)
        raw.setdefault("source", None)
        return ApprovalRequest(**raw)
