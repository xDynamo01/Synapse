from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, runtime_from

router = APIRouter()


class ToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolRunRequest(BaseModel):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    caller: str = "api"
    caller_type: str = "user"
    agent_id: str | None = None
    conversation_id: str | None = None
    mission_id: str | None = None
    resource_ref: dict[str, Any] | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolIntentCreatePayload(BaseModel):
    tool_id: str
    proposed_arguments: dict[str, Any] = Field(default_factory=dict)
    source: str = "user"
    source_agent_id: str | None = None
    conversation_id: str | None = None
    mission_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolIntentReviewPayload(BaseModel):
    reviewed_by: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ToolIntentExecutePayload(BaseModel):
    executor: str = "user"


@router.get("/tools")
def list_tools(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(tool) for tool in runtime.tool_runtime.list_tools()]


@router.get("/mcp/servers")
def list_mcp_servers(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(server) for server in runtime.mcp.list_servers()]


@router.get("/mcp/servers/{server_id}")
def get_mcp_server(server_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.mcp.get_server(server_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/mcp/tools")
def list_mcp_tools(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(tool) for tool in runtime.mcp.list_tools()]


@router.get("/mcp/summary")
def mcp_summary(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.mcp.summary())


@router.get("/mcp/bridge")
def mcp_bridge_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {
        "status": asdict(runtime.mcp_bridge.bridge_status()),
        "tools": [asdict(tool) for tool in runtime.mcp_bridge.list_bridge_tools()],
    }


@router.post("/mcp/bridge/sync")
def sync_mcp_bridge(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.mcp_bridge.sync_from_mcp_registry())


@router.get("/mcp/bridge/tools/{bridge_tool_id}")
def explain_mcp_bridge_tool(bridge_tool_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.mcp_bridge.explain_bridge_tool(bridge_tool_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tools/health")
def tool_health(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {tool_id: asdict(health) for tool_id, health in runtime.tool_runtime.health().items()}


@router.post("/tools/run")
def run_runtime_tool(payload: ToolRunRequest, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        from synapse.resources.models import ResourceRef
        from synapse.tools.models import ToolExecutionRequest

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=payload.tool_id,
                arguments=payload.arguments,
                caller=payload.caller,
                caller_type=payload.caller_type,
                agent_id=payload.agent_id,
                conversation_id=payload.conversation_id,
                mission_id=payload.mission_id,
                resource_ref=ResourceRef(**payload.resource_ref) if payload.resource_ref else None,
                correlation_id=payload.correlation_id,
                causation_id=payload.causation_id,
                dry_run=payload.dry_run,
                metadata=payload.metadata,
            )
        )
        return asdict(result)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tools/preview")
def preview_runtime_tool(payload: ToolRunRequest, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        from synapse.tools.models import ToolExecutionRequest

        return asdict(
            runtime.tool_runtime.preview(
                ToolExecutionRequest(
                    tool_id=payload.tool_id,
                    arguments=payload.arguments,
                    caller=payload.caller,
                    caller_type=payload.caller_type,
                    agent_id=payload.agent_id,
                    conversation_id=payload.conversation_id,
                    mission_id=payload.mission_id,
                    dry_run=True,
                )
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tools/executions/{call_id}")
def get_tool_execution(call_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).tool_runtime.get_result(call_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tools/executions/{call_id}/cancel")
def cancel_tool_execution(call_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).tool_runtime.cancel(call_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tools/executions/{call_id}/retry")
def retry_tool_execution(call_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).tool_runtime.retry(call_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tools/executions/{call_id}/rollback")
def rollback_tool_execution(call_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).tool_runtime.rollback(call_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tools/decision")
def runtime_tool_decision(payload: ToolRunRequest, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        from synapse.resources.models import ResourceRef
        from synapse.tools.models import ToolExecutionRequest

        tool = runtime.tool_runtime.get_tool(payload.tool_id)
        decision = runtime.tool_runtime.permission_bridge.evaluate(
            tool,
            ToolExecutionRequest(
                tool_id=payload.tool_id,
                arguments=payload.arguments,
                caller=payload.caller,
                caller_type=payload.caller_type,
                agent_id=payload.agent_id,
                conversation_id=payload.conversation_id,
                mission_id=payload.mission_id,
                resource_ref=ResourceRef(**payload.resource_ref) if payload.resource_ref else None,
                correlation_id=payload.correlation_id,
                causation_id=payload.causation_id,
                dry_run=True,
                metadata=payload.metadata,
            ),
        )
        return asdict(decision)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tools/catalog")
def user_tool_catalog(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.tool_discovery.catalog_for_user())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tools/explain/{tool_id}")
def explain_runtime_tool(tool_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.tool_discovery.explain_tool(tool_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tools/{tool_id}")
def get_tool(tool_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.tool_runtime.get_tool(tool_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tool-intents")
def list_tool_intents(request: Request, status: str | None = None) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(intent) for intent in runtime.tool_intents.list_intents(status)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tool-intents/{intent_id}")
def get_tool_intent(intent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.tool_intents.get_intent(intent_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tool-intents")
def create_tool_intent(payload: ToolIntentCreatePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.tool_intents.create_intent(
                payload.tool_id,
                payload.proposed_arguments,
                payload.source,
                payload.source_agent_id,
                payload.conversation_id,
                payload.mission_id,
                payload.correlation_id,
                payload.causation_id,
                payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tool-intents/{intent_id}/approve")
def approve_tool_intent(
    intent_id: str,
    payload: ToolIntentReviewPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.tool_intents.approve_intent(
                intent_id,
                reviewed_by=payload.reviewed_by,
                reasons=payload.reasons,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tool-intents/{intent_id}/reject")
def reject_tool_intent(
    intent_id: str,
    payload: ToolIntentReviewPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.tool_intents.reject_intent(
                intent_id,
                reviewed_by=payload.reviewed_by,
                reasons=payload.reasons,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tool-intents/{intent_id}/cancel")
def cancel_tool_intent(
    intent_id: str,
    payload: ToolIntentReviewPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.tool_intents.cancel_intent(intent_id, payload.reviewed_by))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tool-intents/{intent_id}/execute")
def execute_tool_intent(
    intent_id: str,
    payload: ToolIntentExecutePayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.tool_intents.execute_intent(intent_id, payload.executor))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/tool-intents/{intent_id}/execution")
def tool_intent_execution(intent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.tool_intents.execution_summary(intent_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/approvals/pending")
def list_pending_approvals(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(approval) for approval in runtime.approvals.list_pending()]


@router.post("/approvals/{approval_id}/approve")
def approve_approval(
    approval_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        approval, tool_result = runtime.approval_resume.approve_and_resume(context, approval_id)
        return {"approval": asdict(approval), "tool_result": asdict(tool_result)}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/approvals/{approval_id}/reject")
def reject_approval(
    approval_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.approvals.reject(context, approval_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/tools/{tool_name}")
def execute_tool(
    tool_name: str,
    payload: ToolRequest,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        from synapse.tools.models import ToolExecutionRequest

        return asdict(
            runtime.tool_runtime.execute_tool_call(
                ToolExecutionRequest(
                    tool_id=tool_name,
                    arguments=payload.arguments,
                    caller=context.actor_id,
                    caller_type=context.actor_type,
                    requester=context.actor_id,
                )
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc
