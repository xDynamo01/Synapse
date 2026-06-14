from __future__ import annotations

from synapse.approvals.manager import ApprovalManager
from synapse.core.permissions import PermissionContext
from synapse.tools.calls import ToolCallRequest, ToolCallResult
from synapse.tools.router import ToolRouter


class ApprovalResumeRuntime:
    def __init__(self, approvals: ApprovalManager, tool_router: ToolRouter):
        self.approvals = approvals
        self.tool_router = tool_router

    def approve_and_resume(
        self,
        context: PermissionContext,
        approval_id: str,
    ) -> tuple[object, ToolCallResult]:
        approval = self.approvals.approve(context, approval_id)
        return approval, self.resume(context, approval_id)

    def resume(self, context: PermissionContext, approval_id: str) -> ToolCallResult:
        approval = self.approvals.get_status(approval_id)
        call = ToolCallRequest(
            id=approval.tool_call_id,
            name=approval.tool_name,
            arguments=approval.tool_args,
            approval_id=approval.id,
        )
        if approval.status != "approved":
            return ToolCallResult(
                request=call,
                success=False,
                status="failed",
                error=f"Approval request is {approval.status}: {approval_id}",
                approval_id=approval_id,
            )

        tool_context = PermissionContext(
            actor_id=approval.agent_id,
            actor_type="agent",
            device_id=context.device_id,
            autonomy=context.autonomy,
        )
        return self.tool_router.execute_call(
            tool_context,
            call,
            session_id=approval.session_id,
            original_message_id=approval.original_message_id,
            project_id=approval.project_id,
        )
