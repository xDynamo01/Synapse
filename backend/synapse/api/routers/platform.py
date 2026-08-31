from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, payload_dict, runtime_from
from synapse.core.exceptions import ValidationError
from synapse.decisions.models import DecisionRequest
from synapse.maintenance.models import (
    MaintenanceInspectionRequest,
    MaintenanceScope,
    MaintenanceScopeKind,
)
from synapse.observability.redaction import redaction_self_test
from synapse.policies.models import PolicyRule

router = APIRouter()


class PolicyRulePayload(BaseModel):
    scope: str
    subject: str
    action: str
    resource: str
    effect: str
    source: str = "api"
    conditions: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    expires_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyUpdatePayload(BaseModel):
    expected_revision: int
    updates: dict[str, Any]


class PolicyEvaluatePayload(BaseModel):
    subject: str
    action: str
    resource: str
    context: dict[str, Any] = Field(default_factory=dict)


class ObservabilityCleanupPayload(BaseModel):
    retention_days: int = 30
    dry_run: bool = False


class RedactionTestPayload(BaseModel):
    sample_secret: str


class ExecutionPlanPayload(BaseModel):
    tool_id: str | None = None
    intent_id: str | None = None
    mcp_tool_id: str | None = None
    provider_id: str | None = None


class MessageSendPayload(BaseModel):
    sender_agent_id: str
    receiver_agent_id: str
    body: str
    subject: str = "Agent message"
    task_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None


class AdminCheckPayload(BaseModel):
    action: str
    agent_id: str


class DecisionCheckPayload(BaseModel):
    category: str
    action: str
    actor_type: str = "user"
    actor_id: str | None = None
    capability_id: str | None = None
    target_agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


