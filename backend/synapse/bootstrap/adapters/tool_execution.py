from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from synapse.tools.identities import (
    DESKTOP_CANCEL,
    DESKTOP_EXECUTE,
    DESKTOP_PREVIEW,
    DESKTOP_RECOVER,
)
from synapse.tools.models import ToolDefinition, ToolExecutionRequest


class DesktopAutomationToolAdapter:
    """Technology adapter; governance remains inside the frozen Desktop facade."""

    def __init__(self, desktop: Any | Callable[[], Any], operation: str) -> None:
        self._desktop_provider = desktop
        self.operation = operation

    def __call__(self, request: ToolExecutionRequest) -> dict[str, Any]:
        desktop = (
            self._desktop_provider() if callable(self._desktop_provider) else self._desktop_provider
        )
        plan_id = str(request.arguments["plan_id"])
        if self.operation == "preview":
            return asdict(desktop.preview(plan_id))
        if self.operation == "execute":
            return asdict(
                desktop.execute(plan_id, approval_id=request.arguments.get("approval_id"))
            )
        if self.operation == "cancel":
            return asdict(desktop.cancel(plan_id))
        if self.operation == "recover":
            return asdict(
                desktop.recover(plan_id, approval_id=request.arguments.get("approval_id"))
            )
        raise ValueError(f"Unsupported Desktop tool operation: {self.operation}")

    def cancel(self, request: ToolExecutionRequest) -> dict[str, Any]:
        if self.operation != "execute":
            raise ValueError(f"Cancellation is not supported for Desktop {self.operation}")
        desktop = (
            self._desktop_provider() if callable(self._desktop_provider) else self._desktop_provider
        )
        return asdict(desktop.cancel(str(request.arguments["plan_id"])))


def register_desktop_tool_adapters(tools: Any, desktop: Any | Callable[[], Any]) -> None:
    operations = (
        (DESKTOP_PREVIEW, "preview", False),
        (DESKTOP_EXECUTE, "execute", True),
        (DESKTOP_CANCEL, "cancel", True),
        (DESKTOP_RECOVER, "recover", True),
    )
    for tool_id, operation, side_effects in operations:
        tools.register(
            ToolDefinition(
                tool_id=tool_id,
                display_name=f"Desktop {operation.title()}",
                description=f"Canonical adapter for Desktop Automation {operation}.",
                category="desktop_automation",
                input_schema={
                    "type": "object",
                    "required": ["plan_id"],
                    "properties": {
                        "plan_id": {"type": "string"},
                        "approval_id": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={"type": "object"},
                risk_level="low",
                source="desktop",
                provider_id="desktop_runtime",
                supports_cancel=operation == "execute",
                supports_rollback=False,
                metadata={
                    "internal_tool": True,
                    "processing_boundary": "local_process",
                    "side_effects": ["desktop_automation"] if side_effects else [],
                    "owner_governance": True,
                },
            ),
            DesktopAutomationToolAdapter(desktop, operation),
        )
