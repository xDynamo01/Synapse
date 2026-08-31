from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, runtime_from
from synapse.desktop_automation.models import (
    AutomationAction,
    ElementSelector,
    VerificationSpec,
)
from synapse.tools.identities import (
    DESKTOP_CANCEL,
    DESKTOP_EXECUTE,
    DESKTOP_PREVIEW,
)
from synapse.tools.models import ToolExecutionRequest

router = APIRouter()


class SelectorPayload(BaseModel):
    automation_id: str | None = None
    role: str | None = None
    control_type: str | None = None
    name: str | None = None
    description: str | None = None
    value: str | None = None
    window_id: str | None = None
    ancestor_ids: list[str] = Field(default_factory=list)


class VerificationPayload(BaseModel):
    kind: str
    selector: SelectorPayload | None = None
    expected: Any = None
    window_id: str | None = None


class ActionPayload(BaseModel):
    kind: str
    selector: SelectorPayload | None = None
    application: str | None = None
    window_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    verification: VerificationPayload | None = None
    fallback_allowed: bool = True
    max_attempts: int = 2


class PlanPayload(BaseModel):
    objective: str
    actions: list[ActionPayload]
    dry_run: bool = False


class PlanReferencePayload(BaseModel):
    plan_id: str
    approval_id: str | None = None


class ClipboardPayload(BaseModel):
    operation: Literal["get", "set", "clear"]
    value: str | None = None


@router.get("/applications")
def applications(request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).desktop.applications.list()]


@router.get("/windows")
def windows(request: Request, application_id: str | None = None) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).desktop.windows.list(application_id)]


@router.get("/desktop/state")
def desktop_state(request: Request) -> dict[str, Any]:
    return runtime_from(request).desktop.state()


@router.get("/automation/tree")
def automation_tree(request: Request, window_id: str, max_nodes: int = 500) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).desktop.ui_automation.tree(window_id, max_nodes))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/automation/element")
def automation_element(
    request: Request,
    window_id: str | None = None,
    automation_id: str | None = None,
    role: str | None = None,
    control_type: str | None = None,
    name: str | None = None,
) -> list[dict[str, Any]]:
    try:
        selector = ElementSelector(automation_id, role, control_type, name, window_id=window_id)
        _provider, elements = runtime_from(request).desktop.ui_automation.find(selector)
        ui = runtime_from(request).desktop.ui_automation
        return [asdict(ui.public_element(item)) for item in elements]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/automation/plan")
def automation_plan(
    payload: PlanPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        actor_id = x_actor_id or runtime_from(request).settings.default_actor_id
        plan = runtime_from(request).desktop.create_plan(
            actor_id,
            payload.objective,
            [_action(item) for item in payload.actions],
            dry_run=payload.dry_run,
        )
        return asdict(plan)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/automation/preview")
def automation_preview(payload: PlanReferencePayload, request: Request) -> dict[str, Any]:
    try:
        runtime = runtime_from(request)
        return runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=DESKTOP_PREVIEW,
                arguments={"plan_id": payload.plan_id},
                caller=runtime.settings.default_actor_id,
                caller_type="user",
            )
        ).output
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/automation/execute")
def automation_execute(payload: PlanReferencePayload, request: Request) -> dict[str, Any]:
    try:
        runtime = runtime_from(request)
        return runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=DESKTOP_EXECUTE,
                arguments={
                    "plan_id": payload.plan_id,
                    **({"approval_id": payload.approval_id} if payload.approval_id else {}),
                },
                caller=runtime.settings.default_actor_id,
                caller_type="user",
            )
        ).output
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/automation/cancel")
def automation_cancel(payload: PlanReferencePayload, request: Request) -> dict[str, Any]:
    try:
        runtime = runtime_from(request)
        return runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=DESKTOP_CANCEL,
                arguments={"plan_id": payload.plan_id},
                caller=runtime.settings.default_actor_id,
                caller_type="user",
            )
        ).output
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/automation/verify")
def automation_verify(payload: VerificationPayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).desktop.verify(_verification(payload)))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/automation/clipboard")
def automation_clipboard(
    payload: ClipboardPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
) -> dict[str, Any]:
    desktop = runtime_from(request).desktop
    if payload.operation == "get":
        return desktop.clipboard.get(reveal=False)
    try:
        kind = "clipboard.set" if payload.operation == "set" else "clipboard.clear"
        arguments = {"value": payload.value or ""} if kind == "clipboard.set" else {}
        actor_id = x_actor_id or runtime_from(request).settings.default_actor_id
        plan = desktop.create_plan(
            actor_id,
            "Governed clipboard operation",
            [AutomationAction(kind, arguments=arguments)],
        )
        runtime = runtime_from(request)
        return runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id=DESKTOP_EXECUTE,
                arguments={"plan_id": plan.id},
                caller=actor_id,
                caller_type="user",
            )
        ).output
    except Exception as exc:
        raise api_error(exc) from exc


def _selector(payload: SelectorPayload | None) -> ElementSelector | None:
    return ElementSelector(**payload.model_dump()) if payload else None


def _verification(payload: VerificationPayload) -> VerificationSpec:
    return VerificationSpec(
        payload.kind,
        _selector(payload.selector),
        payload.expected,
        payload.window_id,
    )


def _action(payload: ActionPayload) -> AutomationAction:
    return AutomationAction(
        payload.kind,
        _selector(payload.selector),
        payload.application,
        payload.window_id,
        payload.arguments,
        _verification(payload.verification) if payload.verification else None,
        payload.fallback_allowed,
        payload.max_attempts,
    )