@router.post("/messages/{message_id}/cancel")
def cancel_conversation_message(
    message_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.conversations.cancel_message(
                context_from(runtime, x_actor_id, x_actor_type, x_device_id), message_id
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/messages/send")
def send_message(
    payload: MessageSendPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        legacy = runtime.communication.send_agent_message(
            context=context,
            from_agent_id=payload.sender_agent_id,
            to_agent_id=payload.receiver_agent_id,
            subject=payload.subject,
            body=payload.body,
            task_id=payload.task_id,
            conversation_id=payload.conversation_id,
        )
        message = runtime.conversations.message_status(legacy.id)
        return asdict(message)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/messages/{message_id}/ack")
def acknowledge_message(
    message_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.conversations.acknowledge_message(context, message_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/retention")
def retention_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.retention.retention_status())


@router.get("/retention/domains/{domain_id}")
def retention_domain(domain_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.retention.get_domain(domain_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/migrations")
def migrations(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.migrations.migration_status())


@router.get("/capabilities")
def list_capabilities(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(capability) for capability in runtime.capabilities.list_capabilities()]


@router.get("/capabilities/{capability_id}")
def get_capability(capability_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.capabilities.get_capability(capability_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/admin-policy")
def admin_policy(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.admin_policy.current_policy()


@router.post("/admin-check")
def admin_check(
    payload: AdminCheckPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        decision = runtime.admin.check_admin_action(payload.action, payload.agent_id, context)
        return decision.to_dict() if decision else {"allowed": True}
    except Exception:
        return runtime.admin_policy.check(context, payload.action, payload.agent_id).to_dict()


@router.post("/decision-check")
def decision_check(payload: DecisionCheckPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        result = runtime.decisions.evaluate(DecisionRequest(**payload_dict(payload)))
        return result.to_dict()
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/presence")
def list_presence(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(presence) for presence in runtime.presence.list_all()]


@router.get("/presence/{agent_id}")
def get_presence(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.presence.get(agent_id))


@router.get("/lifecycle")
def list_lifecycle(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(lifecycle) for lifecycle in runtime.lifecycle.list_all()]


@router.get("/lifecycle/{agent_id}")
def get_lifecycle(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.lifecycle.get(agent_id))


@router.post("/lifecycle/{agent_id}/wake")
def wake_agent(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.lifecycle.wake(agent_id, "api wake"))


@router.post("/lifecycle/{agent_id}/sleep")
def sleep_agent(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.lifecycle.sleep(agent_id))


@router.get("/notifications")
def list_notifications(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(notification) for notification in runtime.notifications.list_notifications()]


@router.get("/notifications/unread")
def list_unread_notifications(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(notification) for notification in runtime.notifications.list_unread()]


@router.post("/notifications/cleanup")
def cleanup_notifications(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.notifications.cleanup_notifications())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/notifications/{notification_id}")
def get_notification(notification_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.notifications.get(notification_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.notifications.mark_read(notification_id, context=context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        runtime.notifications.delete_notification(notification_id, context=context)
        return {"deleted": True, "id": notification_id}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/events")
def list_events(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    event_type: str | None = None,
    source_module: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [
        asdict(event)
        for event in runtime.events.query_events(
            event_type=event_type,
            source_module=source_module,
            status=status,
            offset=offset,
            limit=limit,
        )
    ]


@router.get("/trace/{correlation_id}")
def trace_events(correlation_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.events.query_trace(correlation_id)


@router.get("/observability/metrics")
def observability_metrics(request: Request) -> dict[str, Any]:
    return runtime_from(request).health.operational_metrics()


@router.get("/observability/errors")
def observability_errors(request: Request, limit: int = 100) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(item) for item in runtime.events.query_events(status="failed", limit=limit)]


@router.get("/observability/status")
def observability_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {"state": "ready", "storage": "events.jsonl", "metrics": runtime.events.metrics()}


@router.post("/observability/cleanup")
def observability_cleanup(payload: ObservabilityCleanupPayload, request: Request) -> dict[str, Any]:
    return runtime_from(request).events.cleanup(payload.retention_days, payload.dry_run)


@router.get("/policies")
def list_policies(request: Request, scope: str | None = None, subject: str | None = None):
    return [asdict(item) for item in runtime_from(request).policies.list_rules(scope, subject)]


@router.post("/policies")
def create_policy(payload: PolicyRulePayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).policies.create_rule(PolicyRule(**payload.model_dump()))
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/policies/{rule_id}")
def get_policy(rule_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).policies.get_rule(rule_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/policies/{rule_id}")
def update_policy(rule_id: str, payload: PolicyUpdatePayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).policies.update_rule(
                rule_id, payload.updates, payload.expected_revision
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/policies/{rule_id}")
def delete_policy(rule_id: str, request: Request, expected_revision: int | None = None):
    try:
        return asdict(runtime_from(request).policies.delete_rule(rule_id, expected_revision))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/policies/evaluate")
def evaluate_policy(payload: PolicyEvaluatePayload, request: Request) -> dict[str, Any]:
    return asdict(
        runtime_from(request).policies.evaluate_policy(
            payload.subject, payload.action, payload.resource, payload.context
        )
    )


@router.post("/policies/explain")
def explain_policy(payload: PolicyEvaluatePayload, request: Request) -> dict[str, Any]:
    return runtime_from(request).policies.explain_policy(
        payload.subject,
        payload.action,
        payload.resource,
        payload.context,
    )


@router.get("/policies/effective/{agent_id}")
def effective_agent_policy(agent_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.policies.resolve(runtime.context(), agent_id).to_dict()


@router.post("/policies/validate")
def validate_policy(payload: PolicyRulePayload, request: Request) -> dict[str, Any]:
    rule = PolicyRule(**payload.model_dump())
    runtime_from(request).policies.validate_rule(rule)
    return {"valid": True, "rule": asdict(rule)}


@router.get("/policies/{rule_id}/history")
def policy_history(rule_id: str, request: Request) -> list[dict[str, Any]]:
    return runtime_from(request).policies.rule_history(rule_id)


@router.post("/security/redaction-test")
def security_redaction_test(payload: RedactionTestPayload) -> dict[str, Any]:
    return redaction_self_test(payload.sample_secret)


@router.get("/foundation/validate-data-dir")
def validate_data_dir(
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    report = runtime.maintenance.inspect(
        context,
        MaintenanceInspectionRequest(
            MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, "foundation")
        ),
    )
    escaped = [item.reference for item in report.findings if item.category == "escaped_symlink"]
    return {
        "state": "ready" if not report.findings else "misconfigured",
        "writable": not any(item.category == "root_not_writable" for item in report.findings),
        "escaped_symlinks": escaped,
        "invalid_configs": [],
        "checked_at": report.completed_at,
    }


@router.get("/foundation/validate-config")
def validate_configuration(
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    report = runtime.maintenance.inspect(
        context,
        MaintenanceInspectionRequest(
            MaintenanceScope(MaintenanceScopeKind.CONTRIBUTOR, "configuration")
        ),
    )
    invalid = [item.reference.removeprefix("config:") for item in report.findings]
    return {"valid": not invalid, "invalid_configs": invalid}


@router.get("/execution/targets")
def execution_targets(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(target) for target in runtime.execution_router.registry.list_targets()]


@router.post("/execution/plan")
def execution_plan(payload: ExecutionPlanPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        supplied = [
            value
            for value in [
                payload.tool_id,
                payload.intent_id,
                payload.mcp_tool_id,
                payload.provider_id,
            ]
            if value
        ]
        if len(supplied) != 1:
            raise ValidationError("Provide exactly one execution routing reference")
        if payload.intent_id:
            plan = runtime.execution_router.route_intent(payload.intent_id)
        elif payload.mcp_tool_id:
            plan = runtime.execution_router.route_mcp(payload.mcp_tool_id)
        elif payload.provider_id:
            plan = runtime.execution_router.route_provider(payload.provider_id)
        else:
            plan = runtime.execution_router.route_tool(str(payload.tool_id))
        return asdict(plan)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/execution/summary")
def execution_summary(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.execution_router.execution_summary())
