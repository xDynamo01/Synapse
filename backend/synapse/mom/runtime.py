from __future__ import annotations

from uuid import uuid4

from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.mom.contracts import (
    Configuration,
    ConfigurationPort,
    InferencePort,
    Operation,
    PrimaryPort,
    Result,
    Route,
)
from synapse.mom.selection import classify_operation


class MoMRuntime:
    def __init__(self, primary: PrimaryPort, configurations: ConfigurationPort,
                 inference: InferencePort, permissions: PermissionManager, events: EventBus):
        self.primary = primary
        self.configurations = configurations
        self.inference = inference
        self.permissions = permissions
        self.events = events

    def select_for_chat(self, context: PermissionContext, agent_id: str | None,
                        message: str, workspace_id: str) -> tuple[str, Route, int] | None:
        # An absent/disabled configuration preserves the legacy path. Malformed
        # storage and an enabled but stale binding must never fall back.
        configuration = self.configurations.read(workspace_id)
        if configuration is None or not configuration.enabled:
            return None
        primary_id = self.primary.current_agent(workspace_id)
        if agent_id is not None and agent_id != primary_id:
            return None
        self._admit(context, workspace_id)
        if configuration.primary_agent_id != primary_id:
            raise ValidationError("O Primary mudou. Salve novamente a configuração do MoM.")
        operation = classify_operation(message)
        # Ordinary conversation stays on the generalist without another inference.
        # Retain old conversation routes on disk for explicit API callers only.
        if operation == Operation.CONVERSATION:
            return None
        route = next((route for route in configuration.routes if route.operation == operation), None)
        if route is None:
            raise ValidationError(f"Configure o modelo de {operation.value} em Settings > MoM.")
        self.inference.validate_route(route)
        self.events.emit("mom.chat.selected", primary_id, {
            "workspace_id": workspace_id, "agent_id": primary_id,
            "operation": operation.value, "provider_id": route.provider,
            "model_id": route.model, "configuration_revision": configuration.revision,
            "selection_policy": "local-intent-v1",
        })
        return primary_id, route, configuration.revision

    def _admit(self, context: PermissionContext, workspace_id: str) -> str:
        primary_id = self.primary.current_agent(workspace_id)
        if context.actor_type == "agent":
            if context.actor_id != primary_id:
                raise PermissionDenied("MoM is reserved for the current Primary Agent.")
        elif context.actor_type != "user":
            raise PermissionDenied("MoM requires a user or the current Primary Agent.")
        self.permissions.require(context, "filesystem.read")
        return primary_id

    def get_configuration(self, context: PermissionContext,
                          workspace_id: str = "default") -> Configuration:
        primary_id = self._admit(context, workspace_id)
        return self.configurations.read(workspace_id) or Configuration(
            workspace_id=workspace_id, primary_agent_id=primary_id,
        )

    def configure(self, context: PermissionContext, workspace_id: str,
                  enabled: bool, routes: tuple[Route, ...], expected_revision: int) -> Configuration:
        if context.actor_type != "user":
            raise PermissionDenied("Only the user can configure Primary MoM routes.")
        primary_id = self._admit(context, workspace_id)
        self.permissions.require(context, "filesystem.write")
        configuration = Configuration(
            workspace_id=workspace_id, primary_agent_id=primary_id, enabled=enabled,
            revision=expected_revision + 1, routes=routes,
        )
        if enabled:
            for route in routes:
                self.inference.validate_route(route)
        self.configurations.write(configuration, expected_revision)
        self.events.emit("mom.configured", context.actor_id, {
            "workspace_id": workspace_id, "agent_id": primary_id,
            "revision": configuration.revision, "enabled": enabled,
        })
        return configuration

    def execute(self, context: PermissionContext, operation: Operation, message: str,
                workspace_id: str = "default") -> Result:
        if not message.strip() or len(message) > 32000:
            raise ValidationError("MoM input must contain between 1 and 32000 characters.")
        primary_id = self._admit(context, workspace_id)
        configuration = self.get_configuration(context, workspace_id)
        if not configuration.enabled:
            raise ValidationError("Primary MoM is not enabled.")
        if configuration.primary_agent_id != primary_id:
            raise ValidationError("Primary Agent changed. Reconfigure MoM routes for this Primary.")
        route = next((item for item in configuration.routes if item.operation == operation), None)
        if route is None:
            raise ValidationError(f"No Primary MoM route configured for {operation}.")
        self.inference.validate_route(route)
        if self._admit(context, workspace_id) != primary_id:
            raise ValidationError("Primary Agent changed before MoM admission.")
        operation_id = str(uuid4())
        activity = {
            "operation_id": operation_id, "operation": operation.value,
            "workspace_id": workspace_id, "agent_id": primary_id,
            "provider_id": route.provider, "model_id": route.model,
            "configuration_revision": configuration.revision,
        }
        self.events.emit("mom.operation.started", primary_id, activity)
        try:
            output = self.inference.generate(context, primary_id, route, message, operation_id)
            if output.provider != route.provider or output.model != route.model:
                raise ValidationError("MoM response did not match the selected route.")
        except Exception as exc:
            self.events.emit("mom.operation.failed", primary_id, {
                **activity, "error_type": type(exc).__name__,
            })
            raise
        self.events.emit("mom.operation.completed", primary_id, activity)
        return Result(**output.model_dump(), operation_id=operation_id,
                      operation=operation, primary_agent_id=primary_id,
                      configuration_revision=configuration.revision)
